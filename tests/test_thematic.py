import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apple_support_watch.http import HttpClient
from apple_support_watch.thematic import (ThemeItem, ThematicWatcher, _jobs_payload, _selected_job,
                                          extract_availability_france, extract_esim_france, extract_maps_france)


class ThematicExtractorTests(unittest.TestCase):
    def test_france_availability_ignores_other_countries(self):
        def page(other):
            return "".join(f'<section class="features" id="feature-{i}"><h2>Feature {i}</h2>'
                           f'<ul><li>French (France)</li><li>{other}</li></ul></section>' for i in range(21))
        old = extract_availability_france(page("German"), "https://www.apple.com/ios/feature-availability/", "ios")
        new = extract_availability_france(page("Spanish"), "https://www.apple.com/ios/feature-availability/", "ios")
        self.assertEqual([item.content_hash for item in old], [item.content_hash for item in new])
        self.assertIn("French (France)", old[0].markdown)
        self.assertNotIn("German", old[0].markdown)

    def test_macos_uses_fourth_level_headings(self):
        html = "".join(f'<section class="features" id="mac-{i}"><h4>Feature {i}</h4>'
                       '<ul><li>France</li></ul></section>' for i in range(21))
        items = extract_availability_france(html, "https://www.apple.com/macos/feature-availability/", "macos")
        self.assertEqual(len(items), 21)
        self.assertIn("macOS", items[0].title)

    def test_careers_filter_discards_retail_and_broad_roles(self):
        self.assertFalse(_selected_job({"postingTitle": "FR - Specialist", "team": {"teamName": "Apple Retail"}}, False))
        self.assertTrue(_selected_job({"postingTitle": "Wallet Payments Manager", "team": {},
                                       "jobSummary": "Work on Wallet capabilities for France."}, False))
        self.assertTrue(_selected_job({"postingTitle": "Health Sensing Hardware Engineer", "team": {},
                                       "locations": []}, True))
        self.assertFalse(_selected_job({"postingTitle": "Satellite Sales Manager", "team": {},
                                        "locations": []}, True))

    def test_careers_missing_hydration_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "search data is missing"):
            _jobs_payload("<html><body>No listings</body></html>", "search")

    def test_extracts_only_selected_france_esim_section(self):
        html = """
        <select><option value="TAG_FR" name="france" selected>France</option></select>
        <h2 class="TAG_FR">France</h2>
        <h3 class="TAG_FR">eSIM Quick Transfer</h3>
        <ul class="TAG_FR"><li><a href="https://carrier.test">Example Mobile</a></li></ul>
        <h2 class="TAG_US">United States</h2><p class="TAG_US">Other carrier</p>
        """
        item = extract_esim_france(html, "https://support.apple.com/en-us/101569")
        self.assertIn("Example Mobile", item.markdown)
        self.assertNotIn("Other carrier", item.markdown)

    def test_extracts_maps_collection_table(self):
        html = """
        <section class="select-country">France</section>
        <section class="section"><h3>Type: Pedestrian - Backpack</h3>
        <table><tr><th>Region</th><th>Periods</th></tr>
        <tr><td>Ile-de-France</td><td>April 6 - June 30</td></tr></table></section>
        """
        item = extract_maps_france(html, "https://maps.apple.com/imagecollection/locations/fr")
        self.assertIn("Ile-de-France", item.markdown)
        self.assertIn("April 6 - June 30", item.markdown)


class ThematicWatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = {
            "user_agent": "Test/1.0",
            "request_timeout_seconds": 2,
            "request_delay_seconds": 0,
            "removal_confirmations": 2,
            "feed_item_limit": 10,
            "feed_diff_line_limit": 10,
            "themes": [{
                "slug": "test-theme",
                "title": "Test theme",
                "sources": [{"type": "dsa", "url": "https://example.test"}],
            }],
        }
        self.client = HttpClient("Test/1.0", 2, 0)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def item(text: str) -> ThemeItem:
        return ThemeItem(
            item_id="test:item",
            collection="test:collection",
            title="Test item",
            url="https://example.test/item",
            source_name="Apple Test",
            category="Test category",
            description="Test description",
            markdown=f"# Test item\n\n{text}\n",
        )

    def test_baseline_is_silent_then_update_has_diff(self):
        first = ThematicWatcher(self.root, self.config, self.client, "https://pages.test")
        with patch.object(first, "_fetch_source", return_value=({"test:collection": [self.item("First version")]}, {})):
            first.run("2026-09-11T10:00:00Z")
        self.assertEqual(first.created_events, [])

        second = ThematicWatcher(self.root, self.config, self.client, "https://pages.test")
        with patch.object(second, "_fetch_source", return_value=({"test:collection": [self.item("Second version")]}, {})):
            second.run("2026-09-11T12:00:00Z")
        self.assertEqual(len(second.created_events), 1)
        self.assertEqual(second.created_events[0].kind, "updated")
        feed = (self.root / "public/feeds/test-theme.xml").read_text(encoding="utf-8")
        self.assertIn("[UPDATED] [Test category] Test item", feed)
        self.assertIn("Full diff", feed)
        events = json.loads((self.root / "events/themes/test-theme.json").read_text(encoding="utf-8"))
        self.assertEqual(events[0]["source_name"], "Apple Test")

    def test_disappearance_is_tracked_without_an_event(self):
        first = ThematicWatcher(self.root, self.config, self.client, "https://pages.test")
        with patch.object(first, "_fetch_source", return_value=({"test:collection": [self.item("First version")]}, {})):
            first.run("2026-09-11T10:00:00Z")

        for hour in (12, 14):
            watcher = ThematicWatcher(self.root, self.config, self.client, "https://pages.test")
            with patch.object(watcher, "_fetch_source", return_value=({"test:collection": []}, {})):
                watcher.run(f"2026-09-11T{hour}:00:00Z")

        self.assertEqual(watcher.created_events, [])
        state = json.loads((self.root / "state/themes/test-theme.json").read_text(encoding="utf-8"))
        self.assertFalse(state["items"]["test:item"]["active"])
        events = json.loads((self.root / "events/themes/test-theme.json").read_text(encoding="utf-8"))
        self.assertEqual(events, [])
        feed = (self.root / "public/feeds/test-theme.xml").read_text(encoding="utf-8")
        self.assertNotIn("REMOVED", feed)


if __name__ == "__main__":
    unittest.main()
