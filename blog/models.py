import datetime
import itertools
import os
import re

from bakery.feeds import BuildableFeed

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect, HttpResponsePermanentRedirect
from django.test import RequestFactory
from django.utils.feedgenerator import Atom1Feed
from django.utils.timezone import get_default_timezone, localtime
from django.utils.translation import gettext_lazy as _

from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey

from taggit.models import TaggedItemBase

from wagtail.admin.edit_handlers import FieldPanel, MultiFieldPanel, StreamFieldPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, route
from wagtail.core.fields import StreamField
from wagtail.core.models import Page
from wagtail.core.url_routing import RouteResult
from wagtail.images.edit_handlers import ImageChooserPanel
from wagtail.snippets.edit_handlers import SnippetChooserPanel
from wagtail.snippets.models import register_snippet

from .blocks import ContentBlock, ContentMethodsMixin


PAGINATION_REGEX = r'(?:page/(?P<page_num>[1-9]\d+|[2-9])/)?'


class ResponseOverrideWrapper(object):
    """
    Wrapper for a Page instance that will always serve a particular response.
    This is a workaround for our inability to redirect the user during routing.
    We could raise a Http301 exception if one existed, but right now
    redirection requires us to return a response object. All method calls
    aside from serve() are forwarded to the wrapped Page.
    """

    def __init__(self, page, response):
        self.page = page
        self.response = response

    def serve(self, request, *args, **kwargs):
        return self.response

    def __getattr__(self, item):
        return getattr(self.page, item)


@register_snippet
class HeroImage(models.Model):
    name = models.CharField(max_length=128)

    wagtail_image = models.ForeignKey(
        'wagtailimages.Image',
        verbose_name='Wagtail image',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='+'
    )
    svg_image = models.FileField(
        'SVG image',
        upload_to='hero_images/',
        blank=True,
        validators=[FileExtensionValidator(['svg'])]
    )

    wagtail_image_dark = models.ForeignKey(
        'wagtailimages.Image',
        verbose_name='dark Wagtail image',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='+',
        help_text='Alternative Wagtail image to display in dark mode.'
    )
    svg_image_dark = models.FileField(
        'dark SVG image',
        upload_to='hero_images/',
        blank=True,
        validators=[FileExtensionValidator(['svg'])],
        help_text='Alternative SVG image to display in dark mode.'
    )

    add_parallax = models.BooleanField()
    repeat = models.CharField(
        'background repeat',
        max_length=11,
        choices=[
            ('repeat_none', 'No repeat'),
            ('repeat_x', 'Horizontally'),
            ('repeat_y', 'Vertically'),
            ('repeat_both', 'Both directions'),
        ],
        default='repeat_none'
    )
    position = models.CharField(
        'background position',
        max_length=13,
        choices=[
            ('top left', 'Top left'),
            ('top center', 'Top center'),
            ('top right', 'Top right'),
            ('mid left', 'Mid left'),
            ('mid center', 'Mid center'),
            ('mid right', 'Mid right'),
            ('bottom left', 'Bottom left'),
            ('bottom center', 'Bottom center'),
            ('bottom right', 'Bottom right'),
        ],
        default='mid center'
    )
    text_color = models.CharField(
        help_text='The color to use for overlaid text, to ensure contrast.',
        max_length=6,
        choices=[
            ('light', 'Light text'),
            ('dark', 'Dark text'),
            ('either', 'Either color ok'),
        ]
    )

    panels = [
        FieldPanel('name'),
        MultiFieldPanel([
            ImageChooserPanel('wagtail_image'),
            ImageChooserPanel('wagtail_image_dark'),
            FieldPanel('svg_image'),
            FieldPanel('svg_image_dark'),
        ], heading='Images'),
        MultiFieldPanel([
            FieldPanel('add_parallax'),
            FieldPanel('repeat'),
            FieldPanel('position'),
            FieldPanel('text_color'),
        ], heading='Display options'),
    ]

    def __str__(self):
        return self.name

    def clean(self):
        if not self.wagtail_image and not self.svg_image:
            raise ValidationError(_('Either a Wagtail image or SVG image is required.'))
        if self.wagtail_image and self.svg_image:
            raise ValidationError(_('Only one Wagtail image or SVG image is allowed.'))
        if (self.wagtail_image_dark and not self.wagtail_image) or (self.svg_image_dark and not self.svg_image):
            raise ValidationError(_('Dark Wagtail/SVG images require a corresponding non-dark image'))


