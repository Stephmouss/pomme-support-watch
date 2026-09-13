import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apple_support_watch.models import Article
from apple_support_watch.watcher import Watcher


def make_article(text: str) -> Article:
    import hashlib

    markdown = f"# Test article\n\n{text}\n"
    return Article(
        url="https://support.apple.com/en-us/123456",
        article_id="123456",
        locale="en-us",
        title="Test article",
        description="Test description",
        markdown=markdown,
        content_hash=hashlib.sha256(markdown.encode()).hexdigest(),
    )


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = {
            "site_title": "Test Watch",
            "user_agent": "Test/1.0",
            "request_timeout_seconds": 2,
            "request_delay_seconds": 0,
            "bootstrap_batch_size": 10,
            "audit_batch_size": 0,
            "removal_confirmations": 2,
            "feed_item_limit": 10,
            "feed_diff_line_limit": 10,
            "sources": [
                {"locale": "en-us", "label": "English", "index": "https://example.test/index.xml"}
            ],
        }
        self.url = "https://support.apple.com/en-us/123456"

    def tearDown(self):
        self.temp.cleanup()

    def test_initializes_silently_then_emits_update(self):
        with patch("apple_support_watch.watcher.fetch_articles", return_value={self.url: "2026-01-01"}), patch.object(
            Watcher, "_fetch_article", return_value=make_article("First version")
        ):
            first = Watcher(self.root, self.config)
            first.run()
        self.assertEqual(first.created_events, [])
        self.assertTrue((self.root / "snapshots/en-us/123456.md").exists())

        with patch("apple_support_watch.watcher.fetch_articles", return_value={self.url: "2026-01-02"}), patch.object(
            Watcher, "_fetch_article", return_value=make_article("Second version")
        ):
            second = Watcher(self.root, self.config)
            second.run()
        self.assertEqual(len(second.created_events), 1)
        self.assertEqual(second.created_events[0].kind, "updated")
        self.assertEqual((second.created_events[0].added, second.created_events[0].removed), (1, 1))
        events = json.loads((self.root / "events/en-us.json").read_text())
        self.assertEqual(events[0]["kind"], "updated")
        feed = (self.root / "public/feeds/en-us-updated.xml").read_text()
        self.assertIn("[UPDATED] Test article", feed)
        self.assertIn("Second version", feed)
        self.assertTrue(any((self.root / "public/diffs/en-us/123456").glob("*.html")))

    def test_disappearance_is_tracked_without_an_event(self):
        with patch("apple_support_watch.watcher.fetch_articles", return_value={self.url: "2026-01-01"}), patch.object(
            Watcher, "_fetch_article", return_value=make_article("First version")
        ):
            Watcher(self.root, self.config).run()

        state_path = self.root / "state/en-us.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["sitemap_count"] = 0
        state_path.write_text(json.dumps(state), encoding="utf-8")

        for _ in range(2):
            with patch("apple_support_watch.watcher.fetch_articles", return_value={}):
                watcher = Watcher(self.root, self.config)
                watcher.run()

        self.assertEqual(watcher.created_events, [])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertFalse(state["articles"][self.url]["active"])
        events = json.loads((self.root / "events/en-us.json").read_text(encoding="utf-8"))
        self.assertEqual(events, [])
        feed = (self.root / "public/feeds/en-us-updated.xml").read_text(encoding="utf-8")
        self.assertNotIn("REMOVED", feed)


if __name__ == "__main__":
    unittest.main()
