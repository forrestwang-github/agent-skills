from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_importer_validator import create_fixture


class CliTests(unittest.TestCase):
    def test_file_command_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            source = temp / "bill.xlsx"
            output = temp / "output"
            create_fixture(source)
            process = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "analyze_bill.py"),
                    "file",
                    "--input",
                    str(source),
                    "--from",
                    "2026-01",
                    "--to",
                    "2026-02",
                    "--customer",
                    "测试客户",
                    "--output-dir",
                    str(output),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
                check=False,
            )
            self.assertEqual(0, process.returncode, process.stderr)
            payload = json.loads(process.stdout.strip().splitlines()[-1])
            self.assertEqual("ok", payload["status"])
            self.assertTrue(Path(payload["report_path"]).exists())
            run_dir = Path(payload["run_dir"])
            self.assertTrue((run_dir / "manifest.json").exists())
            self.assertTrue((run_dir / "validation.json").exists())
            self.assertTrue((run_dir / "analysis-result.json").exists())


if __name__ == "__main__":
    unittest.main()
