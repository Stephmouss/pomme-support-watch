import unittest

from apple_support_watch.diffing import unified_changes


class DiffTests(unittest.TestCase):
    def test_counts_changes(self):
        excerpt, added, removed = unified_changes("one\ntwo\n", "one\nthree\n")
        self.assertEqual((added, removed), (1, 1))
        self.assertIn("+three", excerpt)
        self.assertIn("-two", excerpt)


if __name__ == "__main__":
    unittest.main()

