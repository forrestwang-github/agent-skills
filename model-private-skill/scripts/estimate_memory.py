#!/usr/bin/env python3
"""Backward-compatible memory CLI wrapper."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from model_private_skill.memory import main  # noqa: E402


if __name__ == "__main__":
    main()
