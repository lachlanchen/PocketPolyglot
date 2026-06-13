#!/usr/bin/env python3
"""Export completed language-set PDFs into sibling Nutstore folders."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGET_ROOT = Path.home() / "Nutstore Files" / "Projects" / "LinguaLeaf"
ARCHIVE = DEFAULT_TARGET_ROOT / "book-pdfs-20260525-083406"
REFERENCE_DOC = ROOT / "references" / "language-set-exports.md"


BOOK_SETS = {
    "jp-zh-trilingual-leftovers": {
        "label": "JP/ZH trilingual leftovers",
        "note": "Ordinary Japanese/Chinese paired editions that do not yet have English added.",
        "books": [
            ("chumon-no-ooi-ryoriten", "注文の多い料理店 / 要求太多的餐馆", ROOT / "build" / "chumon-no-ooi-ryoriten"),
            ("ginga-tetsudo", "銀河鉄道の夜 / 银河铁道之夜", ROOT / "build" / "ginga-tetsudo"),
            ("genji-modern", "源氏物語 / 源氏物语", ARCHIVE / "genji-modern"),
            ("izu-no-odori", "伊豆の踊子 / 伊豆的舞女", ARCHIVE / "izu-no-odori"),
            ("kinkakuji", "金閣寺 / 金阁寺", ARCHIVE / "kinkakuji"),
            ("kokoro", "こころ / 心", ARCHIVE / "kokoro"),
            ("no-longer-human", "人間失格 / 人间失格", ARCHIVE / "no-longer-human"),
            ("rashomon-stories", "羅生門短篇集 / 罗生门短篇集", ARCHIVE / "rashomon-stories"),
            ("sichuan-folk-stories-vol1", "中国民间故事集成 四川卷 上", ARCHIVE / "sichuan-folk-stories-vol1"),
            ("snow-country", "雪国", ARCHIVE / "snow-country"),
            ("the-old-capital", "古都", ARCHIVE / "the-old-capital"),
        ],
    },
    "wenyanwen-jp-zh-trilingual-leftovers": {
        "label": "Wenyanwen/JP/ZH trilingual leftovers",
        "note": "Classical Chinese-oriented editions that do not yet have English added; zh means modern Chinese helper/annotation.",
        "books": [
            ("sishu-jizhu", "四書章句集註", ARCHIVE / "sishu-jizhu"),
            ("sishu-jizhu-aginti", "四書章句集注 AgInTi edition", ARCHIVE / "sishu-jizhu-aginti"),
            ("shiji-aginti", "史記", ARCHIVE / "shiji-aginti-indented-20260525-091513"),
        ],
    },
}


def clean_name(text: str) -> str:
    return text.strip().replace("/", "／").replace("\\", "＼")


def discover_book_pdfs(book_id: str, title: str, source_root: Path) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if not source_root.exists():
        return items
    for pdf in sorted(source_root.rglob("*.pdf")):
        if pdf.name == "book.pdf":
            continue
        rel_parts = pdf.relative_to(source_root).parts
        direction = next((p for p in rel_parts if p in {"jp-main", "zh-main"}), "unknown-main")
        variant = next((p for p in rel_parts if p in {"color", "blackwhite"}), "unknown")
        if variant not in {"color", "blackwhite"}:
            continue
        items.append(
            {
                "book_id": book_id,
                "title": title,
                "direction": direction,
                "variant": variant,
                "source": str(pdf),
            }
        )
    return items


def clean_category(target: Path) -> None:
    for variant in ("color", "blackwhite"):
        variant_dir = target / variant
        if variant_dir.exists():
            for pdf in variant_dir.glob("*.pdf"):
                pdf.unlink()
    for name in ("README.md", "manifest.json"):
        path = target / name
        if path.exists():
            path.unlink()


def copy_category(category: str, config: dict[str, object], target_root: Path, no_clean: bool) -> dict[str, object]:
    target = target_root / category
    target.mkdir(parents=True, exist_ok=True)
    if not no_clean:
        clean_category(target)

    copied: list[dict[str, object]] = []
    used: dict[str, set[str]] = {"color": set(), "blackwhite": set()}
    missing: list[dict[str, str]] = []
    for book_id, title, source_root in config["books"]:  # type: ignore[index]
        found = discover_book_pdfs(book_id, title, Path(source_root))
        if not found:
            missing.append({"book_id": book_id, "title": title, "source_root": str(source_root)})
            continue
        for item in found:
            variant = item["variant"]
            variant_dir = target / variant
            variant_dir.mkdir(parents=True, exist_ok=True)
            source = Path(item["source"])
            filename = f"{clean_name(source.stem)}.pdf"
            if filename in used[variant]:
                filename = f"{clean_name(source.stem)} [{book_id} {item['direction']}].pdf"
            used[variant].add(filename)
            output = variant_dir / filename
            shutil.copy2(source, output)
            item = dict(item)
            item["output"] = str(output.relative_to(target))
            item["size_bytes"] = output.stat().st_size
            copied.append(item)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "label": config["label"],
        "note": config["note"],
        "target": str(target),
        "book_count": len({item["book_id"] for item in copied}),
        "pdf_count": len(copied),
        "variant_counts": {
            "color": sum(1 for item in copied if item["variant"] == "color"),
            "blackwhite": sum(1 for item in copied if item["variant"] == "blackwhite"),
        },
        "missing_books": missing,
        "items": copied,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_category_readme(target, manifest)
    return manifest


def write_category_readme(target: Path, manifest: dict[str, object]) -> None:
    lines = [
        f"# {manifest['label']}",
        "",
        str(manifest["note"]),
        "",
        f"Generated at: `{manifest['generated_at']}`",
        f"Books: `{manifest['book_count']}`",
        f"PDFs: `{manifest['pdf_count']}`",
        "",
        "Files are separated by variant:",
        "",
        "- `color/`",
        "- `blackwhite/`",
        "",
        "| Book | Direction | Variant | File |",
        "| --- | --- | --- | --- |",
    ]
    for item in manifest["items"]:  # type: ignore[index]
        lines.append(
            f"| `{item['book_id']}` | `{item['direction']}` | `{item['variant']}` | `{item['output']}` |"
        )
    if manifest["missing_books"]:  # type: ignore[index]
        lines.extend(["", "## Missing", "", "| Book | Source root |", "| --- | --- |"])
        for item in manifest["missing_books"]:  # type: ignore[index]
            lines.append(f"| `{item['book_id']}` | `{item['source_root']}` |")
    (target / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def trilingual_summary(target_root: Path) -> dict[str, object]:
    target = target_root / "en-main-jp-zh"
    manifest_path = target / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            "category": "en-main-jp-zh",
            "label": "EN/JP/ZH",
            "target": str(target),
            "book_count": len({item["book_id"] for item in manifest.get("items", [])}),
            "pdf_count": manifest.get("count", len(manifest.get("items", []))),
            "variant_counts": {
                "color": sum(1 for item in manifest.get("items", []) if item.get("variant") == "color"),
                "blackwhite": sum(1 for item in manifest.get("items", []) if item.get("variant") == "blackwhite"),
            },
            "note": "English main with indented Japanese and Chinese notes.",
        }
    pdfs = sorted(target.glob("*/*.pdf"))
    return {
        "category": "en-main-jp-zh",
        "label": "EN/JP/ZH",
        "target": str(target),
        "book_count": len(pdfs) // 2,
        "pdf_count": len(pdfs),
        "variant_counts": {
            "color": len(list((target / "color").glob("*.pdf"))),
            "blackwhite": len(list((target / "blackwhite").glob("*.pdf"))),
        },
        "note": "English main with indented Japanese and Chinese notes.",
    }


def write_reference_doc(summaries: list[dict[str, object]], target_root: Path) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Language Set Exports",
        "",
        f"Generated at: `{generated_at}`",
        f"Nutstore root: `{target_root}`",
        "",
        "| Set | Folder | Books | PDFs | Color | Black-white | Notes |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in summaries:
        variants = item["variant_counts"]  # type: ignore[index]
        lines.append(
            f"| {item['label']} | `{item['category']}` | {item['book_count']} | {item['pdf_count']} | "
            f"{variants['color']} | {variants['blackwhite']} | {item['note']} |"
        )
    lines.extend(["", "## Detail", ""])
    for item in summaries:
        manifest_path = Path(item["target"]) / "manifest.json"
        lines.append(f"### {item['label']}")
        lines.append("")
        lines.append(f"Folder: `{item['category']}`")
        lines.append("")
        if manifest_path.exists() and item["category"] != "en-main-jp-zh":
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            lines.extend(["| Book | Title | PDFs |", "| --- | --- | ---: |"])
            by_book: dict[str, dict[str, object]] = {}
            for entry in manifest.get("items", []):
                rec = by_book.setdefault(entry["book_id"], {"title": entry["title"], "count": 0})
                rec["count"] = int(rec["count"]) + 1
            for book_id, rec in sorted(by_book.items()):
                lines.append(f"| `{book_id}` | {rec['title']} | {rec['count']} |")
            if manifest.get("missing_books"):
                lines.extend(["", "Missing source/output:", ""])
                for missing in manifest["missing_books"]:
                    lines.append(f"- `{missing['book_id']}` from `{missing['source_root']}`")
        else:
            lines.append("See that folder's `manifest.json` for the full item list.")
        lines.append("")
    REFERENCE_DOC.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-root", type=Path, default=DEFAULT_TARGET_ROOT)
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args()

    target_root = args.target_root.expanduser().resolve()
    summaries = [trilingual_summary(target_root)]
    for category, config in BOOK_SETS.items():
        summaries.append(copy_category(category, config, target_root, args.no_clean))
    write_reference_doc(summaries, target_root)
    for item in summaries:
        variants = item["variant_counts"]  # type: ignore[index]
        print(
            f"{item['category']}: {item['book_count']} books, {item['pdf_count']} PDFs "
            f"({variants['color']} color, {variants['blackwhite']} blackwhite)"
        )
    print(f"wrote {REFERENCE_DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
