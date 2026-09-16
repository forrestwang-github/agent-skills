import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "skillctl.py"


class RegisterSyncTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "registry").mkdir()
        (self.root / "skills" / "work" / "sample-skill").mkdir(parents=True)
        (self.root / "LICENSE").write_text("license\n", encoding="utf-8")
        (self.root / "registry" / "repository.json").write_text(
            json.dumps({"license": "Apache-2.0"}), encoding="utf-8"
        )
        (self.root / "registry" / "catalog.json").write_text(
            json.dumps({"schema_version": 1, "repository": "example/skills", "skills": []}),
            encoding="utf-8",
        )
        (self.root / "README.md").write_text(
            "# Skills\n\n<!-- skill-catalog:start -->\nold\n<!-- skill-catalog:end -->\n",
            encoding="utf-8",
        )
        (self.root / "skills" / "work" / "sample-skill" / "SKILL.md").write_text(
            "---\nname: sample-skill\ndescription: A sample skill.\n---\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def run_skillctl(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo-root", str(self.root), "--json", *args],
            check=False, capture_output=True, text=True,
        )

    def test_register_then_sync_repairs_managed_files(self):
        preview = self.run_skillctl(
            "register", "sample-skill", "--category", "work", "--version", "1.2.3"
        )
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertTrue(json.loads(preview.stdout)["preview"])
        self.assertFalse((self.root / "skills" / "work" / "sample-skill" / "LICENSE").exists())

        applied = self.run_skillctl(
            "register", "sample-skill", "--category", "work", "--version", "1.2.3", "--yes"
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        catalog = json.loads((self.root / "registry" / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["skills"][0]["name"], "sample-skill")
        self.assertEqual(catalog["skills"][0]["version"], "1.2.3")
        self.assertEqual(
            (self.root / "skills" / "work" / "sample-skill" / "LICENSE").read_text(encoding="utf-8"),
            "license\n",
        )
        self.assertIn("A sample skill.", (self.root / "README.md").read_text(encoding="utf-8"))
        self.assertIn("未正式发布", (self.root / "README.md").read_text(encoding="utf-8"))
        self.assertIn("[查看 main](skills/work/sample-skill/)", (self.root / "README.md").read_text(encoding="utf-8"))

        (self.root / "skills" / "work" / "sample-skill" / "LICENSE").write_text("wrong\n", encoding="utf-8")
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        (self.root / "README.md").write_text(readme.replace("A sample skill.", "stale"), encoding="utf-8")

        sync_preview = self.run_skillctl("sync")
        self.assertEqual(sync_preview.returncode, 0, sync_preview.stderr)
        sync_plan = json.loads(sync_preview.stdout)
        self.assertEqual(sync_plan["license_updates"], ["sample-skill"])
        self.assertTrue(sync_plan["readme_update"])

        synced = self.run_skillctl("sync", "--yes")
        self.assertEqual(synced.returncode, 0, synced.stderr)
        verified = self.run_skillctl("verify", "--all")
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertIn("A sample skill.", (self.root / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
