import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "skillctl.py"
SPEC = importlib.util.spec_from_file_location("skillctl_module", SCRIPT)
SKILLCTL = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SKILLCTL)


class ReleaseAssetTests(unittest.TestCase):
    def test_catalog_groups_categories_and_places_manager_first(self):
        catalog = {
            "repository": "example/skills",
            "skills": [
                {"name": "helper", "path": "skills/tooling/helper", "version": "1.0.0", "release_tag": None, "description": "Helper."},
                {"name": "work-a", "path": "skills/work/work-a", "version": "1.0.0", "release_tag": None, "description": "Work A."},
                {"name": "skill-repository-manager", "path": "skills/tooling/skill-repository-manager", "version": "1.1.0", "release_tag": None, "description": "Manager."},
            ],
        }
        rendered = SKILLCTL.render_readme_catalog(catalog)
        self.assertLess(rendered.index("skill-repository-manager"), rendered.index("helper"))
        self.assertLess(rendered.index("helper"), rendered.index("work-a"))
        self.assertIn('<td rowspan="2">工具（tooling）</td>', rendered)

    def test_accepts_uploaded_zip_and_checksum(self):
        tag = "sample-skill-v1.2.3"
        assets = [
            {"name": f"{tag}.zip", "state": "uploaded", "url": "https://example/skill.zip"},
            {"name": f"{tag}.sha256", "state": "uploaded", "url": "https://example/skill.sha256"},
        ]
        result = SKILLCTL.validate_release_assets(tag, assets)
        self.assertEqual(set(result), {f"{tag}.zip", f"{tag}.sha256"})

    def test_rejects_incomplete_assets(self):
        tag = "sample-skill-v1.2.3"
        with self.assertRaises(SKILLCTL.SkillCtlError):
            SKILLCTL.validate_release_assets(
                tag,
                [{"name": f"{tag}.zip", "state": "uploaded", "url": "https://example/skill.zip"}],
            )


if __name__ == "__main__":
    unittest.main()
