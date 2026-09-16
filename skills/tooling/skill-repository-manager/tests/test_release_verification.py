import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "skillctl.py"
SPEC = importlib.util.spec_from_file_location("skillctl_module", SCRIPT)
SKILLCTL = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SKILLCTL)


class ReleaseAssetTests(unittest.TestCase):
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
