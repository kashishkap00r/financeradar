"""Output helpers for audit artifacts."""

from __future__ import annotations

import json
import os


def ensure_parent_dir(path: str) -> None:
    """Ensure parent directory exists for target file path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)


def write_json(path: str, payload) -> None:
    """Write payload as pretty JSON."""
    ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def write_text(path: str, content: str) -> None:
    """Write plain text file."""
    ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

