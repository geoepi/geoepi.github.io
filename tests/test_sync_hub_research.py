import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "sync_hub_research.py"
SPEC = importlib.util.spec_from_file_location("sync_hub_research", SCRIPT)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


FIXTURE = Path(__file__).parent / "fixtures" / "public-research.json"


def fixture_feed():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class FeedValidationTests(unittest.TestCase):
    def test_valid_feed_accepted(self):
        self.assertEqual(sync.validate_feed(fixture_feed()), [])

    def test_unsupported_schema_rejected(self):
        feed = fixture_feed()
        feed["schema_version"] = 2
        self.assertTrue(any("schema_version" in error for error in sync.validate_feed(feed)))

    def test_malformed_feed_rejected(self):
        feed = fixture_feed()
        del feed["projects"][0]["hub_url"]
        self.assertTrue(any("hub_url" in error for error in sync.validate_feed(feed)))

    def test_operational_fields_rejected(self):
        feed = fixture_feed()
        feed["projects"][0]["current_focus"] = "private"
        self.assertTrue(any("operational field" in error for error in sync.validate_feed(feed)))

    def test_missing_repository_visibility_rejected(self):
        feed = fixture_feed()
        del feed["projects"][0]["subprojects"][0]["repository_visibility"]
        self.assertTrue(
            any("repository_visibility" in error for error in sync.validate_feed(feed))
        )

    def test_invalid_repository_visibility_rejected(self):
        feed = fixture_feed()
        feed["projects"][0]["subprojects"][0]["repository_visibility"] = "unknown"
        self.assertTrue(
            any("repository_visibility" in error for error in sync.validate_feed(feed))
        )


class GenerationTests(unittest.TestCase):
    def test_project_order_is_deterministic(self):
        feed = fixture_feed()
        feed["projects"] = list(reversed(feed["projects"]))
        snapshot = sync.snapshot_json(feed)
        self.assertLess(snapshot.index('"alpha-project"'), snapshot.index('"scaffold-project"'))

    def test_subproject_order_is_deterministic(self):
        feed = fixture_feed()
        snapshot = sync.snapshot_json(feed)
        self.assertLess(snapshot.index('"alpha-one"'), snapshot.index('"alpha-two"'))

    def test_scaffold_content_status_is_preserved_without_public_indicator(self):
        page = sync.generate_project_page(fixture_feed()["projects"][1])
        self.assertIn("content_status: scaffold", page)
        self.assertNotIn("Scaffold project summary", page)
        self.assertNotIn("pending project-level review", page)

    def test_reviewed_project_has_no_scaffold_indicator(self):
        page = sync.generate_project_page(fixture_feed()["projects"][0])
        self.assertNotIn("Scaffold project summary", page)
        self.assertNotIn("pending project-level review", page)

    def test_themes_become_categories(self):
        page = sync.generate_project_page(fixture_feed()["projects"][0])
        self.assertIn('categories: ["geography", "modeling"]', page)

    def test_subprojects_are_generated_without_operational_fields(self):
        page = sync.generate_project_page(fixture_feed()["projects"][0])
        self.assertIn("Alpha first analysis", page)
        self.assertIn("<h3>Alpha first analysis</h3>", page)
        self.assertIn("https://github.com/geoepi/alpha-one", page)
        self.assertNotIn("current_focus", page)
        self.assertNotIn("milestone", page)
        self.assertNotIn("compute", page)

    def test_public_repository_name_and_direct_link_render(self):
        project = fixture_feed()["projects"][0]
        project["subprojects"] = [project["subprojects"][1]]
        page = sync.generate_project_page(project)
        self.assertIn("geoepi/alpha-one", page)
        self.assertIn('href="https://github.com/geoepi/alpha-one"', page)
        self.assertNotIn("Access currently restricted", page)
        self.assertNotIn("repository-access.html", page)

    def test_private_repository_is_restricted_without_direct_link(self):
        page = sync.generate_project_page(fixture_feed()["projects"][0])
        self.assertIn("geoepi/alpha-two", page)
        self.assertIn("Access currently restricted", page)
        self.assertIn("../../repository-access.html", page)
        self.assertNotIn('href="https://github.com/geoepi/alpha-two"', page)

    def test_internal_repository_uses_restricted_behavior(self):
        feed = fixture_feed()
        feed["projects"][0]["subprojects"][1]["repository_visibility"] = "internal"
        page = sync.generate_project_page(feed["projects"][0])
        self.assertIn("geoepi/alpha-two", page)
        self.assertIn("Access currently restricted", page)
        self.assertNotIn('href="https://github.com/geoepi/alpha-two"', page)

    def test_visibility_transition_switches_rendered_behavior(self):
        feed = fixture_feed()
        project = feed["projects"][0]
        project["subprojects"] = [project["subprojects"][0]]
        private_page = sync.generate_project_page(project)
        project["subprojects"][0]["repository_visibility"] = "public"
        public_page = sync.generate_project_page(project)
        self.assertIn("Access currently restricted", private_page)
        self.assertNotIn("Access currently restricted", public_page)
        self.assertIn('href="https://github.com/geoepi/alpha-two"', public_page)

    def test_repository_access_page_is_in_render_configuration(self):
        quarto = (Path(__file__).parents[1] / "_quarto.yml").read_text(encoding="utf-8")
        self.assertIn("repository-access.qmd", quarto)

    def test_no_image_and_no_links_render_cleanly(self):
        page = sync.generate_project_page(fixture_feed()["projects"][1])
        self.assertNotIn("image:", page)
        self.assertNotIn("## Public links", page)

    def test_sync_writes_all_projects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sync.replace_generated_sources(fixture_feed(), root)
            self.assertTrue((root / "data/hub-public-research.json").exists())
            self.assertEqual(
                sorted(path.name for path in (root / "research").iterdir()),
                ["alpha-project", "scaffold-project"],
            )
            self.assertTrue(sync.outputs_match(fixture_feed(), root))

    def test_stale_generated_project_removed_after_successful_sync(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "research/old-project").mkdir(parents=True)
            (root / "research/old-project/index.qmd").write_text("old", encoding="utf-8")
            sync.replace_generated_sources(fixture_feed(), root)
            self.assertFalse((root / "research/old-project").exists())

    def test_failed_validation_leaves_previous_output_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sync.replace_generated_sources(fixture_feed(), root)
            before = (root / "data/hub-public-research.json").read_bytes()
            invalid = fixture_feed()
            invalid["projects"][0]["content_status"] = "invalid"
            with self.assertRaises(ValueError):
                errors = sync.validate_feed(invalid)
                if errors:
                    raise ValueError(errors)
                sync.replace_generated_sources(invalid, root)
            self.assertEqual(before, (root / "data/hub-public-research.json").read_bytes())

    def test_identical_input_produces_identical_output(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            feed = fixture_feed()
            sync.replace_generated_sources(feed, first)
            sync.replace_generated_sources(feed, second)
            first_files = sorted(path.relative_to(first) for path in Path(first).rglob("*"))
            second_files = sorted(path.relative_to(second) for path in Path(second).rglob("*"))
            self.assertEqual(first_files, second_files)
            for relative in first_files:
                if (Path(first) / relative).is_file():
                    self.assertEqual(
                        (Path(first) / relative).read_bytes(),
                        (Path(second) / relative).read_bytes(),
                    )


if __name__ == "__main__":
    unittest.main()
