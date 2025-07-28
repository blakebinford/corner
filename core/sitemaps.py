from django.contrib.sitemaps import Sitemap
from django.urls import reverse

class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = 'monthly'

    def items(self):
        return [
            'home',
            'competitions:competition_list',
            'schema',
            'swagger-ui',
            'redoc',
            'accounts:privacy_policy',
            'accounts:terms_of_service',
            'accounts:cookie_policy',
            'accounts:about',
        ]

    def location(self, item):
        return reverse(item)
