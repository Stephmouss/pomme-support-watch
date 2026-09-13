import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from apple_support_watch.diffing import unified_changes, write_html_diff


class DiffTests(unittest.TestCase):
    def test_counts_changes(self):
        excerpt, added, removed = unified_changes("one\ntwo\n", "one\nthree\n")
        self.assertEqual((added, removed), (1, 1))
        self.assertIn("+three", excerpt)
        self.assertIn("-two", excerpt)

    def test_html_diff_wraps_long_content_without_overlap(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "diff.html"
            write_html_diff(
                path,
                "Previous " * 80,
                "Current " * 80,
                "Long comparison",
                "https://support.apple.com/000000",
            )
            page = path.read_text(encoding="utf-8")

        self.assertIn('class="diff-scroll"', page)
        self.assertIn("min-width: 760px", page)
        self.assertIn("white-space: pre-wrap !important", page)
        self.assertIn("word-break: break-word", page)


if __name__ == "__main__":
    unittest.main()