class BlogPostFeed(BuildableFeed):
    feed_type = Atom1Feed

    # Shenanigans to get BuildableFeed to support multiple feed subjects

    def get_queryset(self):
        return BlogIndex.objects.all().public()

    def build_path(self, obj):
        return os.path.join(self.feed_url(obj)[1:], 'atom.xml')

    def create_request(self, url, obj):
        # Essentially what the superclass method does, but this stops
        # all the feed links from pointing to domain "testserver"
        hostname = obj.get_site().hostname
        return RequestFactory(SERVER_NAME=hostname).get(url)

    def get_content(self, obj):
        return super().get_content(blog_index=obj)

    # The standard Feed methods

    def get_object(self, request, blog_index):
        return blog_index

    def title(self, obj):
        return obj.title

    subtitle = ''

    def link(self, obj):
        return obj.url

    def feed_url(self, obj):
        return obj.url + obj.reverse_subpage('feed')

    def items(self, obj):
        return obj.public_posts().order_by('-pub_date', '-id').specific()[:10]

    def item_title(self, item):
        return item.title

    description_template = 'stream_nowrappers.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stream'] = kwargs['item'].body
        return context

    def item_link(self, item):
        return item.url

    def item_pubdate(self, item):
        return item.pub_date

    def item_updateddate(self, item):
        return max(self.item_pubdate(item), item.last_published_at)


class BasePage(Page):
    is_creatable = False

    hero_image = models.ForeignKey(
        HeroImage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+'
    )

    content_panels = Page.content_panels + [
        SnippetChooserPanel('hero_image')
    ]


class AboutPage(BasePage, ContentMethodsMixin):
    body = StreamField(ContentBlock())

    content_panels = BasePage.content_panels + [
        StreamFieldPanel('body')
    ]


