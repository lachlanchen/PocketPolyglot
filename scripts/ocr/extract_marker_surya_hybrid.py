#!/usr/bin/env python3
"""Build page-aware Markdown from Marker layout and Surya OCR text.

Marker is used for block order and figure regions. Surya is used for the text
inside those blocks because it often recovers diacritics and word boundaries
that are missing from an embedded PDF text layer. Raw extractor outputs remain
immutable caches; this script writes a separate merged Markdown artifact and a
machine-readable validation report.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import shutil
import subprocess
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

try:
    from wordfreq import zipf_frequency
except Exception:  # pragma: no cover - optional quality dependency
    zipf_frequency = None


ROOT = Path(__file__).resolve().parents[2]
TEXT_BLOCK_TYPES = {
    "Text",
    "SectionHeader",
    "Caption",
    "Footnote",
    "ListItem",
    "Table",
    "Form",
    "Equation",
}
IGNORED_BLOCK_TYPES = {"PageHeader", "PageFooter"}
KEEP_LINEBREAK_HYPHENS = {
    "as-yet",
    "blossom-viewing",
    "far-reaching",
    "full-time",
    "long-term",
    "part-time",
    "self-conscious",
    "self-contained",
    "well-known",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_logged(command: list[str], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    if process.returncode:
        raise RuntimeError(
            f"command failed with exit code {process.returncode}: {' '.join(command)}; "
            f"see {log_path}"
        )


def archive_existing(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = path.with_name(f"{path.name}.archive-{stamp}")
    counter = 1
    while destination.exists():
        destination = path.with_name(f"{path.name}.archive-{stamp}-{counter}")
        counter += 1
    path.rename(destination)


def find_marker_json(root: Path) -> Path:
    candidates = sorted(
        path
        for path in root.rglob("*.json")
        if not path.name.endswith("_meta.json") and path.name != "status.json"
    )
    if len(candidates) != 1:
        raise RuntimeError(f"expected one Marker JSON under {root}, found {len(candidates)}")
    return candidates[0]


def find_surya_json(root: Path) -> Path:
    candidates = sorted(root.rglob("results.json"))
    if len(candidates) != 1:
        raise RuntimeError(f"expected one Surya results.json under {root}, found {len(candidates)}")
    return candidates[0]


def strip_html(value: str) -> str:
    source = html.unescape(value or "")
    source = re.sub(r"<sup\b[^>]*>(.*?)</sup>", r"[\1]", source, flags=re.I | re.S)
    soup = BeautifulSoup(source, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\s+([’'](?:s|t|re|ve|ll|d|m)\b)", r"\1", text, flags=re.I)
    text = re.sub(r"\s+([’'])(?=\s)", r"\1", text)
    return text


def bbox(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def polygon_bbox(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or not value:
        return None
    try:
        xs = [float(point[0]) for point in value]
        ys = [float(point[1]) for point in value]
    except (IndexError, TypeError, ValueError):
        return None
    return min(xs), min(ys), max(xs), max(ys)


def overlap_fraction(
    line_box: tuple[float, float, float, float],
    block_box: tuple[float, float, float, float],
) -> float:
    lx0, ly0, lx1, ly1 = line_box
    bx0, by0, bx1, by1 = block_box
    width = max(0.0, min(lx1, bx1) - max(lx0, bx0))
    height = max(0.0, min(ly1, by1) - max(ly0, by0))
    area = max((lx1 - lx0) * (ly1 - ly0), 1.0)
    return width * height / area


def scale_surya_lines(
    page: dict[str, Any],
    marker_page_box: tuple[float, float, float, float],
) -> list[dict[str, Any]]:
    image_box = bbox(page.get("image_bbox"))
    if image_box is None:
        raise RuntimeError("Surya page is missing image_bbox")
    _, _, image_width, image_height = image_box
    mx0, my0, mx1, my1 = marker_page_box
    marker_width = mx1 - mx0
    marker_height = my1 - my0
    lines: list[dict[str, Any]] = []
    for order, item in enumerate(page.get("text_lines", [])):
        line_box = polygon_bbox(item.get("polygon"))
        text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if line_box is None or not text:
            continue
        x0, y0, x1, y1 = line_box
        lines.append(
            {
                "order": order,
                "text": text,
                "confidence": float(item.get("confidence") or 0.0),
                "bbox": (
                    mx0 + x0 / image_width * marker_width,
                    my0 + y0 / image_height * marker_height,
                    mx0 + x1 / image_width * marker_width,
                    my0 + y1 / image_height * marker_height,
                ),
            }
        )
    return lines


def join_ocr_lines(lines: list[str]) -> str:
    text = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not text:
            text = line
        elif text.endswith("-"):
            left_match = re.search(r"([^\W_]+)-$", text, re.UNICODE)
            right_match = re.match(r"([^\W_]+)", line, re.UNICODE)
            if left_match and right_match and right_match.group(1)[0].islower():
                joined = left_match.group(1) + right_match.group(1)
                hyphenated = (left_match.group(1) + "-" + right_match.group(1)).casefold()
                if hyphenated not in KEEP_LINEBREAK_HYPHENS:
                    text = text[:-1] + line
                else:
                    text += line
            else:
                text += line
        else:
            text += " " + line
    return re.sub(r"\s+", " ", text).strip()


WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def normalized_word(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    # A common broken font map emits the long-o glyph as the digit 6.
    without_marks = re.sub(r"(?<=[a-z])6(?=[a-z]|$)", "o", without_marks)
    return re.sub(r"[^a-z0-9]+", "", without_marks)


def has_diacritic(value: str) -> bool:
    return any(unicodedata.combining(char) for char in unicodedata.normalize("NFD", value))


def choose_fused_word(marker_word: str, surya_word: str) -> str:
    marker_normalized = normalized_word(marker_word)
    surya_normalized = normalized_word(surya_word)
    if not marker_normalized or not surya_normalized:
        return marker_word
    if marker_normalized == surya_normalized:
        marker_has_embedded_digit = bool(
            re.search(r"(?<=[A-Za-z])\d(?=[A-Za-z]|$)", marker_word)
        )
        if marker_has_embedded_digit and not any(char.isdigit() for char in surya_word):
            return surya_word
        if has_diacritic(surya_word) and not has_diacritic(marker_word):
            return surya_word
        return marker_word
    if "�" in marker_word and "�" not in surya_word:
        return surya_word
    if (
        marker_word.startswith("l")
        and surya_word.startswith("I")
        and normalized_word(marker_word[1:]) == normalized_word(surya_word[1:])
    ):
        return surya_word
    if "rn" in marker_normalized and marker_normalized.replace("rn", "m") == surya_normalized:
        return surya_word
    if zipf_frequency and marker_word.isalpha() and surya_word.isalpha():
        marker_frequency = zipf_frequency(marker_word.casefold(), "en")
        surya_frequency = zipf_frequency(surya_word.casefold(), "en")
        if surya_frequency >= marker_frequency + 0.6:
            return surya_word
    # Marker has already joined print-line hyphenation and is the safer source
    # for ordinary words and names when the two recognizers genuinely differ.
    return marker_word


def join_marker_splits_proven_by_surya(marker_text: str, surya_text: str) -> str:
    """Join split Marker words only when one Surya token proves the join."""

    surya_by_key: dict[str, str] = {}
    for match in WORD_RE.finditer(surya_text):
        key = normalized_word(match.group(0))
        if key:
            surya_by_key.setdefault(key, match.group(0))
    marker_matches = list(WORD_RE.finditer(marker_text))
    replacements: list[tuple[int, int, str]] = []
    index = 0
    while index + 1 < len(marker_matches):
        first = marker_matches[index]
        second = marker_matches[index + 1]
        gap = marker_text[first.end() : second.start()]
        if gap.isspace():
            combined = first.group(0) + second.group(0)
            key = normalized_word(combined)
            surya_word = surya_by_key.get(key)
            if surya_word:
                replacement = choose_fused_word(combined, surya_word)
                replacements.append((first.start(), second.end(), replacement))
                index += 2
                continue
        index += 1
    for start, end, replacement in reversed(replacements):
        marker_text = marker_text[:start] + replacement + marker_text[end:]
    return marker_text


def fuse_marker_surya_text(marker_text: str, surya_text: str) -> str:
    """Preserve Marker prose and borrow only evidenced Surya repairs."""

    surya_text = strip_html(surya_text)
    if "�" in marker_text and "�" not in surya_text:
        return surya_text
    marker_text = join_marker_splits_proven_by_surya(marker_text, surya_text)
    marker_matches = list(WORD_RE.finditer(marker_text))
    surya_matches = list(WORD_RE.finditer(surya_text))
    if not marker_matches:
        return surya_text
    if not surya_matches:
        return marker_text
    marker_words = [match.group(0) for match in marker_matches]
    surya_words = [match.group(0) for match in surya_matches]
    marker_keys = [normalized_word(word) for word in marker_words]
    surya_keys = [normalized_word(word) for word in surya_words]
    replacements: dict[int, str] = {}
    aligned: dict[int, int] = {}
    span_replacements: list[tuple[int, int, str]] = []
    matcher = SequenceMatcher(a=marker_keys, b=surya_keys, autojunk=False)
    for tag, marker_start, marker_end, surya_start, surya_end in matcher.get_opcodes():
        marker_count = marker_end - marker_start
        surya_count = surya_end - surya_start
        if tag == "equal":
            for offset in range(marker_count):
                marker_index = marker_start + offset
                surya_index = surya_start + offset
                aligned[marker_index] = surya_index
                replacements[marker_index] = choose_fused_word(
                    marker_words[marker_start + offset],
                    surya_words[surya_start + offset],
                )
            continue
        if marker_count == 1 and surya_count == 2:
            marker_word = marker_words[marker_start]
            surya_pair = surya_words[surya_start:surya_end]
            if normalized_word(marker_word) == normalized_word("".join(surya_pair)):
                span_replacements.append(
                    (
                        marker_matches[marker_start].start(),
                        marker_matches[marker_start].end(),
                        surya_text[
                            surya_matches[surya_start].start() :
                            surya_matches[surya_end - 1].end()
                        ],
                    )
                )
            continue
        if marker_count != surya_count:
            continue
        for offset in range(marker_count):
            marker_word = marker_words[marker_start + offset]
            surya_word = surya_words[surya_start + offset]
            marker_index = marker_start + offset
            surya_index = surya_start + offset
            aligned[marker_index] = surya_index
            if marker_word.isdigit() and surya_word.isdigit():
                replacements[marker_index] = marker_word
                continue
            similarity = SequenceMatcher(
                a=normalized_word(marker_word),
                b=normalized_word(surya_word),
                autojunk=False,
            ).ratio()
            if similarity >= 0.75:
                replacements[marker_index] = choose_fused_word(marker_word, surya_word)

    for marker_index in range(len(marker_matches) - 1):
        next_marker_index = marker_index + 1
        surya_index = aligned.get(marker_index)
        next_surya_index = aligned.get(next_marker_index)
        if surya_index is None or next_surya_index != surya_index + 1:
            continue
        marker_gap_start = marker_matches[marker_index].end()
        marker_gap_end = marker_matches[next_marker_index].start()
        marker_gap = marker_text[marker_gap_start:marker_gap_end]
        surya_gap = surya_text[
            surya_matches[surya_index].end() : surya_matches[next_surya_index].start()
        ]
        if (
            re.fullmatch(r"-\s+", marker_gap)
            and re.fullmatch(r"[-–—]", surya_gap)
        ) or (
            marker_gap == "-" and surya_gap in {"–", "—"}
        ) or (
            marker_gap.isspace() and surya_gap in {"-", "–", "—"}
        ):
            span_replacements.append((marker_gap_start, marker_gap_end, surya_gap))

    for marker_index, surya_index in aligned.items():
        marker_match = marker_matches[marker_index]
        surya_match = surya_matches[surya_index]
        if not marker_match.group(0).isdigit() or not surya_match.group(0).isdigit():
            continue
        if (
            surya_match.start() > 0
            and surya_match.end() < len(surya_text)
            and surya_text[surya_match.start() - 1] == "["
            and surya_text[surya_match.end()] == "]"
            and not (
                marker_match.start() > 0
                and marker_match.end() < len(marker_text)
                and marker_text[marker_match.start() - 1] == "["
                and marker_text[marker_match.end()] == "]"
            )
        ):
            replacements.pop(marker_index, None)
            span_replacements.append(
                (marker_match.start(), marker_match.end(), f"[{marker_match.group(0)}]")
            )

    for index, replacement in replacements.items():
        match = marker_matches[index]
        span_replacements.append((match.start(), match.end(), replacement))
    for start, end, replacement in sorted(span_replacements, reverse=True):
        marker_text = marker_text[:start] + replacement + marker_text[end:]
    marker_text = re.sub(r"(?<=\S)\s*-{2,3}\s*(?=\S)", "—", marker_text)
    marker_text = re.sub(r"(\[\d+\])(?=[A-Za-z])", r"\1 ", marker_text)
    return marker_text


def heading_prefix(block: dict[str, Any]) -> str:
    block_type = str(block.get("block_type") or "")
    if block_type != "SectionHeader":
        return ""
    source = str(block.get("html") or "")
    match = re.search(r"<h([1-6])\b", source, re.I)
    level = int(match.group(1)) if match else 2
    return "#" * max(2, min(level, 4)) + " "


def image_extension(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG"):
        return ".png"
    if raw.startswith(b"GIF8"):
        return ".gif"
    if raw.startswith(b"RIFF") and b"WEBP" in raw[:16]:
        return ".webp"
    return ".jpg"


def decode_block_images(
    block: dict[str, Any],
    asset_dir: Path,
    page_index: int,
    block_index: int,
) -> list[Path]:
    outputs: list[Path] = []
    images = block.get("images") or {}
    if not isinstance(images, dict):
        return outputs
    for image_index, encoded in enumerate(images.values(), start=1):
        if not isinstance(encoded, str) or not encoded:
            continue
        raw = base64.b64decode(encoded)
        extension = image_extension(raw)
        output = asset_dir / (
            f"page-{page_index + 1:04d}-block-{block_index:03d}-image-{image_index:02d}{extension}"
        )
        output.write_bytes(raw)
        outputs.append(output)
    return outputs


def marker_pages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    pages = [
        item
        for item in payload.get("children", [])
        if isinstance(item, dict) and item.get("block_type") == "Page"
    ]
    if not pages:
        raise RuntimeError("Marker JSON contains no Page blocks")
    return pages


def surya_pages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if len(payload) != 1:
        raise RuntimeError(f"expected one Surya document, found {len(payload)}")
    pages = next(iter(payload.values()))
    if not isinstance(pages, list) or not pages:
        raise RuntimeError("Surya JSON contains no pages")
    return pages


def merge_outputs(
    marker_json: Path,
    surya_json: Path,
    output_dir: Path,
    title: str,
    source_pdf: Path,
) -> dict[str, Any]:
    marker = json.loads(marker_json.read_text(encoding="utf-8"))
    surya = json.loads(surya_json.read_text(encoding="utf-8"))
    m_pages = marker_pages(marker)
    s_pages = surya_pages(surya)
    if len(m_pages) != len(s_pages):
        raise RuntimeError(
            f"page coverage mismatch: Marker={len(m_pages)} Surya={len(s_pages)}"
        )

    asset_dir = output_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    markdown_lines = [
        "---",
        f"source_pdf: {source_pdf.name}",
        "conversion: marker-surya-hybrid",
        f"generated_at: {utc_now()}",
        f"total_pdf_pages: {len(m_pages)}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    image_count = 0
    fallback_blocks = 0
    fused_blocks = 0
    unmatched_lines = 0
    low_confidence_lines = 0
    output_blocks = 0

    for page_offset, (m_page, s_page) in enumerate(zip(m_pages, s_pages)):
        page_id = str(m_page.get("id") or "")
        page_match = re.search(r"/page/(\d+)/", page_id)
        page_index = int(page_match.group(1)) if page_match else page_offset
        page_box = bbox(m_page.get("bbox")) or (0.0, 0.0, 432.0, 648.0)
        ocr_lines = scale_surya_lines(s_page, page_box)
        blocks = [item for item in m_page.get("children", []) if isinstance(item, dict)]
        assignments: dict[int, list[dict[str, Any]]] = {index: [] for index in range(len(blocks))}

        for line in ocr_lines:
            scored: list[tuple[float, int]] = []
            for block_index, block in enumerate(blocks):
                if str(block.get("block_type") or "") not in TEXT_BLOCK_TYPES:
                    continue
                block_box = bbox(block.get("bbox"))
                if block_box is None:
                    continue
                score = overlap_fraction(line["bbox"], block_box)
                if score >= 0.28:
                    scored.append((score, block_index))
            if not scored:
                unmatched_lines += 1
                continue
            _, best_index = max(scored)
            assignments[best_index].append(line)
            if line["confidence"] < 0.70:
                low_confidence_lines += 1

        markdown_lines.append(f"<!-- source_page_index={page_index} -->")
        markdown_lines.append("")
        for block_index, block in enumerate(blocks):
            block_type = str(block.get("block_type") or "")
            if block_type in IGNORED_BLOCK_TYPES:
                continue
            image_paths = decode_block_images(block, asset_dir, page_index, block_index)
            for image_path in image_paths:
                relative = image_path.relative_to(output_dir).as_posix()
                markdown_lines.extend((f"![]({relative})", ""))
                image_count += 1
                output_blocks += 1
            if block_type not in TEXT_BLOCK_TYPES:
                continue
            selected = sorted(assignments.get(block_index, []), key=lambda item: item["order"])
            surya_text = join_ocr_lines([item["text"] for item in selected])
            marker_text = strip_html(str(block.get("html") or ""))
            block_box = bbox(block.get("bbox"))
            if (
                block_type == "SectionHeader"
                and block_box is not None
                and block_box[3] <= page_box[1] + (page_box[3] - page_box[1]) * 0.10
                and re.fullmatch(r"\d+[.]?\s+.{1,80}", marker_text or surya_text)
            ):
                continue
            if marker_text and surya_text:
                text = fuse_marker_surya_text(marker_text, surya_text)
                fused_blocks += 1
            elif marker_text:
                text = marker_text
                fallback_blocks += 1
            else:
                text = surya_text
            if not text or re.fullmatch(r"(?:\d{1,5}|[ivxlcdm]{1,10})", text, re.I):
                continue
            prefix = heading_prefix(block)
            if block_type == "ListItem" and not prefix:
                prefix = "- "
            markdown_lines.extend((prefix + text, ""))
            output_blocks += 1

    markdown_path = output_dir / "hybrid.md"
    markdown_path.write_text("\n".join(markdown_lines).rstrip() + "\n", encoding="utf-8")
    visible_chars = len(re.sub(r"\s+", "", "\n".join(markdown_lines)))
    report = {
        "schema_version": 1,
        "status": "complete",
        "generated_at": utc_now(),
        "source_pdf": str(source_pdf),
        "marker_json": str(marker_json),
        "surya_json": str(surya_json),
        "markdown": str(markdown_path),
        "pages": len(m_pages),
        "visible_chars": visible_chars,
        "output_blocks": output_blocks,
        "image_count": image_count,
        "fused_text_blocks": fused_blocks,
        "fallback_marker_text_blocks": fallback_blocks,
        "unmatched_surya_lines": unmatched_lines,
        "low_confidence_surya_lines": low_confidence_lines,
    }
    (output_dir / "status.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_pdf")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--page-range", default="")
    parser.add_argument("--highres-image-dpi", type=int, default=240)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--merge-only", action="store_true")
    args = parser.parse_args()

    source_pdf = Path(args.input_pdf).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    marker_dir = output_dir / "marker"
    surya_dir = output_dir / "surya"
    if not source_pdf.exists():
        raise FileNotFoundError(source_pdf)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.force and not args.merge_only:
        archive_existing(marker_dir)
        archive_existing(surya_dir)

    if not args.merge_only and not marker_dir.exists():
        command = [
            shutil.which("marker_single") or "marker_single",
            str(source_pdf),
            "--output_dir",
            str(marker_dir),
            "--output_format",
            "json",
            "--highres_image_dpi",
            str(args.highres_image_dpi),
            "--disable_tqdm",
        ]
        if args.page_range:
            command.extend(("--page_range", args.page_range))
        run_logged(command, output_dir / "marker.log")

    if not args.merge_only and not surya_dir.exists():
        command = [
            shutil.which("surya_ocr") or "surya_ocr",
            str(source_pdf),
            "--output_dir",
            str(surya_dir),
            "--disable_math",
        ]
        if args.page_range:
            command.extend(("--page_range", args.page_range))
        run_logged(command, output_dir / "surya.log")

    report = merge_outputs(
        find_marker_json(marker_dir),
        find_surya_json(surya_dir),
        output_dir,
        args.title,
        source_pdf,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
