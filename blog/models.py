import datetime
import re

from django.db import models
from django.http import Http404, HttpResponsePermanentRedirect

from modelcluster.fields import ParentalKey
from modelcluster.contrib.taggit import ClusterTaggableManager

from taggit.models import TaggedItemBase

from wagtail.contrib.wagtailroutablepage.models import RoutablePageMixin, route
from wagtail.wagtailadmin.edit_handlers import FieldPanel, StreamFieldPanel
from wagtail.wagtailcore import blocks
from wagtail.wagtailcore.models import Page
from wagtail.wagtailcore.fields import RichTextField, StreamField
from wagtail.wagtailcore.url_routing import RouteResult
from wagtail.wagtaildocs.blocks import DocumentChooserBlock
from wagtail.wagtailembeds.blocks import EmbedBlock
from wagtail.wagtailimages.blocks import ImageChooserBlock
from wagtail.wagtailimages.edit_handlers import ImageChooserPanel


class ResponseOverrideWrapper(object):
    """
    Wrapper for a page object that will always serve a particular response.
    This is a workaround for the fact that we can't redirect the user during routing.
    """

    def __init__(self, page, response):
        self.page = page
        self.response = response

    def serve(self, request, *args, **kwargs):
        return self.response

    def __getattr__(self, item):
        return getattr(self.page, item)


class BasePage(Page):
    hero_image = models.ForeignKey(
        'wagtailimages.Image',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+'
    )

    content_panels = Page.content_panels + [
        ImageChooserPanel('hero_image')
    ]


class BlogIndex(RoutablePageMixin, BasePage):
    intro = RichTextField()

    content_panels = BasePage.content_panels + [
        FieldPanel('intro')
    ]

    @route(r'^$')
    def all_posts(self, request):
        return Page.serve(self, request, title='')

    @route(r'^tag/(?P<tag>[\a-zA-Z0-9_-]+)/$')
    def posts_by_tag(self, request, tag):
        posts = self.posts.live().filter(tags__name=tag)

        return Page.serve(self, request, posts=posts, title='Posts tagged "{}"'.format(tag), intro='')

    @route(r'^(?P<year>\d+)/(?:(?P<month>\d{2})/)?$')
    def posts_by_date(self, request, year, month=None):
        posts = self.posts.live()

        if month is None:
            posts = posts.filter(pub_date__year=int(year))
            title = year
        else:
            n_year, n_month = int(year), int(month)
            posts = posts.filter(pub_date__year=n_year, pub_date__month=n_month)
            title = datetime.date(n_year, n_month, 1).strftime('%B %Y')

        return Page.serve(self, request, posts=posts, title=title, intro='')

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)

        posts = kwargs.get('posts', self.posts.live())
        context['posts'] = posts.specific().order_by('-pub_date')

        context['title'] = kwargs.get('title', self.title)
        context['intro'] = kwargs.get('intro', self.intro)

        return context

    @property
    def posts(self):
        return BlogPost.objects.child_of(self)

    _year_re = re.compile(r'^\d+$')
    _month_re = re.compile(r'^\d{2}$')

    def route(self, request, path_components):
        """
        Kludge to insert the publication year and month into BlogPost URLs.

        If the request includes an incorrect year or month, returns a redirect to the canonical URL.
        If the request includes the correct year and month, discards them before delegating to the target post.
        If the request doesn't include a year and month but does include a valid post slug, returns a 404.
        """

        # Handle paths of the form year/month/slug/ - if there's a matching blog post we want to route to it
        if len(path_components) > 2:
            year, month, child_slug = path_components[:3]
            remaining_components = path_components[3:]

            if self._year_re.match(year) and self._month_re.match(month):
                try:
                    post = self.posts.get(slug=child_slug).specific
                except Page.DoesNotExist:
                    pass
                else:
                    # 404 if the post hasn't been published
                    if not post.live:
                        raise Http404

                    # Redirect to the canonical url if the request included incorrect dates
                    if post.pub_date.year != int(year) or post.pub_date.month != int(month):
                        canonical_post_url = post.url
                        if remaining_components:
                            canonical_post_url += '/'.join(remaining_components) + '/'

                        response = HttpResponsePermanentRedirect(canonical_post_url)
                        return RouteResult(ResponseOverrideWrapper(post, response))

                    # Otherwise, delegate routing to the post
                    return post.route(request, remaining_components)

        # Handle paths of the form slug/ - matching blog posts shouldn't be accessible this way
        if len(path_components) > 0:
            child_slug = path_components[0]

            try:
                self.posts.get(slug=child_slug)
            except Page.DoesNotExist:
                pass
            else:
                raise Http404

        # For all other paths, defer to existing routing
        return super().route(request, path_components)


class BlogPostTag(TaggedItemBase):
    content_object = ParentalKey('blog.BlogPost', related_name='tagged_items')


class BlogPost(BasePage):
    pub_date = models.DateField(verbose_name='Publication date')
    body = StreamField([
        ('text', blocks.RichTextBlock()),
        ('image', ImageChooserBlock()),
        ('embed', EmbedBlock()),
        ('document', DocumentChooserBlock())
    ])
    tags = ClusterTaggableManager(through=BlogPostTag, blank=True)

    content_panels = BasePage.content_panels + [
        FieldPanel('pub_date'),
        StreamFieldPanel('body')
    ]

    promote_panels = BasePage.promote_panels + [
        FieldPanel('tags')
    ]

    def set_url_path(self, parent):
        """
        Adds the publication year and month into this page's recorded URL.
        """

        if parent:
            self.url_path = parent.url_path + '{0.year}/{0.month:02}/{1}/'.format(self.pub_date, self.slug)
        else:
            self.url_path = '/'

        return self.url_path
