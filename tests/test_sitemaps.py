import unittest

from apple_support_watch.sitemaps import canonical_article_url, parse_sitemap_index, parse_urlset


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

    def test_urlset_deduplicates_device_variants(self):
        xml = '''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://support.apple.com/fr-fr/119902?device-type=iphone</loc><lastmod>2026-09-17</lastmod></url>
          <url><loc>https://support.apple.com/fr-fr/119902</loc><lastmod>2026-09-18</lastmod></url>
          <url><loc>https://support.apple.com/fr-fr/119902?device-type=mac</loc><lastmod>2026-09-16</lastmod></url>
        </urlset>'''
        self.assertEqual(
            parse_urlset(xml, "fr-fr"),
            {"https://support.apple.com/fr-fr/119902": "2026-09-18"},
        )

    def test_canonical_article_url_removes_query_and_fragment(self):
        self.assertEqual(
            canonical_article_url("https://support.apple.com/fr-fr/119902?device-type=iphone#balance"),
            "https://support.apple.com/fr-fr/119902",
        )


if __name__ == "__main__":
    unittest.main()
