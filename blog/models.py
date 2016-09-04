import datetime
import math
import re

from django.db import models
from django.http import Http404, HttpResponsePermanentRedirect
from django.http import HttpResponseRedirect

from modelcluster.fields import ParentalKey
from modelcluster.contrib.taggit import ClusterTaggableManager

from taggit.models import TaggedItemBase

from wagtail.contrib.wagtailroutablepage.models import RoutablePageMixin, route
from wagtail.wagtailadmin.edit_handlers import FieldPanel, StreamFieldPanel
from wagtail.wagtailcore.blocks import RichTextBlock
from wagtail.wagtailcore.models import Page
from wagtail.wagtailcore.fields import StreamField
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
    subpage_types = ['blog.BlogPost']

    posts_per_page = 3

    @route(r'^$')
    def all_posts(self, request):
        return self.paginate(request, posts=self.posts.live(), view_name='all_posts',
                             title=self.title, title_root=True)

    @route(r'^tag/(?P<tag>[\a-zA-Z0-9_-]+)/$')
    def posts_by_tag(self, request, tag):
        return self.paginate(request, posts=self.posts.live().filter(tags__name=tag),
                             view_name='posts_by_tag', view_kwargs={'tag': tag},
                             title='Posts tagged "{}"'.format(tag), hero_title='#{}'.format(tag))

    @route(r'^(?P<year>\d+)/$')
    @route(r'^(?P<year>\d+)/(?P<month>\d{2})/$')
    @route(r'^(?P<year>\d+)/0(?P<month>\d{1})/$')  # A subset of the previous pattern, included for the URL reverser
    def posts_by_date(self, request, year, month=None):
        if month is None:
            posts = self.posts.live().filter(pub_date__year=int(year))
            title = year
        else:
            n_year, n_month = int(year), int(month)
            posts = self.posts.live().filter(pub_date__year=n_year, pub_date__month=n_month)
            title = datetime.date(n_year, n_month, 1).strftime('%B %Y')

        return self.paginate(request, posts=posts,
                             view_name='posts_by_date', view_kwargs={'year': year, 'month': month}, title=title)

    def paginate(self, request, posts, view_name, view_kwargs=None, **kwargs):
        post_count = posts.count()
        max_page = max(math.ceil(post_count / self.posts_per_page), 1)
        base_url = self.url + self.reverse_subpage(view_name, kwargs=view_kwargs)

        try:
            page = int(request.GET.get('page', 1))
        except (TypeError, ValueError):
            page = 1
        if page < 1 or page > max_page == 1:
            return HttpResponseRedirect(base_url)
        elif page > max_page:
            return HttpResponseRedirect(base_url + '?page=' + str(max_page))

        page_start_index = (page - 1) * self.posts_per_page
        page_end_index = page * self.posts_per_page

        prev_page_url = next_page_url = None
        if page == 2:
            prev_page_url = base_url
        elif page > 2:
            prev_page_url = base_url + '?page=' + str(page - 1)
        if post_count > page_end_index:
            next_page_url = base_url + '?page=' + str(page + 1)

        posts = posts.specific().order_by('-pub_date')[page_start_index:page_end_index]

        return Page.serve(self, request, posts=posts,
                          prev_page_url=prev_page_url, next_page_url=next_page_url,
                          any_post_contains_math=any(post.contains_math for post in posts),
                          **kwargs)

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context.update(kwargs)
        return context

    @property
    def posts(self):
        return BlogPost.objects.child_of(self)

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

            if re.match(r'^\d+$', year) and re.match(r'^\d{2}$', month):
                try:
                    post = self.posts.get(slug=child_slug).specific
                except Page.DoesNotExist:
                    pass
                else:
                    # 404 if the post hasn't been published
                    if not post.live:
                        raise Http404

                    # Redirect to the canonical url if the request included incorrect dates
                    if str(post.pub_date.year) != year or '{:02}'.format(post.pub_date.month) != month:
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
    parent_page_types = ['blog.BlogIndex']

    pub_date = models.DateTimeField(verbose_name='Publication date')
    body = StreamField([
        ('text', RichTextBlock()),
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

    @property
    def prev_post(self):
        return (self.get_parent().specific.posts
                .live()
                .not_page(self)
                .specific()
                .filter(pub_date__lte=self.pub_date)
                .order_by('-pub_date')
                .first())

    @property
    def next_post(self):
        return (self.get_parent().specific.posts
                .live()
                .not_page(self)
                .specific()
                .filter(pub_date__gte=self.pub_date)
                .order_by('pub_date')
                .first())

    @property
    def first_text_block(self):
        try:
            return next(block for block in self.body if isinstance(block.block, RichTextBlock))
        except StopIteration:
            return None

    @property
    def contains_math(self):
        return any(isinstance(block.block, RichTextBlock)
                   and re.search(r'(?:\\\[.*\\\])|(?:\\\(.*\\\))', block.value.source)
                   for block in self.body)
