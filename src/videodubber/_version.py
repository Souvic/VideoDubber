"""Single source of truth for the package version (see repo root VERSION)."""

from pathlib import Path

__version__ = (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