class BlogIndex(RoutablePageMixin, BasePage):
    posts_per_pagination_page = 3
    feed_view = BlogPostFeed()

    @route('^' + PAGINATION_REGEX + '$')
    def all_posts(self, request, page_num=None):
        page_num = page_num and int(page_num)
        return self.paginate(request, posts=self.public_posts(),
                             view_name='all_posts', view_kwargs={'page_num': page_num}, title=self.title)

    @route(r'^tag/(?P<tag>[a-zA-Z0-9_-]+)/' + PAGINATION_REGEX + '$')
    def posts_by_tag(self, request, tag, page_num=None):
        page_num = page_num and int(page_num)
        return self.paginate(request, posts=self.public_posts().filter(tags__name=tag),
                             view_name='posts_by_tag', view_kwargs={'tag': tag, 'page_num': page_num},
                             title='Posts tagged "{}"'.format(tag), hero_title='#{}'.format(tag))

    @route(r'^(?P<year>[1-9]\d*)/' + PAGINATION_REGEX + '$')
    @route(r'^(?P<year>[1-9]\d*)/(?P<month>1[0-2])/' + PAGINATION_REGEX + '$')
    @route(r'^(?P<year>[1-9]\d*)/0(?P<month>[1-9])/' + PAGINATION_REGEX + '$')
    def posts_by_date(self, request, year, month=None, page_num=None):
        year = int(year)
        month = month and int(month)
        page_num = page_num and int(page_num)

        if month is None:
            posts = self.public_posts().filter(pub_date__year=year)
            title = year
        else:
            posts = self.public_posts().filter(pub_date__year=year, pub_date__month=month)
            title = datetime.date(year, month, 1).strftime('%B %Y')

        return self.paginate(request, title=title, posts=posts,
                             view_name='posts_by_date',
                             view_kwargs={'year': year, 'month': month, 'page_num': page_num})

    @route(r'^feed/$')
    def feed(self, request):
        return self.feed_view(request, blog_index=self)

    def paginate(self, request, posts, view_name, view_kwargs=None, **kwargs):
        paginator = Paginator(posts.specific().order_by('-pub_date', '-id'), self.posts_per_pagination_page)
        view_kwargs = {k: v for k, v in view_kwargs.items() if v is not None}
        page_num = view_kwargs.get('page_num', 1)

        if page_num > paginator.num_pages:
            if paginator.num_pages > 1:
                view_kwargs['page_num'] = paginator.num_pages
            else:
                del view_kwargs['page_num']
            return HttpResponseRedirect(self.url + self.reverse_subpage(view_name, kwargs=view_kwargs))

        page = paginator.page(page_num)
        prev_url = next_url = None

        if page.has_previous():
            if page.previous_page_number() > 1:
                view_kwargs['page_num'] = page.previous_page_number()
            else:
                del view_kwargs['page_num']
            prev_url = self.url + self.reverse_subpage(view_name, kwargs=view_kwargs)

        if page.has_next():
            view_kwargs['page_num'] = page.next_page_number()
            next_url = self.url + self.reverse_subpage(view_name, kwargs=view_kwargs)

        return Page.serve(self, request, posts=page, prev_page_url=prev_url, next_page_url=next_url, **kwargs)

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)

        posts = kwargs['posts']
        full_posts = context.get('full_posts', False)

        def limit(blocks):
            return blocks if full_posts else itertools.islice(blocks, 1)

        context['includes_math'] = any(post.block_contains_math(block)
                                       for post in posts
                                       for block in limit(post.all_text_blocks()))

        context.update(kwargs)

        return context

    def posts(self):
        return BlogPost.objects.child_of(self)

    def public_posts(self):
        return self.posts().live().public()

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
                    post = self.posts().get(slug=child_slug).specific
                except Page.DoesNotExist:
                    pass
                else:
                    # 404 if the post hasn't been published
                    if not post.live:
                        raise Http404

                    # Redirect to the canonical url if the request included incorrect dates
                    if str(post.pub_date_norm.year) != year or '{:02}'.format(post.pub_date_norm.month) != month:
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
                self.posts().get(slug=child_slug)
            except Page.DoesNotExist:
                pass
            else:
                raise Http404

        # For all other paths, defer to existing routing
        return super().route(request, path_components)


class BlogPostTag(TaggedItemBase):
    content_object = ParentalKey('blog.BlogPost', related_name='tagged_items')


class BlogPost(BasePage, ContentMethodsMixin):
    parent_page_types = ['blog.BlogIndex']

    pub_date = models.DateTimeField(verbose_name='Publication date')
    body = StreamField(ContentBlock())
    tags = ClusterTaggableManager(through=BlogPostTag, blank=True)

    content_panels = BasePage.content_panels + [
        FieldPanel('pub_date'),
        StreamFieldPanel('body'),
    ]

    promote_panels = BasePage.promote_panels + [
        FieldPanel('tags')
    ]

    def set_url_path(self, parent):
        """
        Adds the publication year and month into this page's recorded URL.
        """

        if parent:
            self.url_path = parent.url_path + '{0.year}/{0.month:02}/{1}/'.format(self.pub_date_norm, self.slug)
        else:
            self.url_path = '/'

        return self.url_path

    @property
    def pub_date_norm(self):
        return localtime(self.pub_date, get_default_timezone())

    def prev_post(self):
        q = Q(pub_date__lt=self.pub_date)
        if self.id:
            q |= Q(pub_date__lte=self.pub_date) & Q(id__lt=self.id)

        return (self.get_parent().specific.public_posts()
                .filter(q)
                .order_by('-pub_date', '-id')
                .specific().first())

    def next_post(self):
        q = Q(pub_date__gt=self.pub_date)
        if self.id:
            q |= Q(pub_date__gte=self.pub_date) & Q(id__gt=self.id)

        return (self.get_parent().specific.public_posts()
                .filter(q)
                .order_by('pub_date', 'id')
                .specific().first())
