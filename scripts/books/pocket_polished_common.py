#!/usr/bin/env python3
"""Shared preparation and validation for evidence-preserving pocket polishing."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
SOURCE_QUEUE = ROOT / "build-pocket/tasks/source-queue-2026-07-12.json"
OUTPUT_ROOT = ROOT / "build-pocket-polished"

ATOMIC_ENV_RE = re.compile(
    r"\\begin\{(?P<env>longtable|tabular\*?|tabularx|equation\*?|align\*?|"
    r"gather\*?|multline\*?|displaymath|math|tikzpicture|picture|verbatim|"
    r"lstlisting|adjustbox)\}(?P<body>.*?)\\end\{(?P=env)\}",
    re.S,
)
DISPLAY_MATH_RE = re.compile(r"\\\[(?:.|\n)*?\\\]", re.S)
INLINE_PROTECTED_RE = re.compile(
    r"\\includegraphics(?:\[[^\]]*\])?\{[^{}]*\}"
    r"|\\(?:label|ref|pageref|eqref|cite|url)\{[^{}]*\}"
    r"|\\\((?:.|\n)*?\\\)"
    r"|(?<!\\)\$(?:\\.|[^$\n])*?(?<!\\)\$",
    re.S,
)
COMMAND_RE = re.compile(r"\\[A-Za-z@]+\*?|\\.")
NUMBER_RE = re.compile(r"\d+")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
HTML_RE = re.compile(r"</?[A-Za-z][^>]*>|&(?:nbsp|amp|lt|gt|quot);", re.I)
STRUCTURAL_ONLY_RE = re.compile(
    r"^\s*(?:%[^\n]*\n\s*)*(?:\\(?:frontmatter|mainmatter|backmatter|maketitle|"
    r"tableofcontents|clearpage|cleardoublepage|newpage|appendix|thispagestyle|"
    r"setcounter|hypersetup|addcontentsline|phantomsection|begin|end)\b[^\n]*\s*)+$",
    re.S,
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_no}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"expected object at {path}:{line_no}")
        rows.append(value)
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def source_tasks(queue_path: Path = SOURCE_QUEUE) -> list[dict[str, Any]]:
    payload = read_json(queue_path)
    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list):
        raise ValueError(f"queue does not contain tasks: {queue_path}")
    return tasks


def visible_text(tex: str) -> str:
    text = re.sub(r"(?m)%.*$", " ", tex)
    text = INLINE_PROTECTED_RE.sub(" ", text)
    text = COMMAND_RE.sub(" ", text)
    text = text.replace("{", " ").replace("}", " ").replace("&", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detect_source_language(tex: str) -> str:
    plain = visible_text(tex)
    cjk = len(re.findall(r"[\u3400-\u9fff]", plain))
    latin = len(re.findall(r"[A-Za-z]", plain))
    return "zh" if cjk > max(200, latin * 0.7) else "en"


def classify_segment(tex: str, environment: str = "") -> str:
    if environment in {"longtable", "tabular", "tabular*", "tabularx"}:
        return "table"
    if environment:
        return "protected"
    plain = visible_text(tex)
    if not plain or sum(char.isalpha() for char in plain) < 5:
        return "protected"
    if STRUCTURAL_ONLY_RE.match(tex):
        return "protected"
    if "\\includegraphics" in tex and len(plain) < 12:
        return "protected"
    return "text"


def split_non_atomic(text: str) -> list[tuple[str, str]]:
    parts = re.split(r"(\n[ \t]*\n+)", text)
    return [(classify_segment(part), part) for part in parts if part]


def split_tex_segments(tex: str, book_id: str) -> list[dict[str, Any]]:
    begin = tex.find(r"\begin{document}")
    end = tex.rfind(r"\end{document}")
    if begin < 0 or end < begin:
        raise ValueError(f"{book_id}: TeX document boundaries not found")
    begin_end = begin + len(r"\begin{document}")
    raw_parts: list[tuple[str, str]] = [("protected", tex[:begin_end])]
    body = tex[begin_end:end]
    cursor = 0
    atomic_matches = list(ATOMIC_ENV_RE.finditer(body)) + list(DISPLAY_MATH_RE.finditer(body))
    atomic_matches.sort(key=lambda match: (match.start(), -(match.end() - match.start())))
    selected: list[re.Match[str]] = []
    occupied_until = -1
    for match in atomic_matches:
        if match.start() < occupied_until:
            continue
        selected.append(match)
        occupied_until = match.end()
    for match in selected:
        if match.start() > cursor:
            raw_parts.extend(split_non_atomic(body[cursor : match.start()]))
        block = match.group(0)
        environment = match.groupdict().get("env") or "displaymath"
        raw_parts.append((classify_segment(block, environment), block))
        cursor = match.end()
    if cursor < len(body):
        raw_parts.extend(split_non_atomic(body[cursor:]))
    raw_parts.append(("protected", tex[end:]))

    segments: list[dict[str, Any]] = []
    offset = 0
    for index, (kind, source_tex) in enumerate(raw_parts, start=1):
        segment_id = f"{book_id}-s{index:06d}"
        segment = {
            "segment_id": segment_id,
            "index": index,
            "kind": kind,
            "source_sha256": sha256_text(source_tex),
            "source_tex": source_tex,
            "start_offset": offset,
            "end_offset": offset + len(source_tex),
        }
        segments.append(segment)
        offset += len(source_tex)
    if "".join(item["source_tex"] for item in segments) != tex:
        raise AssertionError(f"{book_id}: segment split is not lossless")
    return segments


def protect_inline(tex: str) -> tuple[str, list[dict[str, str]]]:
    protected: list[dict[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        token = f"@@PROTECTED_{len(protected) + 1:04d}@@"
        protected.append({"token": token, "tex": match.group(0)})
        return token

    return INLINE_PROTECTED_RE.sub(replace, tex), protected


def restore_inline(tex: str, protected: list[dict[str, str]]) -> str:
    restored = tex
    for item in protected:
        restored = restored.replace(item["token"], item["tex"])
    return restored


def protected_token_sequence(text: str) -> list[str]:
    return re.findall(r"@@PROTECTED_\d{4}@@", text)


def command_signature(text: str) -> list[str]:
    return COMMAND_RE.findall(text)


def numeric_signature(text: str) -> list[str]:
    # Compare numeric atoms rather than punctuation-bound groups.  This keeps
    # factual digit order strict while permitting definite OCR repairs such as
    # ``94305- 4060`` -> ``94305-4060``.
    return NUMBER_RE.findall(text)


def japanese_kana_required(source_tex: str, source_plain: str) -> bool:
    """Return whether kana is required to prove prose is actually Japanese."""
    if len(source_plain) < 40:
        return False
    if re.search(
        r"\\(?:part|chapter|section|subsection|subsubsection|paragraph|title|"
        r"author|date|hypertarget|texorpdfstring)\b",
        source_tex,
    ):
        return False
    if re.search(
        r"\b(?:office|address|isbn|issn|copyright|publisher|published|"
        r"department|university)\b",
        source_plain,
        re.I,
    ):
        return False
    return True


def japanese_translation_optional(source_plain: str) -> bool:
    """Allow invariant publisher/address metadata to remain in its source form."""
    return bool(
        re.search(
            r"\b(?:copyright|isbn|issn|publisher|publishing|printed|office|"
            r"address|street|suite|road|avenue|university press)\b",
            source_plain,
            re.I,
        )
    )


def table_signature(text: str) -> dict[str, int]:
    return {
        "ampersands": len(re.findall(r"(?<!\\)&", text)),
        "row_breaks": len(re.findall(r"\\\\(?:\[[^\]]*\])?", text)),
        "toprule": text.count(r"\toprule"),
        "midrule": text.count(r"\midrule"),
        "bottomrule": text.count(r"\bottomrule"),
        "endhead": text.count(r"\endhead"),
    }


def make_review_chunks(
    segments: list[dict[str, Any]],
    *,
    book_id: str,
    title: str,
    source: str,
    source_language: str,
    max_chars: int,
) -> list[dict[str, Any]]:
    review = [item for item in segments if item["kind"] in {"text", "table"}]
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for segment in review:
        size = len(segment["source_tex"])
        if current and current_chars + size > max_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(segment)
        current_chars += size
    if current:
        chunks.append(current)

    tasks: list[dict[str, Any]] = []
    for index, group in enumerate(chunks, start=1):
        task_segments: list[dict[str, Any]] = []
        for segment in group:
            protected_tex, protected = protect_inline(segment["source_tex"])
            task_segments.append(
                {
                    "segment_id": segment["segment_id"],
                    "kind": segment["kind"],
                    "source_sha256": segment["source_sha256"],
                    "source_tex": protected_tex,
                    "protected": protected,
                    "command_signature": command_signature(protected_tex),
                    "numeric_signature": numeric_signature(protected_tex),
                    "table_signature": table_signature(protected_tex),
                }
            )
        chunk_id = f"{book_id}-p{index:05d}"
        tasks.append(
            {
                "schema_version": 1,
                "book_id": book_id,
                "title": title,
                "source": source,
                "source_language": source_language,
                "chunk_id": chunk_id,
                "chunk_index": index,
                "segment_count": len(task_segments),
                "segments": task_segments,
            }
        )
    return tasks


def output_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "book_id", "chunk_id", "segments"],
        "properties": {
            "schema_version": {"type": "integer", "const": 1},
            "book_id": {"type": "string"},
            "chunk_id": {"type": "string"},
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "segment_id",
                        "source_sha256",
                        "en_tex",
                        "ja_tex",
                        "changes",
                        "unresolved",
                    ],
                    "properties": {
                        "segment_id": {"type": "string"},
                        "source_sha256": {"type": "string"},
                        "en_tex": {"type": "string"},
                        "ja_tex": {"type": "string"},
                        "changes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["before", "after", "reason", "confidence"],
                                "properties": {
                                    "before": {"type": "string"},
                                    "after": {"type": "string"},
                                    "reason": {"type": "string"},
                                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                                },
                            },
                        },
                        "unresolved": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
    }


def reviewer_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["accept", "issues", "summary"],
        "properties": {
            "accept": {"type": "boolean"},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["segment_id", "severity", "message"],
                    "properties": {
                        "segment_id": {"type": "string"},
                        "severity": {"type": "string", "enum": ["error", "warning"]},
                        "message": {"type": "string"},
                    },
                },
            },
            "summary": {"type": "string"},
        },
    }


def validate_chunk_output(task: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if result.get("book_id") != task["book_id"]:
        errors.append("book_id mismatch")
    if result.get("chunk_id") != task["chunk_id"]:
        errors.append("chunk_id mismatch")
    expected = task["segments"]
    actual = result.get("segments")
    if not isinstance(actual, list):
        return errors + ["segments must be an array"]
    if [item.get("segment_id") for item in actual if isinstance(item, dict)] != [
        item["segment_id"] for item in expected
    ]:
        errors.append("segment IDs/order do not exactly match source")
        return errors

    for source, output in zip(expected, actual):
        segment_id = source["segment_id"]
        prefix = f"{segment_id}: "
        if output.get("source_sha256") != source["source_sha256"]:
            errors.append(prefix + "source_sha256 mismatch")
        en_tex = output.get("en_tex")
        ja_tex = output.get("ja_tex")
        if not isinstance(en_tex, str) or not isinstance(ja_tex, str):
            errors.append(prefix + "en_tex and ja_tex must be strings")
            continue
        for language, candidate in (("en", en_tex), ("ja", ja_tex)):
            if "\ufffd" in candidate or HTML_RE.search(candidate):
                errors.append(prefix + f"{language}_tex contains replacement/HTML text")
            if protected_token_sequence(candidate) != protected_token_sequence(source["source_tex"]):
                errors.append(prefix + f"{language}_tex changed protected token sequence")
            if command_signature(candidate) != source["command_signature"]:
                errors.append(prefix + f"{language}_tex changed TeX command sequence")
            if Counter(numeric_signature(candidate)) != Counter(source["numeric_signature"]):
                errors.append(prefix + f"{language}_tex changed numeric facts/counts")
            if source["kind"] == "table" and table_signature(candidate) != source["table_signature"]:
                errors.append(prefix + f"{language}_tex changed table structure")
            if candidate.count("{") != candidate.count("}"):
                errors.append(prefix + f"{language}_tex has unbalanced braces")

        source_plain = visible_text(source["source_tex"])
        en_plain = visible_text(en_tex)
        ja_plain = visible_text(ja_tex)
        source_len = max(1, len(source_plain))
        source_language = task.get("source_language", "en")
        if source_language == "en":
            if len(en_plain) < source_len * 0.62 or len(en_plain) > source_len * 1.45:
                errors.append(prefix + "English length suggests omission or unsupported expansion")
            similarity = SequenceMatcher(None, source_plain.lower(), en_plain.lower()).ratio()
            if source_len >= 80 and similarity < 0.52:
                errors.append(prefix + f"English is not conservative enough (similarity={similarity:.3f})")
        elif source_len >= 40 and (len(en_plain) < source_len * 0.20 or len(en_plain) > source_len * 4.0):
            errors.append(prefix + "translated English length suggests omission or unsupported expansion")
        if source_len >= 40 and (len(ja_plain) < source_len * 0.20 or len(ja_plain) > source_len * 3.20):
            errors.append(prefix + "Japanese length suggests omission or unsupported expansion")
        if (
            source_len >= 40
            and not japanese_translation_optional(source_plain)
            and not KANA_RE.search(ja_plain)
        ):
            if not CJK_RE.search(ja_plain):
                errors.append(prefix + "Japanese output contains no Japanese script")
            elif japanese_kana_required(source["source_tex"], source_plain):
                errors.append(prefix + "Japanese prose contains no kana")

        changes = output.get("changes")
        if not isinstance(changes, list):
            errors.append(prefix + "changes must be an array")
        else:
            for change in changes:
                if not isinstance(change, dict):
                    errors.append(prefix + "change entry is not an object")
                    continue
                before = change.get("before", "")
                after = change.get("after", "")
                confidence = change.get("confidence")
                if not before or before not in source["source_tex"]:
                    errors.append(prefix + "change.before is not grounded in source_tex")
                if not after or after not in en_tex:
                    errors.append(prefix + "change.after is not present in en_tex")
                if not isinstance(confidence, (int, float)) or confidence < 0.85:
                    errors.append(prefix + "English corrections require confidence >= 0.85")
            if source_language == "en" and en_tex != source["source_tex"] and not changes:
                errors.append(prefix + "changed English lacks an evidence record")
        unresolved = output.get("unresolved")
        if not isinstance(unresolved, list):
            errors.append(prefix + "unresolved must be an array")
    return errors


def restored_segment_output(task_segment: dict[str, Any], output: dict[str, Any], language: str) -> str:
    return restore_inline(output[f"{language}_tex"], task_segment["protected"])


def inventory(tex: str) -> dict[str, Any]:
    return {
        "includegraphics": tex.count(r"\includegraphics"),
        "longtable": tex.count(r"\begin{longtable}"),
        "tabular": tex.count(r"\begin{tabular}"),
        "display_math": tex.count(r"\[") + len(re.findall(r"\\begin\{(?:equation|align|gather|multline)", tex)),
        "labels": sorted(re.findall(r"\\label\{([^{}]+)\}", tex)),
        "refs": sorted(re.findall(r"\\(?:ref|eqref|pageref)\{([^{}]+)\}", tex)),
    }


def compare_inventory(source: str, candidate: str) -> list[str]:
    expected = inventory(source)
    actual = inventory(candidate)
    return [f"{key}: expected {expected[key]!r}, got {actual[key]!r}" for key in expected if expected[key] != actual[key]]
