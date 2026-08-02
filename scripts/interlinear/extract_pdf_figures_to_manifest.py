#!/usr/bin/env python3
"""Extract source-page PDF images and build an evidence-checked figure manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compact(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text))
    return " ".join(normalized.split())


def paragraph_index(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for chapter in data.get("chapters", []):
        for paragraph in chapter.get("paragraphs", []):
            paragraph_id = str(paragraph.get("id") or "")
            if not paragraph_id:
                continue
            if paragraph_id in index:
                raise ValueError(f"duplicate paragraph id: {paragraph_id}")
            index[paragraph_id] = paragraph
    return index


def chunk_index(chunks_jsonl: Path) -> dict[str, str]:
    index: dict[str, str] = {}
    with chunks_jsonl.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            chunk = json.loads(raw_line)
            chunk_id = str(chunk.get("chunk_id") or "")
            for paragraph in chunk.get("paragraphs", []):
                paragraph_id = str(paragraph.get("id") or "")
                if not paragraph_id:
                    continue
                if paragraph_id in index:
                    raise ValueError(
                        f"duplicate paragraph id in {chunks_jsonl}:{line_number}: "
                        f"{paragraph_id}"
                    )
                index[paragraph_id] = chunk_id
    return index


def extract_single_page_image(pdf: Path, page: int, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"pdf-figure-p{page:04d}-") as raw_tmp:
        temporary = Path(raw_tmp)
        prefix = temporary / "image"
        subprocess.run(
            [
                "pdfimages",
                "-f",
                str(page),
                "-l",
                str(page),
                "-j",
                str(pdf),
                str(prefix),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        candidates = sorted(
            path
            for path in temporary.iterdir()
            if path.is_file() and path.stat().st_size > 0
        )
        if len(candidates) != 1:
            raise RuntimeError(
                f"expected one embedded image on PDF page {page}, found "
                f"{len(candidates)}: {[path.name for path in candidates]}"
            )
        extracted = candidates[0]
        output = destination.with_suffix(extracted.suffix.lower())
        for existing in destination.parent.glob(destination.stem + ".*"):
            existing.unlink()
        shutil.copy2(extracted, output)
        return output


def build_manifest(config_path: Path) -> Path:
    config = read_json(config_path)
    source_pdf = resolve(config["source_pdf"])
    assembled_json = resolve(config["assembled_json"])
    chunks_jsonl = resolve(config["chunks_jsonl"])
    output_dir = resolve(config["output_dir"])
    output_manifest = resolve(config["output_manifest"])

    for required in (source_pdf, assembled_json, chunks_jsonl):
        if not required.is_file():
            raise FileNotFoundError(required)

    expected_pdf_sha = str(config.get("source_pdf_sha256") or "")
    actual_pdf_sha = sha256(source_pdf)
    if expected_pdf_sha and expected_pdf_sha != actual_pdf_sha:
        raise RuntimeError(
            f"source PDF checksum mismatch: expected={expected_pdf_sha} "
            f"actual={actual_pdf_sha}"
        )

    paragraphs = paragraph_index(read_json(assembled_json))
    chunks = chunk_index(chunks_jsonl)
    rows = list(config.get("figures") or [])
    if not rows:
        raise ValueError("figure configuration is empty")

    seen_pages: set[int] = set()
    seen_orders: set[int] = set()
    figures: list[dict[str, Any]] = []
    for row in rows:
        source_order = int(row["source_order"])
        source_page = int(row["source_page_index"])
        paragraph_id = str(row["paragraph_id"])
        caption = str(row.get("caption") or "").strip()
        anchor = compact(str(row.get("anchor_phrase") or ""))
        if source_order in seen_orders:
            raise ValueError(f"duplicate source order: {source_order}")
        if source_page in seen_pages:
            raise ValueError(f"duplicate source PDF page: {source_page}")
        seen_orders.add(source_order)
        seen_pages.add(source_page)

        paragraph = paragraphs.get(paragraph_id)
        if paragraph is None:
            raise ValueError(f"unknown paragraph id: {paragraph_id}")
        source_text = compact(str(paragraph.get("source_en") or ""))
        if not anchor or anchor not in source_text:
            raise ValueError(
                f"source anchor does not match {paragraph_id}: {anchor!r}"
            )
        chunk_id = chunks.get(paragraph_id)
        if not chunk_id:
            raise ValueError(f"paragraph has no source chunk: {paragraph_id}")

        basename = str(row.get("filename") or f"map-{source_order:02d}")
        extracted = extract_single_page_image(
            source_pdf,
            source_page,
            output_dir / Path(basename).stem,
        )
        figures.append(
            {
                "source_order": source_order,
                "source_page_index": source_page,
                "chunk_id": chunk_id,
                "paragraph_id": paragraph_id,
                "path": relative(extracted),
                "caption": caption,
                "image_sha256": sha256(extracted),
                "source_evidence": {
                    "pdf": relative(source_pdf),
                    "pdf_sha256": actual_pdf_sha,
                    "page": source_page,
                    "anchor_phrase": str(row["anchor_phrase"]),
                },
            }
        )

    figures.sort(key=lambda item: int(item["source_order"]))
    expected_orders = list(range(1, len(figures) + 1))
    actual_orders = [int(item["source_order"]) for item in figures]
    if actual_orders != expected_orders:
        raise ValueError(
            f"source orders must be contiguous: expected={expected_orders} "
            f"actual={actual_orders}"
        )

    write_json(
        output_manifest,
        {
            "schema_version": 1,
            "book_id": config["book_id"],
            "source_book_id": config["source_book_id"],
            "source_pdf": relative(source_pdf),
            "source_pdf_sha256": actual_pdf_sha,
            "figure_count": len(figures),
            "figures": figures,
        },
    )
    return output_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    config = args.config if args.config.is_absolute() else ROOT / args.config
    manifest = build_manifest(config)
    payload = read_json(manifest)
    print(
        json.dumps(
            {
                "manifest": relative(manifest),
                "figure_count": payload["figure_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
