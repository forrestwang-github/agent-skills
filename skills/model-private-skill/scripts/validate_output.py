#!/usr/bin/env python3
"""Backward-compatible output validation wrapper."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from model_private_skill.output_validation import main, validate  # noqa: E402,F401


if __name__ == "__main__":
    main()
