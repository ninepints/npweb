from collections import Counter
import math
import os

from django.conf import settings
from django.db.models import Count
from django.db.models.functions import ExtractMonth, ExtractYear
from django.test import RequestFactory
from wagtail.wagtailcore.models import Page
from wagtailbakery.views import WagtailBakeryView

from .models import BlogIndex, BlogPostTag


class BlogIndexView(WagtailBakeryView):
    def get_queryset(self):
        return BlogIndex.objects.all().public()

    def build_object(self, obj):
        # Build tag view
        tag_counts = ((tag, tag.post_count) for tag in BlogPostTag.tag_model().objects
            .filter(blogpost__in=obj.public_posts())
            .annotate(post_count=Count('blogpost')))
        self.paginate_subpage(obj, tag_counts, 'posts_by_tag', lambda tag: {'tag': tag.slug})

        # Build date view
        # It's possible to get a post count by publication year/month via the ORM, but this
        # is much more straightforward. For the record, I did get the ORM version working.
        pub_dates = obj.public_posts().values_list(ExtractYear('pub_date'), ExtractMonth('pub_date'))
        month_counter = Counter(pub_dates)
        year_counter = Counter(ym[0] for ym in pub_dates)
        self.paginate_subpage(obj, month_counter.items(), 'posts_by_date', lambda ym: {'year': ym[0], 'month': ym[1]})
        self.paginate_subpage(obj, year_counter.items(), 'posts_by_date', lambda year: {'year': year})

        # Build all posts view
        self.paginate_subpage(obj, ((None, sum(year_counter.values())),), 'all_posts', lambda _: {})

    def paginate_subpage(self, page, counts, view_name, view_kwargs_func):
        for key, count in counts:
            view_kwargs = view_kwargs_func(key)
            for page_num in range(1, math.ceil(count / page.posts_per_pagination_page) + 1):
                if page_num > 1:
                    view_kwargs['page_num'] = page_num
                self.build_subpage(page, view_name, view_kwargs)

    def build_subpage(self, page, view_name, view_kwargs):
        hostname = page.get_site().hostname
        url = os.path.join(page.url, page.reverse_subpage(view_name, kwargs=view_kwargs))

        self.request = RequestFactory(SERVER_NAME=hostname).get(url)
        content = self.get_content(page)

        path = os.path.join(settings.BUILD_DIR, url[1:])
        if not os.path.exists(path):
            os.makedirs(path)
        path = os.path.join(path, 'index.html')

        self.build_file(path, content)


class OtherPagesView(WagtailBakeryView):
    def get_queryset(self):
        return Page.objects.all().public().not_type(BlogIndex)
