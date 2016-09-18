from collections import Counter
import math

from django_medusa.renderers import StaticSiteRenderer

from wagtail.wagtailcore.models import Page

from blog.models import BlogIndex, BlogPost


class WholeSiteRenderer(StaticSiteRenderer):
    @staticmethod
    def get_paths():
        paths = set()

        for page in Page.objects.live().public():
            url = page.url
            if not url:
                # Page wasn't routable
                continue
            paths.add(url)

            # If this page is a BlogIndex, add pagination and filter urls based on child attributes
            if page.specific_class == BlogIndex:
                page = page.specific
                posts = list(BlogPost.objects.descendant_of(page).live().public().specific().prefetch_related('tags'))

                paths.add(url + page.reverse_subpage('all_posts'))
                for i in range(2, math.ceil(len(posts) / page.posts_per_page) + 1):
                    paths.add(url + page.reverse_subpage('all_posts', kwargs={'page': i}))

                months = Counter((post.pub_date.year, post.pub_date.month) for post in posts)
                years = Counter(post.pub_date.year for post in posts)
                tags = Counter(slug for post in posts for slug in post.tags.slugs())

                for month, count in months.items():
                    kwargs = {'year': month[0], 'month': month[1]}
                    paths.add(url + page.reverse_subpage('posts_by_date', kwargs=kwargs))
                    for i in range(2, math.ceil(count / page.posts_per_page) + 1):
                        kwargs['page'] = i
                        paths.add(url + page.reverse_subpage('posts_by_date', kwargs=kwargs))

                for year, count in years.items():
                    kwargs = {'year': year}
                    paths.add(url + page.reverse_subpage('posts_by_date', kwargs=kwargs))
                    for i in range(2, math.ceil(count / page.posts_per_page) + 1):
                        kwargs['page'] = i
                        paths.add(url + page.reverse_subpage('posts_by_date', kwargs=kwargs))

                for tag, count in tags.items():
                    kwargs = {'tag': tag}
                    paths.add(url + page.reverse_subpage('posts_by_tag', kwargs=kwargs))
                    for i in range(2, math.ceil(count / page.posts_per_page) + 1):
                        kwargs['page'] = i
                        paths.add(url + page.reverse_subpage('posts_by_date', kwargs=kwargs))

        return sorted(paths)


renderers = [WholeSiteRenderer]
