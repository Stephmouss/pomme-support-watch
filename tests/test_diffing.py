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

    def test_html_diff_uses_two_equal_readable_panes(self):
        old = "\n".join([f"unchanged {index}" for index in range(8)] + ["AirPods Pro"] + ["ending"] * 8)
        new = "\n".join(
            [f"unchanged {index}" for index in range(8)] + ["AirPods 5 and AirPods Pro"] + ["ending"] * 8
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "diff.html"
            write_html_diff(path, old, new, "Long comparison", "https://support.apple.com/000000")
            page = path.read_text(encoding="utf-8")

        self.assertIn('class="diff-grid"', page)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(0, 1fr)", page)
        self.assertIn("grid-template-columns: 3.5rem minmax(0, 1fr)", page)
        self.assertIn('class="pane-header previous">Version précédente', page)
        self.assertIn('class="pane-header current">Version actuelle', page)
        self.assertNotIn("<table", page)

    def test_html_diff_highlights_edits_and_folds_unchanged_text(self):
        old = "\n".join([f"before {index}" for index in range(12)] + ["AirPods Pro"] + [f"after {index}" for index in range(12)])
        new = "\n".join(
            [f"before {index}" for index in range(12)]
            + ["AirPods 5 and AirPods Pro"]
            + [f"after {index}" for index in range(12)]
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "diff.html"
            write_html_diff(path, old, new, "AirPods", "https://support.apple.com/108918")
            page = path.read_text(encoding="utf-8")

        self.assertIn('class="inline-add">AirPods 5 and </mark>', page)
        self.assertIn("lignes inchangées masquées", page)
        self.assertIn("+1 ajout", page)
        self.assertIn("−1 suppression", page)


if __name__ == "__main__":
    unittest.main()
