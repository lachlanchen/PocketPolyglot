#!/usr/bin/env python3
"""Shared Nutstore path defaults for LinguaLeaf exports."""

from __future__ import annotations

import os
from pathlib import Path
import re


def _nutstore_root() -> Path:
    raw = os.environ.get("NUTSTORE_ROOT")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / "Nutstore Files"


def _first_existing_or_default(candidates: list[Path], default: Path) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return default


def lingualeaf_project_root() -> Path:
    """Return the preferred Nutstore NoSync Projects/LinguaLeaf root.

    Project PDFs are intentionally large. Keep the private project export under
    Nutstore NoSync and do not fall back to the synced Projects/LinguaLeaf path.
    Public flat exports still use :func:`lingualeaf_share_root`.
    """

    raw = os.environ.get("LINGUALEAF_NUTSTORE_PROJECT") or os.environ.get("LINGUALEAF_PROJECT_ROOT")
    if raw:
        return Path(raw).expanduser()
    root = _nutstore_root()
    candidates = [
        root / "NoSync" / "Projects" / "LinguaLeaf",
        root / "NOSync" / "Projects" / "LinguaLeaf",
        root / "No Sync" / "Projects" / "LinguaLeaf",
    ]
    return _first_existing_or_default(candidates, root / "NoSync" / "Projects" / "LinguaLeaf")


def lingualeaf_share_root() -> Path:
    raw = os.environ.get("LINGUALEAF_NUTSTORE_SHARE") or os.environ.get("LINGUALEAF_SHARE_ROOT")
    if raw:
        return Path(raw).expanduser()
    root = _nutstore_root()
    return _first_existing_or_default(
        [root / "Share" / "LinguaLeaf"],
        root / "Share" / "LinguaLeaf",
    )


_SERVER_UNSAFE_FILENAME_CHARS = str.maketrans(
    {
        "<": "＜",
        ">": "＞",
        ":": "：",
        '"': "＂",
        "/": "／",
        "\\": "／",
        "|": "｜",
        "?": "？",
        "*": "＊",
    }
)


def nutstore_safe_filename(name: str) -> str:
    """Return a filename accepted by Nutstore's upstream server.

    Nutstore accepts local files with Windows/server-unsafe characters such as
    ASCII ``:`` but then rejects them during upload with ``NotAcceptableByServer``.
    Keep the title readable by using fullwidth replacements instead of dropping
    information.
    """

    safe = name.translate(_SERVER_UNSAFE_FILENAME_CHARS)
    safe = re.sub(r"[\x00-\x1f\x7f]", "", safe)
    safe = re.sub(r"\s+", " ", safe).strip()
    if "." in safe:
        stem, suffix = safe.rsplit(".", 1)
        safe = f"{stem.rstrip(' .')}.{suffix}"
    else:
        safe = safe.rstrip(" .")
    return safe or "untitled"
