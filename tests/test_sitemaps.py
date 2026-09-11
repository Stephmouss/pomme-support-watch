import unittest

from apple_support_watch.sitemaps import parse_sitemap_index, parse_urlset


class SitemapTests(unittest.TestCase):
    def test_index_selects_article_sitemaps(self):
        xml = '''<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap><loc>https://example/core-1.xml</loc></sitemap>
          <sitemap><loc>https://example/sitemap-en-us-ac-1.xml</loc></sitemap>
        </sitemapindex>'''
        self.assertEqual(parse_sitemap_index(xml), ["https://example/sitemap-en-us-ac-1.xml"])

    def test_urlset(self):
        xml = '''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://support.apple.com/en-us/123456</loc><lastmod>2026-09-10</lastmod></url>
          <url><loc>https://support.apple.com/fr-fr/123456</loc><lastmod>2026-09-11</lastmod></url>
        </urlset>'''
        self.assertEqual(parse_urlset(xml, "en-us"), {"https://support.apple.com/en-us/123456": "2026-09-10"})


if __name__ == "__main__":
    unittest.main()

