#!/usr/bin/env python3
"""Apply a source-evidenced figure overlay to assembled trilingual JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OVERLAY_ORIGIN = "source_figure_manifest"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def apply_manifest(
    data: dict[str, Any],
    manifest: dict[str, Any],
    *,
    require_assets: bool = True,
) -> dict[str, Any]:
    paragraphs: dict[str, dict[str, Any]] = {}
    for chapter in data.get("chapters", []):
        for paragraph in chapter.get("paragraphs", []):
            paragraph_id = str(paragraph.get("id") or "")
            if not paragraph_id:
                continue
            if paragraph_id in paragraphs:
                raise ValueError(f"duplicate paragraph id: {paragraph_id}")
            paragraphs[paragraph_id] = paragraph

    figures = list(manifest.get("figures") or [])
    if int(manifest.get("figure_count") or 0) != len(figures):
        raise ValueError("figure manifest count does not match its rows")

    manifest_paths = {str(figure.get("path") or "") for figure in figures}
    for paragraph in paragraphs.values():
        retained = [
            figure
            for figure in paragraph.get("figures", [])
            if not (
                isinstance(figure, dict)
                and (
                    figure.get("origin") == OVERLAY_ORIGIN
                    or str(figure.get("path") or "") in manifest_paths
                )
            )
        ]
        if retained:
            paragraph["figures"] = retained
        else:
            paragraph.pop("figures", None)

    applied = 0
    for row in sorted(figures, key=lambda item: int(item.get("source_order") or 0)):
        paragraph_id = str(row.get("paragraph_id") or "")
        paragraph = paragraphs.get(paragraph_id)
        if paragraph is None:
            raise ValueError(f"figure targets unknown paragraph: {paragraph_id}")
        raw_path = str(row.get("path") or "").strip()
        if not raw_path:
            raise ValueError(f"figure for {paragraph_id} has no path")
        asset = Path(raw_path)
        if not asset.is_absolute():
            asset = ROOT / asset
        if require_assets and not asset.is_file():
            raise FileNotFoundError(asset)
        paragraph.setdefault("figures", []).append(
            {
                "path": raw_path,
                "caption": str(row.get("caption") or ""),
                "source_order": int(row.get("source_order") or 0),
                "source_page_index": int(row.get("source_page_index") or 0),
                "origin": OVERLAY_ORIGIN,
            }
        )
        paragraph["figures"].sort(
            key=lambda item: int(item.get("source_order") or 0)
            if isinstance(item, dict)
            else 0
        )
        applied += 1

    if applied != len(figures):
        raise RuntimeError(f"figure overlay incomplete: {applied}/{len(figures)}")
    data.setdefault("source", {})["figure_count"] = applied
    return data


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source = resolve(args.source)
    manifest_path = resolve(args.manifest)
    output = resolve(args.output) if args.output else source
    data = read_json(source)
    manifest = read_json(manifest_path)
    apply_manifest(data, manifest)
    data.setdefault("source", {})["figure_manifest"] = str(
        manifest_path.relative_to(ROOT)
    )
    write_json(output, data)
    print(
        json.dumps(
            {
                "output": str(output.relative_to(ROOT)),
                "figure_count": manifest["figure_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
