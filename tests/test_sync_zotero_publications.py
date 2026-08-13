import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "sync_zotero_publications.py"
SPEC = importlib.util.spec_from_file_location("sync_zotero_publications", SCRIPT)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


FIXTURE = ROOT / "tests" / "fixtures" / "zotero-items.json"


class ZoteroNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = sync.load_source_items(FIXTURE)
        cls.records, cls.stats = sync.normalize_items(cls.items)
        cls.by_key = {record["key"]: record for record in cls.records}

    def test_configuration_loads(self):
        config = sync.load_config(ROOT / "config" / "publications.json")
        self.assertEqual(config["zotero_group_id"], 6637692)
        self.assertIsNone(config["collection_key"])
        self.assertEqual(sync.endpoint_for_config(config), "https://api.zotero.org/groups/6637692/items/top")

    def test_attachment_and_note_are_excluded(self):
        self.assertEqual(self.stats["excluded"], 2)
        self.assertEqual(self.stats["excluded_types"], {"attachment": 1, "note": 1})
        self.assertNotIn("ATTACHMENT1", self.by_key)
        self.assertNotIn("NOTE1", self.by_key)

    def test_title_is_required(self):
        self.assertEqual(self.stats["skipped"], {"missing-title": 1})
        self.assertNotIn("TITLELESS", self.by_key)

    def test_individual_creators_are_normalized(self):
        record = self.by_key["JOURNAL1"]
        self.assertEqual(record["creator_display"], "Ada Lovelace, Grace Hopper")
        self.assertEqual(record["creators"][0]["first_name"], "Ada")
        self.assertEqual(record["creators"][0]["creator_type"], "author")

    def test_institutional_creator_is_preserved(self):
        record = self.by_key["INSTITUTIONAL"]
        self.assertEqual(record["creators"][0]["name"], "GeoEpi Methods Consortium")
        self.assertEqual(record["creator_display"], "GeoEpi Methods Consortium")
        self.assertEqual(record["creators"][1]["creator_type"], "editor")

    def test_abstract_handling(self):
        self.assertEqual(self.by_key["JOURNAL1"]["abstract"], "This is a synthetic fixture abstract.")
        self.assertIsNone(self.by_key["NOABSTRACT"]["abstract"])

    def test_doi_and_links(self):
        record = self.by_key["JOURNAL1"]
        self.assertEqual(record["doi"], "10.1234/synthetic.2024.001")
        page = sync.generate_publications_page(sync.build_snapshot(self.records, {"zotero_group_id": 6637692, "collection_key": None}))
        self.assertIn("https://doi.org/10.1234/synthetic.2024.001", page)
        self.assertIsNone(self.by_key["NOABSTRACT"]["doi"])

    def test_year_handling(self):
        self.assertEqual(self.by_key["JOURNAL1"]["year"], 2024)
        self.assertIsNone(self.by_key["UNPARSEABLE"]["year"])

    def test_non_journal_item_type_is_preserved(self):
        self.assertEqual(self.by_key["BOOKSECTION"]["item_type"], "bookSection")
        self.assertEqual(self.by_key["INSTITUTIONAL"]["item_type"], "report")

    def test_formatted_reference_is_preserved(self):
        self.assertIn("Spatial patterns", self.by_key["JOURNAL1"]["formatted_reference"])

    def test_deterministic_sorting(self):
        titles = [record["title"] for record in self.records]
        self.assertEqual(titles[0], "Spatial patterns in a synthetic disease system")
        self.assertEqual(titles[-1], "Synthetic book with an undated record")


class ZoteroGenerationTests(unittest.TestCase):
    def setUp(self):
        items = sync.load_source_items(FIXTURE)
        records, _ = sync.normalize_items(items)
        self.config = {"zotero_group_id": 6637692, "collection_key": None}
        self.snapshot = sync.build_snapshot(records, self.config)

    def test_generated_page_contains_publication_and_abstract_only_when_available(self):
        page = sync.generate_publications_page(self.snapshot)
        self.assertIn("Spatial patterns in a synthetic disease system", page)
        self.assertIn("This is a synthetic fixture abstract.", page)
        self.assertNotIn("Abstract not available", page)
        no_abstract_start = page.index("A synthetic article without an abstract")
        no_abstract_end = page.index("</article>", no_abstract_start)
        self.assertNotIn("<details", page[no_abstract_start:no_abstract_end])

    def test_identical_input_produces_identical_snapshot(self):
        first = sync.snapshot_json(self.snapshot)
        second = sync.snapshot_json(self.snapshot)
        self.assertEqual(first, second)

    def test_failed_generation_leaves_existing_files_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data").mkdir()
            snapshot_path = root / "data" / "zotero-publications.json"
            page_path = root / "publications.qmd"
            snapshot_path.write_text("old snapshot\n", encoding="utf-8")
            page_path.write_text("old page\n", encoding="utf-8")
            with patch.object(sync, "generate_publications_page", side_effect=RuntimeError("generation failed")):
                with self.assertRaises(RuntimeError):
                    sync.replace_outputs(self.snapshot, root)
            self.assertEqual(snapshot_path.read_text(encoding="utf-8"), "old snapshot\n")
            self.assertEqual(page_path.read_text(encoding="utf-8"), "old page\n")

    def test_check_detects_stale_generated_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data").mkdir()
            (root / "data" / "zotero-publications.json").write_text(
                sync.snapshot_json(self.snapshot), encoding="utf-8"
            )
            (root / "publications.qmd").write_text("stale\n", encoding="utf-8")
            self.assertFalse(sync.outputs_match(self.snapshot, root))

    def test_pagination_link_is_parsed(self):
        headers = {"Link": '<https://api.zotero.org/next>; rel="next", <https://api.zotero.org/last>; rel="last"'}
        self.assertEqual(sync._next_link(headers), "https://api.zotero.org/next")

    def test_pagination_fetch_follows_next_link(self):
        pages = iter(
            [
                ([{"key": "one"}], "https://api.zotero.org/next"),
                ([{"key": "two"}], None),
            ]
        )
        config = {"zotero_group_id": 6637692, "collection_key": None, "citation_style": "apa", "locale": "en-US"}
        with patch.object(sync, "_fetch_page", side_effect=lambda url: next(pages)) as fetch:
            items, page_count = sync.fetch_all_items(config)
        self.assertEqual([item["key"] for item in items], ["one", "two"])
        self.assertEqual(page_count, 2)
        self.assertEqual(fetch.call_count, 2)


if __name__ == "__main__":
    unittest.main()
