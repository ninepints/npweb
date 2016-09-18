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

            # If this page is a BlogIndex, add filter urls based on child attributes
            if page.specific_class == BlogIndex:
                page = page.specific

                for post in BlogPost.objects.descendant_of(page).live().public().specific().prefetch_related('tags'):
                    paths.add(url + page.reverse_subpage('posts_by_date', args=(post.pub_date.year,
                                                                                post.pub_date.month)))
                    paths.add(url + page.reverse_subpage('posts_by_date', args=(post.pub_date.year,)))

                    for tag in post.tags.all():
                        paths.add(url + page.reverse_subpage('posts_by_tag', args=(tag,)))

        return sorted(paths)


renderers = [WholeSiteRenderer]
