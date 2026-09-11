import unittest

from apple_support_watch.extract import extract_article


HTML = '''<!doctype html><html><head>
<meta property="og:title" content="Use a feature - Apple Support">
<meta name="description" content="Learn how to use it."></head><body>
<div id="content"><div id="sections"><h2>Before you begin</h2><p>Install the latest software.</p>
<ul><li>First step</li><li><a href="/en-us/654321">Second step</a></li></ul><form><button>Helpful?</button></form></div></div>
</body></html>'''


class ExtractTests(unittest.TestCase):
    def test_extracts_stable_markdown(self):
        article = extract_article(HTML, "https://support.apple.com/en-us/123456", "en-us")
        self.assertEqual(article.title, "Use a feature")
        self.assertIn("# Use a feature", article.markdown)
        self.assertIn("## Before you begin", article.markdown)
        self.assertIn("- First step", article.markdown)
        self.assertIn("[Second step](https://support.apple.com/en-us/654321)", article.markdown)
        self.assertNotIn("Helpful", article.markdown)
        self.assertEqual(len(article.content_hash), 64)


if __name__ == "__main__":
    unittest.main()
