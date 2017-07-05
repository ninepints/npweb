import datetime
import math
import re

from django.db import models
from django.http import Http404, HttpResponseRedirect, HttpResponsePermanentRedirect

from modelcluster.fields import ParentalKey
from modelcluster.contrib.taggit import ClusterTaggableManager

from taggit.models import TaggedItemBase

from wagtail.contrib.wagtailroutablepage.models import RoutablePageMixin, route
from wagtail.wagtailadmin.edit_handlers import FieldPanel, StreamFieldPanel
from wagtail.wagtailcore.models import Page
from wagtail.wagtailcore.fields import StreamField
from wagtail.wagtailcore.url_routing import RouteResult
from wagtail.wagtailimages.edit_handlers import ImageChooserPanel

from .blocks import ContentBlock, ContentMethodsMixin


pagination_regex = r'(?:page/(?P<page_num>[1-9]\d+|[2-9])/)?'


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
    is_creatable = False

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


class AboutPage(BasePage, ContentMethodsMixin):
    body = StreamField(ContentBlock())

    content_panels = BasePage.content_panels + [
        StreamFieldPanel('body')
    ]


class BlogIndex(RoutablePageMixin, BasePage):
    posts_per_pagination_page = 3

    @route(r'^' + pagination_regex + '$')
    def all_posts(self, request, page_num=None):
        page_num = page_num and int(page_num)
        return self.paginate(request, posts=self.public_posts,
                             view_name='all_posts', view_kwargs={'page_num': page_num},
                             title=self.title, title_root=True)

    @route(r'^tag/(?P<tag>[\a-zA-Z0-9_-]+)/' + pagination_regex + r'$')
    def posts_by_tag(self, request, tag, page_num=None):
        page_num = page_num and int(page_num)
        return self.paginate(request, posts=self.public_posts.filter(tags__name=tag),
                             view_name='posts_by_tag', view_kwargs={'tag': tag, 'page_num': page_num},
                             title='Posts tagged "{}"'.format(tag), hero_title='#{}'.format(tag))

    @route(r'^(?P<year>[1-9]\d*)/' + pagination_regex + r'$')
    @route(r'^(?P<year>[1-9]\d*)/(?P<month>1[0-2])/' + pagination_regex + r'$')
    @route(r'^(?P<year>[1-9]\d*)/0(?P<month>[1-9])/' + pagination_regex + r'$')
    def posts_by_date(self, request, year, month=None, page_num=None):
        year = int(year)
        month = month and int(month)
        page_num = page_num and int(page_num)

        if month is None:
            posts = self.public_posts.filter(pub_date__year=year)
            title = year
        else:
            posts = self.public_posts.filter(pub_date__year=year, pub_date__month=month)
            title = datetime.date(year, month, 1).strftime('%B %Y')

        return self.paginate(request, title=title, posts=posts,
                             view_name='posts_by_date',
                             view_kwargs={'year': year, 'month': month, 'page_num': page_num})

    def paginate(self, request, posts, view_name, view_kwargs=None, **kwargs):
        post_count = posts.count()
        max_page = max(math.ceil(post_count / self.posts_per_pagination_page), 1)
        view_kwargs = {k: v for k, v in view_kwargs.items() if v is not None}
        page_num = view_kwargs.get('page_num', 1)

        if page_num > max_page == 1:
            del view_kwargs['page_num']
            return HttpResponseRedirect(self.url + self.reverse_subpage(view_name, kwargs=view_kwargs))
        elif page_num > max_page:
            view_kwargs['page_num'] = max_page
            return HttpResponseRedirect(self.url + self.reverse_subpage(view_name, kwargs=view_kwargs))

        pagination_start_index = (page_num - 1) * self.posts_per_pagination_page
        pagination_end_index = page_num * self.posts_per_pagination_page

        prev_page_url = next_page_url = None
        if page_num == 2:
            del view_kwargs['page_num']
            prev_page_url = self.url + self.reverse_subpage(view_name, kwargs=view_kwargs)
        elif page_num > 2:
            view_kwargs['page_num'] = page_num - 1
            prev_page_url = self.url + self.reverse_subpage(view_name, kwargs=view_kwargs)
        if post_count > pagination_end_index:
            view_kwargs['page_num'] = page_num + 1
            next_page_url = self.url + self.reverse_subpage(view_name, kwargs=view_kwargs)

        posts = posts.specific().order_by('-pub_date')[pagination_start_index:pagination_end_index]

        return Page.serve(self, request, posts=posts,
                          prev_page_url=prev_page_url, next_page_url=next_page_url,
                          **kwargs)

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)

        posts = kwargs['posts']
        full_posts = context.get('full_posts', False)
        context['includes_math'] = any(post.contains_math if full_posts else post.first_text_block_contains_math
                                       for post in posts)

        context.update(kwargs)

        return context

    @property
    def posts(self):
        return BlogPost.objects.child_of(self)

    @property
    def public_posts(self):
        return self.posts.live().public()

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


class BlogPost(BasePage, ContentMethodsMixin):
    parent_page_types = ['blog.BlogIndex']

    pub_date = models.DateTimeField(verbose_name='Publication date')
    body = StreamField(ContentBlock())
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
        return (self.get_parent().specific.public_posts
                .not_page(self)
                .specific()
                .filter(pub_date__lte=self.pub_date)
                .order_by('-pub_date')
                .first())

    @property
    def next_post(self):
        return (self.get_parent().specific.public_posts
                .not_page(self)
                .specific()
                .filter(pub_date__gte=self.pub_date)
                .order_by('pub_date')
                .first())
