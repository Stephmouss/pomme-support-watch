import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from apple_support_watch.http import HttpClient
from apple_support_watch.references import family, models, signature
from apple_support_watch.thematic import ThematicWatcher, _regulatory_item


class ReferenceFilterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = {"user_agent": "test", "request_timeout_seconds": 1,
            "removal_confirmations": 2, "feed_diff_line_limit": 20, "feed_item_limit": 150,
            "regulatory_reference_filter": True, "themes": [{"slug": "hardware", "title": "Hardware",
                "sources": [{"type": "regulatory_catalog", "url": "https://test"}]}]}

    def tearDown(self):
        self.temp.cleanup()

    def item(self, model="A3632", name="Smart Folio pour iPad mini", endpoint="device/regulatory_data", extra=None):
        return _regulatory_item(endpoint, "Environmental characteristics", {
            "id": model, "modelNames": [model], "productName": name,
            "yearOfRelease": 2026, **(extra or {}),
        })

    def run_watch(self, collections, day=1):
        watcher = ThematicWatcher(self.root, self.config, HttpClient("test", 1, 0), "https://pages.test")
        with patch.object(watcher, "_fetch_source", return_value=(collections, {})):
            watcher.run(f"2026-10-{day:02d}T10:00:00Z")
        return watcher

    def baseline(self):
        return self.run_watch({"regulatory:device/regulatory_data": [self.item("A2567")],
                               "regulatory:eLabels": [], "regulatory:compliance/declaration": []})

    def state(self):
        return json.loads((self.root / "state/themes/hardware.json").read_text())

    def test_extracts_explicit_models_only_and_groups_language_variants(self):
        self.assertEqual(models("Models: A3632, a3632, A2567 · Release year: 2026"), ["A2567", "A3632"])
        self.assertEqual(models("Document filename contains A3632"), [])
        self.assertEqual(signature("Smart Folio pour iPad mini"), signature("Smart Folio for iPad mini"))
        self.assertEqual(family("Smart Folio for iPad mini (8th generation)"), "Smart Folio pour iPad mini")

    def test_baseline_is_silent_and_new_model_is_reported_once_across_sections(self):
        self.assertEqual(self.baseline().created_events, [])
        new = self.item()
        watcher = self.run_watch({"regulatory:device/regulatory_data": [self.item("A2567"), new],
                                 "regulatory:eLabels": [self.item(endpoint="eLabels")]}, day=2)
        self.assertEqual(len(watcher.created_events), 1)
        event = watcher.created_events[0]
        self.assertEqual(event.editorial_type, "new_reference")
        self.assertEqual(event.reference_models, ["A3632"])
        self.assertIn("pas qu’un produit est non annoncé", event.reference_context)
        feed = (self.root / "public/feeds/hardware.xml").read_text()
        self.assertIn("[NOUVELLE REF] Smart Folio pour iPad mini — A3632", feed)
        self.assertEqual(self.state()["reference_filter"]["totals"]["new_references"], 1)
        # A later section listing does not re-alert for the same hardware.
        later = self.run_watch({"regulatory:compliance/declaration": [self.item(endpoint="compliance/declaration")]}, day=3)
        self.assertEqual(later.created_events, [])
        self.assertTrue((self.root / "public/references/index.html").exists())

    def test_migration_uses_all_old_models_without_replaying_them(self):
        self.baseline()
        path = self.root / "state/themes/hardware.json"
        state = self.state()
        state.pop("reference_filter")  # Simulate the deployed pre-filter state.
        path.write_text(json.dumps(state))
        watcher = self.run_watch({"regulatory:device/regulatory_data": [self.item("A2567")],
                                 "regulatory:eLabels": [self.item("A2567", endpoint="eLabels")]}, day=2)
        self.assertFalse(any(e.editorial_type for e in watcher.created_events))
        self.assertEqual(self.state()["reference_filter"]["models"]["A2567"]["first_seen"], "2026-10-01T10:00:00Z")

    def test_known_model_actual_document_update_is_preserved(self):
        self.baseline()
        watcher = self.run_watch({"regulatory:device/regulatory_data": [self.item("A2567", extra={"battery": "changed"})]}, day=2)
        self.assertEqual(len(watcher.created_events), 1)
        self.assertEqual(watcher.created_events[0].kind, "updated")
        self.assertEqual(watcher.created_events[0].editorial_type, "")

    def test_name_change_is_highlighted_but_translation_is_not(self):
        self.baseline()
        translated = self.run_watch({"regulatory:device/regulatory_data": [self.item("A2567", "Smart Folio for iPad mini")]}, day=2)
        self.assertEqual(translated.created_events[0].editorial_type, "")
        renamed = self.run_watch({"regulatory:device/regulatory_data": [self.item("A2567", "Smart Folio for iPad mini (8th gen)")]}, day=3)
        self.assertEqual(renamed.created_events[0].editorial_type, "identity_change")
        self.assertIn("Nom du produit modifié", renamed.created_events[0].reference_context)

    def test_uninitialized_collection_is_a_baseline_not_a_new_model(self):
        self.baseline()
        watcher = self.run_watch({"regulatory:reach": [self.item(endpoint="reach")]}, day=2)
        self.assertEqual(watcher.created_events, [])
        self.assertIn("A3632", self.state()["reference_filter"]["models"])

    def test_new_section_does_not_steal_the_primary_new_reference(self):
        self.baseline()
        # The preferred category is new, but an already-monitored category also sees the model.
        state = self.state()
        state["initialized_collections"].pop("regulatory:device/regulatory_data")
        (self.root / "state/themes/hardware.json").write_text(json.dumps(state))
        watcher = self.run_watch({"regulatory:device/regulatory_data": [self.item()],
                                 "regulatory:eLabels": [self.item(endpoint="eLabels")]}, day=2)
        self.assertEqual(len(watcher.created_events), 1)
        self.assertEqual(watcher.created_events[0].editorial_type, "new_reference")

    def test_archive_survives_rss_retention_and_escapes_names(self):
        self.baseline()
        self.config["feed_item_limit"] = 1
        self.run_watch({"regulatory:device/regulatory_data": [self.item(name="Smart Folio <script>bad</script> pour iPad mini")]}, day=2)
        self.run_watch({"regulatory:device/regulatory_data": [self.item("A3633", "Another accessory")]}, day=3)
        feed = ET.parse(self.root / "public/feeds/hardware.xml")
        self.assertEqual(len(feed.findall("./channel/item")), 1)
        archive = (self.root / "public/references/index.html").read_text()
        self.assertIn("A3632", archive)
        self.assertNotIn("<script>", archive)
        self.assertEqual(len(self.state()["reference_filter"]["alerts"]), 2)

    def test_filter_can_be_disabled_without_changing_collection(self):
        self.baseline()
        self.config["regulatory_reference_filter"] = False
        watcher = self.run_watch({"regulatory:device/regulatory_data": [self.item()]}, day=2)
        self.assertEqual(watcher.created_events[0].editorial_type, "")
        self.assertEqual(watcher.created_events[0].kind, "new")
