#!/usr/bin/env python3
"""Source-tree entry point for the platform-neutral CLI."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from model_private_skill.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
