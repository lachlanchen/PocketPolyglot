#!/usr/bin/env python3
"""Shared preparation and validation for evidence-preserving pocket polishing."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
SOURCE_QUEUE = ROOT / "build-pocket/tasks/source-queue-2026-07-12.json"
OUTPUT_ROOT = ROOT / "build-pocket-polished"

ATOMIC_ENV_RE = re.compile(
    r"\\begin\{(?P<env>longtable|tabular\*?|tabularx|equation\*?|align\*?|"
    r"gather\*?|multline\*?|displaymath|math|tikzpicture|picture|verbatim|"
    r"lstlisting|adjustbox|center(?=\}(?:(?!\\end\{center\}).){0,4000}\\multirow))\}"
    r"(?P<body>.*?)\\end\{(?P=env)\}",
    re.S,
)
DISPLAY_MATH_RE = re.compile(r"\\\[.*?\\\]", re.S)
INCLUDEGRAPHICS_TOKEN_RE = re.compile(
    r"\\includegraphics(?:\[[^\]]*\])?"
    r"\{(?P<argument>\\detokenize\{[^{}]*\}|[^{}]*)\}"
)
INLINE_PROTECTED_RE = re.compile(
    INCLUDEGRAPHICS_TOKEN_RE.pattern
    + r"|\\(?:label|ref|pageref|eqref|cite|url)\{[^{}]*\}"
    + r"|\\\(.*?\\\)"
    + r"|(?<!\\)\$(?:\\.|[^$\n])*?(?<!\\)\$",
    re.S,
)
NON_MATH_INLINE_PROTECTED_RE = re.compile(
    INCLUDEGRAPHICS_TOKEN_RE.pattern
    + r"|\\(?:label|ref|pageref|eqref|cite|url)\{[^{}]*\}",
    re.S,
)
COMMAND_RE = re.compile(r"\\[A-Za-z@]+\*?|\\.")
STRUCTURAL_COMMAND_RE = re.compile(
    r"\\(?:begin|end)\{[^{}]+\}"
    r"|\\(?:part|chapter|section|subsection|subsubsection|paragraph|"
    r"item|frontmatter|mainmatter|backmatter|appendix|clearpage|cleardoublepage|"
    r"newpage|tableofcontents|addcontentsline|setcounter|label|ref|pageref|"
    r"eqref|cite|includegraphics)\*?"
)
INLINE_MATH_RE = re.compile(
    r"\\\[(?P<display>.*?)\\\]"
    r"|\\\((?P<paren>.*?)\\\)"
    r"|(?<!\\)\$(?P<dollar>(?:\\.|[^$\n])*?)(?<!\\)\$",
    re.S,
)
MATH_ENV_RE = re.compile(
    r"\\begin\{(?P<env>equation\*?|align\*?|gather\*?|multline\*?|displaymath|math)\}"
    r"(?P<body>.*?)\\end\{(?P=env)\}",
    re.S,
)
MATH_ENVIRONMENTS = {
    "equation",
    "equation*",
    "align",
    "align*",
    "gather",
    "gather*",
    "multline",
    "multline*",
    "displaymath",
    "math",
}
NUMBER_RE = re.compile(r"\d+")
NUMERIC_POWER_RE = re.compile(
    r"(?P<base>\d+)\s*\^\s*(?:\{(?P<braced>[+-]?\d+)\}|(?P<plain>[+-]?\d+))"
)
PROTECTED_TOKEN_RE = re.compile(r"@@PROTECTED_\d{4}@@")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
# Restrict tag detection to actual transport/markup tags.  Technical game
# theory prose legitimately uses angle profiles such as ``<up, left>``;
# treating every alphabetic angle span as HTML caused deterministic retries.
HTML_RE = re.compile(
    r"</?(?:html|head|body|div|span|p|br|hr|sup|sub|em|strong|b|i|u|"
    r"table|thead|tbody|tfoot|tr|td|th|ul|ol|li|a|img|figure|figcaption)"
    r"(?:\s+[^<>]*)?/?>|&(?:nbsp|amp|lt|gt|quot);",
    re.I,
)
PLAIN_STRATEGY_PROFILE_RE = re.compile(
    r"(?:<\s*[^<>\n,，、]+(?:\s*[,，、]\s*[^<>\n,，、]+)+\s*>"
    r"|〈\s*[^〈〉\n,，、]+(?:\s*[,，、]\s*[^〈〉\n,，、]+)+\s*〉)"
)
STRUCTURAL_ONLY_RE = re.compile(
    r"^\s*(?:%[^\n]*\n\s*)*(?:\\(?:frontmatter|mainmatter|backmatter|maketitle|"
    r"tableofcontents|clearpage|cleardoublepage|newpage|appendix|thispagestyle|"
    r"setcounter|hypersetup|addcontentsline|phantomsection|begin|end)\b[^\n]*\s*)+$",
    re.S,
)
RUNNING_HEADER_TEX_RE = re.compile(
    r"\s*(?:"
    r"\\(?:emph|textit)\{[^{}\n]{1,64}\}\s+"
    r"(?:\d{1,4}|[ivxlcdm]{1,10})"
    r"|(?:\d{1,4}|[ivxlcdm]{1,10})\s+"
    r"\\(?:emph|textit)\{[^{}\n]{1,64}\}"
    r")\s*",
    re.I,
)
PAGE_BREAK_TEX_RE = re.compile(
    r"\s*(?:\\(?:clearpage|cleardoublepage|newpage)\s*)+\s*",
    re.I,
)
HEADING_START_TEX_RE = re.compile(
    r"\s*\\(?:part|chapter|section|subsection|subsubsection|paragraph|"
    r"begin|includegraphics)\b",
    re.I,
)
ENVIRONMENT_COMMAND_RE = re.compile(
    r"\\(?P<action>begin|end)\{(?P<environment>[A-Za-z*@]+)\}"
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_tex_environment_balance(tex: str) -> None:
    """Reject mismatched TeX environments before splitting model tasks."""

    stack: list[tuple[str, int]] = []
    for match in ENVIRONMENT_COMMAND_RE.finditer(tex):
        environment = match.group("environment")
        line = tex.count("\n", 0, match.start()) + 1
        if match.group("action") == "begin":
            stack.append((environment, line))
            continue
        if not stack or stack[-1][0] != environment:
            current = stack[-1][0] if stack else "none"
            raise ValueError(
                "malformed source environment at line "
                f"{line}: closing {environment} while {current} is open"
            )
        stack.pop()
    if stack:
        environment, line = stack[-1]
        raise ValueError(
            f"malformed source environment: unclosed {environment} from line {line}"
        )


ANSI_ITALIC_RE = re.compile(r"\x1b\[3m(?P<body>.*?)\x1b\[0m", re.DOTALL)
ANSI_BOLD_RE = re.compile(r"\x1b\[1m(?P<body>.*?)\x1b\[0m", re.DOTALL)
ANSI_SGR_RE = re.compile(r"\x1b\[[0-9;]*m")
INVALID_TRANSPORT_CONTROL_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1a\x1c-\x1f\x7f]"
)


def normalize_transport_formatting(text: str) -> tuple[str, int]:
    """Convert leaked terminal styling to TeX and drop invalid control bytes."""

    changes = 0
    text, changed = ANSI_ITALIC_RE.subn(
        lambda match: rf"\emph{{{match.group('body')}}}", text
    )
    changes += changed
    text, changed = ANSI_BOLD_RE.subn(
        lambda match: rf"\textbf{{{match.group('body')}}}", text
    )
    changes += changed
    text, changed = ANSI_SGR_RE.subn("", text)
    changes += changed
    text, changed = INVALID_TRANSPORT_CONTROL_RE.subn("", text)
    changes += changed
    return text, changes


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


def normalize_page_boundary_artifacts(
    tex: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Remove evidence-clear page markers inside a split sentence.

    PDF-to-TeX tools sometimes emit ``paragraph / running header / paragraph``
    or ``paragraph / clearpage / paragraph`` at a page boundary. This pass is
    deliberately narrow: the text before the marker must end mid-sentence, the
    text after it must begin with a lowercase continuation, and the middle
    paragraph must be a known page marker. The untouched flattened source
    remains available separately as evidence.
    """

    parts = re.split(r"(\n[ \t]*\n+)", tex)
    changes: list[dict[str, Any]] = []
    index = 0
    while index + 4 < len(parts):
        before, first_gap, marker, second_gap, after = parts[index : index + 5]
        if not first_gap.strip() and not second_gap.strip():
            before_plain = visible_text(before)
            marker_plain = visible_text(marker)
            after_plain = visible_text(after)
            marker_words = marker_plain.split()
            marker_is_running_header = bool(RUNNING_HEADER_TEX_RE.fullmatch(marker))
            marker_is_page_break = bool(PAGE_BREAK_TEX_RE.fullmatch(marker))
            before_is_open = bool(
                before_plain
                and re.search(r"[A-Za-z0-9)'\"]$", before_plain)
                and not re.search(r"[.!?:;][)'\"]?$", before_plain)
            )
            after_is_continuation = bool(
                re.match(r"[a-z]", after_plain)
                or re.match(r"\s*(?:\\\(|\$)", after)
            )
            page_break_is_safe = bool(
                marker_is_page_break
                and sum(char.isalpha() for char in before_plain) >= 24
                and sum(char.isalpha() for char in after_plain) >= 12
                and not HEADING_START_TEX_RE.match(after)
                and not HEADING_START_TEX_RE.match(before)
            )
            if (
                (marker_is_running_header or page_break_is_safe)
                and before_is_open
                and after_is_continuation
            ):
                joiner = "" if before.rstrip().endswith("-") else " "
                merged = before.rstrip() + joiner + after.lstrip()
                changes.append(
                    {
                        "type": (
                            "page-boundary-running-header"
                            if marker_is_running_header
                            else "page-boundary-command"
                        ),
                        "marker_tex": marker.strip(),
                        "marker_text": marker_plain,
                        "before_tail": before_plain[-120:],
                        "after_head": after_plain[:120],
                    }
                )
                parts[index : index + 5] = [merged]
                continue
        index += 2
    return "".join(parts), changes


def apply_exact_paragraph_drops(
    tex: str,
    rules: Iterable[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Apply task-local, evidence-reviewed removal of exact artifact paragraphs."""

    parts = re.split(r"(\n[ \t]*\n+)", tex)
    changes: list[dict[str, Any]] = []
    for rule_index, rule in enumerate(rules, start=1):
        needle = rule.get("tex") if isinstance(rule, dict) else None
        expected = rule.get("expected_count", 1) if isinstance(rule, dict) else 1
        reason = rule.get("reason", "Evidence-reviewed source artifact.") if isinstance(rule, dict) else ""
        if not isinstance(needle, str) or not needle.strip():
            raise ValueError(f"source normalization rule {rule_index} has no exact tex")
        matches = [
            index
            for index in range(0, len(parts), 2)
            if parts[index].strip() == needle.strip()
        ]
        if len(matches) != expected:
            raise ValueError(
                f"source normalization rule {rule_index} expected {expected} exact "
                f"paragraphs, found {len(matches)}: {needle!r}"
            )
        for index in matches:
            digest = sha256_text(parts[index].strip())[:16]
            parts[index] = (
                "% Removed evidence-reviewed source artifact "
                f"sha256={digest}"
            )
            changes.append(
                {
                    "type": "configured-exact-paragraph-drop",
                    "marker_tex": needle.strip(),
                    "marker_text": visible_text(needle),
                    "reason": str(reason),
                    "sha256": sha256_text(needle.strip()),
                }
            )
    return "".join(parts), changes


def apply_exact_text_replacements(
    tex: str,
    rules: Iterable[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Apply evidence-reviewed exact source repairs with cardinality checks."""

    repaired = tex
    changes: list[dict[str, Any]] = []
    for rule_index, rule in enumerate(rules, start=1):
        before = rule.get("before") if isinstance(rule, dict) else None
        span_start = rule.get("span_start") if isinstance(rule, dict) else None
        span_end = rule.get("span_end") if isinstance(rule, dict) else None
        after = rule.get("after") if isinstance(rule, dict) else None
        expected = rule.get("expected_count", 1) if isinstance(rule, dict) else 1
        reason = rule.get("reason", "Evidence-reviewed exact source repair.") if isinstance(rule, dict) else ""
        if not isinstance(after, str):
            raise ValueError(f"source replacement rule {rule_index} has no after text")
        if not isinstance(expected, int) or expected < 1:
            raise ValueError(
                f"source replacement rule {rule_index} has invalid expected_count"
            )
        if isinstance(before, str) and before:
            found = repaired.count(before)
            if found != expected:
                raise ValueError(
                    f"source replacement rule {rule_index} expected {expected} exact "
                    f"matches, found {found}: {before!r}"
                )
            repaired = repaired.replace(before, after)
            changes.append(
                {
                    "type": "configured-exact-text-replacement",
                    "before": before,
                    "after": after,
                    "expected_count": expected,
                    "reason": str(reason),
                    "before_sha256": sha256_text(before),
                }
            )
            continue
        if not (
            isinstance(span_start, str)
            and span_start
            and isinstance(span_end, str)
            and span_end
        ):
            raise ValueError(
                f"source replacement rule {rule_index} needs before text or "
                "non-empty span_start/span_end markers"
            )
        found = repaired.count(span_start)
        if found != expected:
            raise ValueError(
                f"source replacement rule {rule_index} expected {expected} span "
                f"starts, found {found}: {span_start!r}"
            )
        spans: list[tuple[int, int, str]] = []
        cursor = 0
        for _ in range(expected):
            start = repaired.find(span_start, cursor)
            end_marker = repaired.find(span_end, start + len(span_start))
            if end_marker < 0:
                raise ValueError(
                    f"source replacement rule {rule_index} has no span_end after "
                    f"offset {start}: {span_end!r}"
                )
            end = end_marker + len(span_end)
            spans.append((start, end, repaired[start:end]))
            cursor = end
        for start, end, _matched in reversed(spans):
            repaired = repaired[:start] + after + repaired[end:]
        changes.append(
            {
                "type": "configured-exact-span-replacement",
                "span_start": span_start,
                "span_end": span_end,
                "after": after,
                "expected_count": expected,
                "reason": str(reason),
                "before_sha256": [sha256_text(matched) for _, _, matched in spans],
            }
        )
    return repaired, changes


def normalize_split_prose_paragraphs(
    tex: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Join evidence-clear prose paragraphs split only by a PDF page break."""

    parts = re.split(r"(\n[ \t]*\n+)", tex)
    changes: list[dict[str, Any]] = []
    index = 0
    excluded_prefix = re.compile(r"^(?:fig(?:ure)?\.?|table|plate)\s", re.I)
    structural = re.compile(
        r"\\(?:begin|end|part|chapter|section|subsection|subsubsection|"
        r"hypertarget|includegraphics)\b|\\\[|\\\]"
    )
    while index + 2 < len(parts):
        before, gap, after = parts[index : index + 3]
        if gap.strip():
            index += 2
            continue
        before_plain = visible_text(before)
        after_plain = visible_text(after)
        before_letters = sum(char.isalpha() for char in before_plain)
        after_letters = sum(char.isalpha() for char in after_plain)
        uppercase_ratio = (
            sum(char.isupper() for char in before_plain if char.isalpha())
            / before_letters
            if before_letters
            else 0.0
        )
        before_is_open = bool(
            before_plain
            and re.search(r"[A-Za-z0-9)'\"]$", before_plain)
            and not re.search(r"[.!?:;][)'\"]?$", before_plain)
        )
        after_is_continuation = bool(re.match(r"[a-z]", after_plain))
        safe_prose = (
            before_letters >= 24
            and after_letters >= 12
            and not excluded_prefix.match(before_plain)
            and not structural.search(before)
            and not structural.search(after)
            and not before.lstrip().startswith("% Removed evidence-reviewed")
            and not before_plain.lstrip().startswith(("-", "—"))
            and uppercase_ratio < 0.70
        )
        if before_is_open and after_is_continuation and safe_prose:
            joiner = "" if before.rstrip().endswith("-") else " "
            parts[index : index + 3] = [before.rstrip() + joiner + after.lstrip()]
            changes.append(
                {
                    "type": "split-prose-page-boundary",
                    "before_tail": before_plain[-120:],
                    "after_head": after_plain[:120],
                }
            )
            continue
        index += 2
    return "".join(parts), changes


def visible_text_with_math(tex: str) -> str:
    """Extract prose while retaining words accidentally fused into math OCR."""

    text = re.sub(r"(?m)%.*$", " ", tex)
    text = NON_MATH_INLINE_PROTECTED_RE.sub(" ", text)
    text = COMMAND_RE.sub(" ", text)
    text = text.replace("{", " ").replace("}", " ").replace("&", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detect_source_language(
    tex: str,
    *,
    validation_profile: str = "prose_exact",
) -> str:
    plain = (
        visible_text_with_math(tex)
        if validation_profile == "technical_exact"
        else visible_text(tex)
    )
    cjk = len(re.findall(r"[\u3400-\u9fff]", plain))
    latin = len(re.findall(r"[A-Za-z]", plain))
    return "zh" if cjk > max(200, latin * 0.7) else "en"


def classify_segment(
    tex: str,
    environment: str = "",
    *,
    validation_profile: str = "prose_exact",
) -> str:
    if environment in {"longtable", "tabular", "tabular*", "tabularx"}:
        return "table"
    if environment in MATH_ENVIRONMENTS:
        # Equations are source evidence, not translation prose.  Keep them
        # immutable and translate only their surrounding explanation/caption.
        return "protected"
    if environment:
        return "protected"
    plain = (
        visible_text_with_math(tex)
        if validation_profile == "technical_exact"
        else visible_text(tex)
    )
    if not plain or sum(char.isalpha() for char in plain) < 5:
        return "protected"
    if STRUCTURAL_ONLY_RE.match(tex):
        return "protected"
    if "\\includegraphics" in tex and len(plain) < 12:
        return "protected"
    return "text"


def split_non_atomic(
    text: str,
    *,
    validation_profile: str,
) -> list[tuple[str, str]]:
    parts = re.split(r"(\n[ \t]*\n+)", text)
    return [
        (classify_segment(part, validation_profile=validation_profile), part)
        for part in parts
        if part
    ]


def split_tex_segments(
    tex: str,
    book_id: str,
    *,
    validation_profile: str = "prose_exact",
) -> list[dict[str, Any]]:
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
            raw_parts.extend(
                split_non_atomic(
                    body[cursor : match.start()],
                    validation_profile=validation_profile,
                )
            )
        block = match.group(0)
        environment = match.groupdict().get("env") or "displaymath"
        raw_parts.append(
            (
                classify_segment(
                    block,
                    environment,
                    validation_profile=validation_profile,
                ),
                block,
            )
        )
        cursor = match.end()
    if cursor < len(body):
        raw_parts.extend(
            split_non_atomic(
                body[cursor:],
                validation_profile=validation_profile,
            )
        )
    raw_parts.append(("protected", tex[end:]))

    segments: list[dict[str, Any]] = []
    hash_occurrences: Counter[str] = Counter()
    offset = 0
    for index, (kind, source_tex) in enumerate(raw_parts, start=1):
        source_hash = sha256_text(source_tex)
        hash_occurrences[source_hash] += 1
        segment_id = (
            f"{book_id}-s{source_hash[:12]}-{hash_occurrences[source_hash]:02d}"
        )
        segment = {
            "segment_id": segment_id,
            "index": index,
            "kind": kind,
            "source_sha256": source_hash,
            "source_tex": source_tex,
            "start_offset": offset,
            "end_offset": offset + len(source_tex),
        }
        segments.append(segment)
        offset += len(source_tex)
    if "".join(item["source_tex"] for item in segments) != tex:
        raise AssertionError(f"{book_id}: segment split is not lossless")
    return segments


def protect_inline(
    tex: str,
    *,
    protect_math: bool = True,
) -> tuple[str, list[dict[str, str]]]:
    protected: list[dict[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        token = f"@@PROTECTED_{len(protected) + 1:04d}@@"
        protected.append({"token": token, "tex": match.group(0)})
        return token

    pattern = INLINE_PROTECTED_RE if protect_math else NON_MATH_INLINE_PROTECTED_RE
    return pattern.sub(replace, tex), protected


def restore_inline(tex: str, protected: list[dict[str, str]]) -> str:
    restored = tex
    for item in protected:
        restored = restored.replace(item["token"], item["tex"])
    return restored


def protected_token_sequence(text: str) -> list[str]:
    return re.findall(r"@@PROTECTED_\d{4}@@", text)


def command_signature(text: str) -> list[str]:
    return COMMAND_RE.findall(text)


def structural_command_signature(text: str) -> list[str]:
    return STRUCTURAL_COMMAND_RE.findall(text)


def inline_math_signature(text: str) -> list[str]:
    positioned: list[tuple[int, str]] = []
    for match in MATH_ENV_RE.finditer(text):
        body = re.sub(r"\s+", " ", match.group("body")).strip()
        positioned.append((match.start(), f"{match.group('env')}:{body}"))
    for match in INLINE_MATH_RE.finditer(text):
        body = match.group("display") or match.group("paren") or match.group("dollar") or ""
        normalized = re.sub(r"\s+", " ", body).strip()
        atoms = [item.strip() for item in re.split(r"(?<!\\);", normalized) if item.strip()]
        positioned.extend((match.start(), item) for item in atoms)
    positioned.sort(key=lambda item: item[0])
    return [value for _position, value in positioned]


def numeric_signature(text: str) -> list[str]:
    # Compare numeric atoms rather than punctuation-bound groups.  This keeps
    # factual digit order strict while permitting definite OCR repairs such as
    # ``94305- 4060`` -> ``94305-4060``.
    # Placeholder serials are implementation details, not numeric facts.
    return NUMBER_RE.findall(PROTECTED_TOKEN_RE.sub("", text))


def numeric_signature_matches(source: Iterable[str], candidate: str) -> bool:
    """Compare digit facts while allowing evidence-grounded exponent markup.

    OCR frequently flattens ``10^{51}`` into ``1051``.  The English repair
    path remains grounded by exact before/after patches and semantic review;
    this guard only recognizes the two digit-preserving tokenizations of a
    TeX numeric power.  It therefore accepts ``1051`` -> ``10^{51}`` but still
    rejects ``10^{50}``, dropped numbers, duplicated numbers, or reordering
    that changes the numeric multiset.
    """

    expected = Counter(source)
    cleaned = PROTECTED_TOKEN_RE.sub("", candidate)
    matches = list(NUMERIC_POWER_RE.finditer(cleaned))
    if not matches:
        return Counter(numeric_signature(cleaned)) == expected

    variants: list[list[str]] = [[]]
    cursor = 0
    for match in matches:
        fixed = NUMBER_RE.findall(cleaned[cursor : match.start()])
        exponent = (match.group("braced") or match.group("plain")).lstrip("+-")
        alternatives = (
            [match.group("base"), exponent],
            [match.group("base") + exponent],
        )
        variants = [
            existing + fixed + alternative
            for existing in variants
            for alternative in alternatives
        ]
        # Technical prose rarely contains many editable numeric powers in one
        # segment.  Bound pathological inputs without weakening the exact
        # comparison: the unflattened and all-flattened paths are retained.
        if len(variants) > 256:
            variants = variants[:255] + [
                NUMBER_RE.findall(cleaned[: match.end()])
            ]
        cursor = match.end()
    suffix = NUMBER_RE.findall(cleaned[cursor:])
    return any(Counter(variant + suffix) == expected for variant in variants)


def has_grounded_numeric_repair(
    source_tex: str,
    changes: Any,
) -> bool:
    """Return whether a declared source-grounded repair changes OCR digits.

    Numeric OCR errors often substitute a letter and a digit (``lC``/``10``
    or ``ordina1ily``/``ordinarily``).  Such edits cannot satisfy a raw digit
    inventory check, but they are still auditable: the English result is
    reconstructed from exact patches and the independent reviewer receives a
    numeric-difference warning.  This predicate only lets that reviewed path
    run; ordered repair replay below remains the final deterministic guard.
    """

    if not isinstance(changes, list):
        return False
    for change in changes:
        if not isinstance(change, dict):
            continue
        before = change.get("before")
        after = change.get("after")
        confidence = change.get("confidence")
        if (
            isinstance(before, str)
            and isinstance(after, str)
            and before
            and before in source_tex
            and isinstance(confidence, (int, float))
            and confidence >= 0.90
            and numeric_signature(before) != numeric_signature(after)
        ):
            return True
    return False


MATH_SPACING_RE = re.compile(r"\\(?:,|!|;|:|quad|qquad)\s*")
MATH_UNIT_RE = re.compile(
    r"\\(?:mathrm|text)\{(?:"
    r"cm|mm|km|m|kg|g|s|ms|K|Hz|kHz|MHz|GHz|eV|keV|MeV|GeV|TeV"
    r")\}",
    re.I,
)
SIMPLE_MATH_ATOM_RE = re.compile(
    r"^[+-]?(?:\d+(?:\.\d+)?|[A-Za-z]|\\[A-Za-z]+)"
    r"(?:_\{?(?:\d+|[A-Za-z]|\\[A-Za-z]+)\}?)?"
    r"(?:[+-](?:\d+(?:\.\d+)?|[A-Za-z]))?$"
)
PURE_NUMERIC_POWER_RE = re.compile(
    r"^(?:\d+(?:\.\d+)?\\times)?10\^(?:"
    r"\{(?:[+-]?\d+|[A-Za-z]+|\\text\{[A-Za-z]+\})\}"
    r"|[+-]?\d+|[A-Za-z]+)$"
)


def normalized_substantive_math_signature(text: str) -> list[str]:
    """Return equations while ignoring harmless inline-wrapper placement.

    Translation may put a unit or a standalone variable inside ``\(...\)``
    where English leaves it outside.  Requiring identical raw math spans made
    correct technical chunks retry indefinitely.  Nontrivial expressions are
    still compared exactly after removing TeX spacing and a conservative list
    of unit-formatting wrappers; standalone variables are reviewed
    semantically with their surrounding prose.
    """

    # Strategy/action profiles are semantic identities whose labels are
    # translated (``up`` -> ``上``).  Compare their arity and multiplicity,
    # whether represented as textbook angle prose or TeX, while leaving the
    # independent reviewer responsible for label translation accuracy.
    result: list[str] = [
        f"strategy-profile:{match.group(0).count(',') + match.group(0).count('，') + match.group(0).count('、') + 1}"
        for match in PLAIN_STRATEGY_PROFILE_RE.finditer(text)
    ]
    for expression in inline_math_signature(text):
        normalized = expression
        normalized = normalized.replace(r"\left", "").replace(r"\right", "")
        normalized = MATH_SPACING_RE.sub("", normalized)
        normalized = MATH_UNIT_RE.sub("", normalized)
        normalized = re.sub(r"\s+", "", normalized)
        normalized = normalized.replace("−", "-").replace("×", r"\times")
        if r"\langle" in normalized and r"\rangle" in normalized:
            result.append(f"strategy-profile:{normalized.count(',') + 1}")
            continue
        if (
            not normalized
            or SIMPLE_MATH_ATOM_RE.fullmatch(normalized)
            or PURE_NUMERIC_POWER_RE.fullmatch(normalized)
        ):
            continue
        result.append(normalized)
    return result


def numeric_source_is_preserved(source: Iterable[str], candidate: Iterable[str]) -> bool:
    """Require every source digit atom without banning valid translation forms.

    A translated language can conventionally render an English number word or
    Roman ordinal with Arabic digits (for example, ``Leopold I`` as
    ``レオポルト1世``).  Exact Counter equality therefore rejects faithful
    translations.  Source-language transcription remains exact elsewhere;
    translated output must contain every explicit source digit atom at least
    as many times, while the semantic reviewer rejects invented numeric facts.
    """

    expected = Counter(source)
    actual = Counter(candidate)
    return all(actual[value] >= count for value, count in expected.items())


def conservative_english_repair(tex: str) -> tuple[str, list[dict[str, Any]]]:
    """Apply only context-independent OCR fixes to English source TeX."""

    repaired = tex
    changes: list[dict[str, Any]] = []

    def replace_literal(before: str, after: str, reason: str) -> None:
        nonlocal repaired
        if before not in repaired:
            return
        repaired = repaired.replace(before, after)
        changes.append(
            {
                "before": before,
                "after": after,
                "reason": reason,
                "confidence": 0.99,
            }
        )

    for before, after in {
        "ﬀ": "ff",
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
        "undoubtably": "undoubtedly",
    }.items():
        reason = (
            "Expanded a Unicode presentation ligature."
            if before in {"ﬀ", "ﬁ", "ﬂ", "ﬃ", "ﬄ"}
            else "Corrected a definite English spelling error."
        )
        replace_literal(before, after, reason)

    substitutions = (
        (
            re.compile(
                r"(?P<left>\b[A-Za-z][A-Za-z'-]{1,})(?P<mark>[.!?])"
                r"(?P<right>[A-Z][A-Za-z'-]{1,}\b)"
            ),
            lambda match: (
                match.group(0)
                if (
                    match.group("mark") == "."
                    and (
                        match.group("left").lower() in {"www", "http", "https"}
                        or re.match(
                            r"(?:com|org|net|edu|gov|io|co|jp|uk)\b",
                            match.group("right"),
                            re.I,
                        )
                    )
                )
                else match.group("left")
                + match.group("mark")
                + " "
                + match.group("right")
            ),
            "Restored missing whitespace after sentence punctuation.",
        ),
        (
            re.compile(r"(?P<first>\d{5})-[ \t]+(?P<last>\d{4})"),
            lambda match: f"{match.group('first')}-{match.group('last')}",
            "Removed OCR whitespace inside a postal-code digit group.",
        ),
    )
    for pattern, replacement, reason in substitutions:
        pieces: list[str] = []
        cursor = 0
        changed = False
        for match in pattern.finditer(repaired):
            before = match.group(0)
            after = replacement(match)
            if before == after:
                continue
            pieces.extend((repaired[cursor : match.start()], after))
            cursor = match.end()
            changed = True
            changes.append(
                {
                    "before": before,
                    "after": after,
                    "reason": reason,
                    "confidence": 0.99,
                }
            )
        if changed:
            pieces.append(repaired[cursor:])
            repaired = "".join(pieces)
    return repaired, changes


def apply_grounded_english_repairs(
    source_tex: str,
    repairs: Iterable[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Build English deterministically from source plus exact, auditable patches."""

    repaired, changes = conservative_english_repair(source_tex)
    errors: list[str] = []
    for index, repair in enumerate(repairs, start=1):
        if not isinstance(repair, dict):
            errors.append(f"repair {index} is not an object")
            continue
        before = repair.get("before")
        after = repair.get("after")
        reason = repair.get("reason")
        confidence = repair.get("confidence")
        if not isinstance(before, str) or not before:
            errors.append(f"repair {index} has no exact before text")
            continue
        if not isinstance(after, str) or not after:
            errors.append(f"repair {index} has no replacement text")
            continue
        if before not in source_tex:
            errors.append(f"repair {index} before text is not grounded in source")
            continue
        occurrence_count = repaired.count(before)
        already_applied_automatically = any(
            change.get("before") == before and change.get("after") == after
            for change in changes
        )
        if occurrence_count == 0 and (
            after in repaired or already_applied_automatically
        ):
            # The deterministic pre-pass may already have applied the same
            # repair.  A later grounded patch can alter the surrounding text,
            # so the replacement itself need not remain as one literal span.
            # Treat matching evidence as idempotent rather than regenerating
            # an otherwise valid segment.
            continue
        if occurrence_count != 1:
            errors.append(
                f"repair {index} before text must occur exactly once after automatic repair"
            )
            continue
        if not isinstance(confidence, (int, float)) or confidence < 0.90:
            errors.append(f"repair {index} confidence must be at least 0.90")
            continue
        if protected_token_sequence(before) != protected_token_sequence(after):
            errors.append(f"repair {index} changes an immutable protected token")
            continue
        repaired = repaired.replace(before, after, 1)
        changes.append(
            {
                "before": before,
                "after": after,
                "reason": str(reason or "Grounded OCR correction."),
                "confidence": float(confidence),
            }
        )
    return repaired, changes, errors


def japanese_kana_required(source_tex: str, source_plain: str) -> bool:
    """Return whether kana is required to prove prose is actually Japanese."""

    if (
        r"\begin{figure}" in source_tex
        and r"\caption" in source_tex
        and source_tex.count(r"\begin{figure}") == source_tex.count(r"\end{figure}") == 1
    ):
        # Short technical captions such as "dispersion relation" naturally
        # translate to valid kanji-only Japanese (e.g. 分散関係). Semantic
        # review still checks the caption; requiring kana here is a false
        # positive that cannot be fixed by regenerating the same translation.
        return False
    # TeX control lines can make a tiny catalog fragment look long after a
    # naive text extraction (for example an enumerate wrapper around ``cm.``).
    # Measure the actual non-command payload before requiring a translation.
    probe_lines: list[str] = []
    ignorable_control = re.compile(
        r"^\\(?:begin|end|def|setcounter|tightlist|item|label|hypertarget)\b"
    )
    for line in source_tex.splitlines():
        stripped = line.strip()
        if not stripped or ignorable_control.match(stripped):
            continue
        probe_lines.append(line)
    probe_plain = visible_text_with_math("\n".join(probe_lines))
    if len(probe_plain) < 40:
        return False
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


_STANDALONE_CAPTION_RE = re.compile(
    r"\\caption\{(?P<label>Figure|Fig\.?|Table|Equation)\s+"
    r"(?P<number>\d+(?:\.\d+)*)\}",
    re.I,
)


def deterministic_japanese_caption(source_tex: str) -> str | None:
    """Translate a caption-only technical object without a model retry.

    Exact-book sources often wrap a diagram or equation in a structural block
    whose only translatable text is ``Figure 11.3.5``.  A language model can
    turn that label into an incomplete phrase such as ``図11.3.5に示す``.
    Canonicalize only this provably narrow case; any additional prose keeps the
    segment on the normal translation and semantic-review path.
    """

    matches = list(_STANDALONE_CAPTION_RE.finditer(source_tex))
    if len(matches) != 1:
        return None

    residue = _STANDALONE_CAPTION_RE.sub("", source_tex)
    residue = PROTECTED_TOKEN_RE.sub("", residue)
    residue = re.sub(r"\\\((?:.|\n)*?\\\)", "", residue)
    residue = re.sub(r"\\\[(?:.|\n)*?\\\]", "", residue)
    structural_line = re.compile(
        r"(?:\\(?:begin|end)\{[^{}]+\}(?:\[[^\]]*\])?"
        r"|\\captionsetup(?:\[[^\]]*\])?\{[^{}]*\}"
        r"|\\noindent)\s*$"
    )
    for line in residue.splitlines():
        stripped = line.strip()
        if not stripped or structural_line.fullmatch(stripped):
            continue
        return None

    match = matches[0]
    label = match.group("label").lower().rstrip(".")
    translated_label = {
        "figure": "図",
        "fig": "図",
        "table": "表",
        "equation": "式",
    }[label]
    replacement = rf"\caption{{{translated_label}{match.group('number')}}}"
    return source_tex[: match.start()] + replacement + source_tex[match.end() :]


def japanese_translation_optional(
    source_plain: str,
    source_tex: str | None = None,
) -> bool:
    """Allow invariant metadata, references, and indexes to remain unchanged.

    Bibliographies and indexes are lookup structures: translating author names,
    titles, or index headwords breaks their relationship to the English body.
    Detect them conservatively from their conventional locator-heavy shape so
    ordinary prose still requires a real Japanese translation.
    """

    compact = re.sub(r"\s+", "", source_plain)
    music_notation = musical_notation_only(source_plain)
    symbolic_sequence = bool(
        compact
        and len(compact) >= 8
        and re.fullmatch(r"[HTF01→←.·…\-]+", compact, re.I)
    )
    bibliography_entry = bool(
        re.fullmatch(
            r"[A-Z][A-Za-z'’.-]+,\s*(?:[A-Z]\.\s*){1,4}"
            r"\(\d{4}[a-z]?\),?\s+.+"
            r"(?:\[\s*\d+(?:\s*,\s*\d+)*\s*\]|\d+\.?)",
            source_plain.strip(),
        )
    )

    raw_lines = re.split(r"\\\\|\n", source_tex or source_plain)
    reference_lines = [
        visible_text_with_math(line).strip()
        for line in raw_lines
        if visible_text_with_math(line).strip()
    ]
    author_locator = re.compile(
        r"^[A-Z][A-Za-z'’.-]+(?:,\s*(?:[A-Z]\.\s*){1,4})?"
        r"\s*\(\d{4}[a-z]?\),\s*\d+(?:\s*,\s*\d+)*$"
    )
    citation_index = bool(reference_lines) and all(
        author_locator.fullmatch(line) for line in reference_lines
    )

    locator_tail = re.compile(
        r"(?:^|[,\s])\d+(?:\s*[-–]\s*\d+)?"
        r"(?:\s*,\s*\d+(?:\s*[-–]\s*\d+)?)*\s*[.]?$"
    )
    locator_lines = sum(bool(locator_tail.search(line)) for line in reference_lines)
    sentence_lines = sum(bool(re.search(r"[?!]|\.(?:\s|$)", line)) for line in reference_lines)
    average_line_length = (
        sum(len(line) for line in reference_lines) / len(reference_lines)
        if reference_lines
        else 0.0
    )
    subject_index = bool(
        len(reference_lines) >= 12
        and (source_tex or "").count(r"\\") >= 10
        and locator_lines / len(reference_lines) >= 0.45
        and sentence_lines / len(reference_lines) <= 0.15
        and average_line_length <= 100
    )

    return (
        deterministic_japanese_caption(source_tex or "") is not None
        or music_notation
        or symbolic_sequence
        or bibliography_entry
        or citation_index
        or subject_index
        or bool(
        re.search(
            r"\b(?:copyright|isbn|issn|publisher|publishing|printed|office|"
            r"address|street|suite|road|avenue|university press)\b",
            source_plain,
            re.I,
        )
        )
    )


_NOTE_CHORD_TOKEN_RE = re.compile(
    r"(?<![A-Za-z])"
    r"[A-G](?:[#b♭♯])?"
    r"(?:maj|min|mai|m|dim|aug|sus|add|alt|dom)\d*"
    r"(?:[#b♭♯+°]\d*)?"
    r"(?![A-Za-z])"
    r"|(?<![A-Za-z])"
    r"[A-G](?:[#b♭♯])?\d+(?:[#b♭♯+°]\d*)?"
    r"(?:alt)?"
    r"(?![A-Za-z])"
    r"|(?<![A-Za-z])"
    r"[A-G](?:[#b♭♯])?(?:[+°]\d*)?"
    r"(?![A-Za-z])"
)
_ROMAN_CHORD_TOKEN_RE = re.compile(
    r"(?<![A-Za-z])"
    r"[#b♭♯]?[ivIV]+"
    r"(?:maj|min|mai|m|dim|aug|sus|add|alt|dom)?\d*"
    r"(?:[#b♭♯+°]\d*)?"
    r"(?:alt)?"
    r"(?![A-Za-z])"
)
_CHORD_QUALITY_TOKEN_RE = re.compile(
    r"(?<![A-Za-z])(?:maj|min|m|dim|aug|sus|alt|dom)\d+(?:[#b♭♯]\d*)?"
    r"(?![A-Za-z])",
    re.I,
)


def musical_notation_only(source_plain: str) -> bool:
    """Recognize chord charts and progressions that are language-invariant.

    Music OCR frequently emits a long line of chord symbols as a text segment.
    Requiring kana makes a writer add unsupported prose such as ``コード進行``
    or repeatedly regenerate an otherwise exact chart.  This detector remains
    conservative: at least two notation tokens must be present and, after
    removing conventional figure/field labels, at most one short lexical OCR
    residue may remain.  Semantic review still checks notation correctness.
    """

    probe = PROTECTED_TOKEN_RE.sub(" ", source_plain)
    # ``visible_text_with_math`` intentionally keeps enough TeX context for
    # validation, which means table environments can leave lexical-looking
    # residue such as ``longtable @ llllllll@``.  Those are structure, not
    # prose.  Remove only conventional environment names and pure column
    # specifications before classifying the musical payload.
    probe = re.sub(
        r"\b(?:longtable|tabularx?|array|toprule|midrule|bottomrule|endhead)\b",
        " ",
        probe,
        flags=re.I,
    )
    probe = re.sub(r"(?<![A-Za-z])@?[lcrxpmb]{2,}@?(?![A-Za-z])", " ", probe, flags=re.I)
    probe = re.sub(
        r"\b(?:Fig(?:s|ures?)?\.?\s*\d+[A-Za-z]?(?:\s*[-–]\s*\d+[A-Za-z]?)?"
        r"|Harmony|Formula|Construction)\b\s*:?",
        " ",
        probe,
        flags=re.I,
    )
    patterns = (
        _NOTE_CHORD_TOKEN_RE,
        _ROMAN_CHORD_TOKEN_RE,
        _CHORD_QUALITY_TOKEN_RE,
    )
    marker_count = sum(len(pattern.findall(probe)) for pattern in patterns)
    residue = probe
    for pattern in patterns:
        residue = pattern.sub(" ", residue)
    residue = re.sub(r"[\d\s_#♭♯+°()\[\]{}/\\:;,.|*→←=\-–—]+", " ", residue)
    words = re.findall(r"[A-Za-z]+", residue)
    return marker_count >= 2 and len(words) <= 1 and sum(map(len, words)) <= 8


def source_is_notation_only(source_tex: str) -> bool:
    """Return true for protected/structural rows with no translatable prose."""

    without_tokens = PROTECTED_TOKEN_RE.sub("", source_tex)
    # Asset-only rows can carry long file paths and layout options even though
    # they contain no prose. Strip complete graphics/layout commands before
    # checking for lexical text so an image is not sent through futile
    # Japanese-regeneration loops.
    without_tokens = re.sub(
        r"\\graphicspath\s*\{(?:\{[^{}]*\})+\}",
        "",
        without_tokens,
    )
    without_tokens = re.sub(
        r"\\includegraphics(?:\[[^\]]*\])?\{[^{}]*\}",
        "",
        without_tokens,
    )
    without_tokens = re.sub(
        r"\\captionsetup(?:\[[^\]]*\])?\{[^{}]*\}",
        "",
        without_tokens,
    )
    without_tokens = INLINE_MATH_RE.sub("", without_tokens)
    without_tokens = MATH_ENV_RE.sub("", without_tokens)
    without_tokens = re.sub(
        r"\\(?:begin|end)\{[^{}]+\}(?:\[[^\]]*\])?",
        "",
        without_tokens,
    )
    without_commands = re.sub(r"\\[A-Za-z@]+(?:\[[^\]]*\])?", "", without_tokens)
    without_braces = re.sub(r"[{}\\]", "", without_commands)
    return not re.search(r"[A-Za-z]{2,}", without_braces)


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
    max_segments: int = 16,
    validation_profile: str = "prose_exact",
) -> list[dict[str, Any]]:
    review_kinds = {"text", "table"}
    review = [item for item in segments if item["kind"] in review_kinds]
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for segment in review:
        size = len(segment["source_tex"])
        if current and (
            current_chars + size > max_chars or len(current) >= max_segments
        ):
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
            protected_tex, protected = protect_inline(
                segment["source_tex"],
                protect_math=True,
            )
            task_segments.append(
                {
                    "segment_id": segment["segment_id"],
                    "kind": segment["kind"],
                    "source_sha256": segment["source_sha256"],
                    "source_tex": protected_tex,
                    "protected": protected,
                    "command_signature": command_signature(protected_tex),
                    "structural_command_signature": structural_command_signature(protected_tex),
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
                "validation_profile": validation_profile,
                "chunk_id": chunk_id,
                "chunk_index": index,
                "segment_count": len(task_segments),
                "segments": task_segments,
            }
        )
    return tasks


def chunk_subset(task: dict[str, Any], segment_ids: Iterable[str]) -> dict[str, Any]:
    """Return a schema-compatible task containing only selected segments."""

    selected = set(segment_ids)
    subset = deepcopy(task)
    subset["segments"] = [
        segment for segment in task["segments"] if segment["segment_id"] in selected
    ]
    subset["segment_count"] = len(subset["segments"])
    return subset


def source_english_writer_schema() -> dict[str, Any]:
    """Compact model schema for an English source.

    English is reconstructed deterministically from the immutable source plus
    grounded repair patches, so the model returns it neither verbatim nor as a
    free rewrite.  This materially lowers output tokens and variance.
    """

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "book_id", "chunk_id", "segments"],
        "properties": {
            "schema_version": {"type": "integer", "const": 3},
            "book_id": {"type": "string"},
            "chunk_id": {"type": "string"},
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "segment_id",
                        "ja_tex",
                        "repairs",
                        "unresolved",
                    ],
                    "properties": {
                        "segment_id": {"type": "string"},
                        "ja_tex": {"type": "string"},
                        "repairs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["before", "after", "reason", "confidence"],
                                "properties": {
                                    "before": {"type": "string"},
                                    "after": {"type": "string"},
                                    "reason": {"type": "string"},
                                    "confidence": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                },
                            },
                        },
                        "unresolved": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
    }


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
        "required": ["accept", "issues", "corrections", "summary"],
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
            "corrections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "segment_id",
                        "ja_tex",
                        "repairs",
                        "unresolved",
                    ],
                    "properties": {
                        "segment_id": {"type": "string"},
                        "ja_tex": {"type": "string"},
                        "repairs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["before", "after", "reason", "confidence"],
                                "properties": {
                                    "before": {"type": "string"},
                                    "after": {"type": "string"},
                                    "reason": {"type": "string"},
                                    "confidence": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                },
                            },
                        },
                        "unresolved": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "summary": {"type": "string"},
        },
    }


def validate_segment_output(
    task: dict[str, Any],
    source: dict[str, Any],
    output: dict[str, Any],
) -> list[str]:
    """Validate one segment without invalidating unrelated work."""

    errors: list[str] = []
    segment_id = source["segment_id"]
    prefix = f"{segment_id}: "
    if output.get("segment_id") != segment_id:
        return [prefix + "segment_id mismatch"]
    if output.get("source_sha256") != source["source_sha256"]:
        errors.append(prefix + "source_sha256 mismatch")
    en_tex = output.get("en_tex")
    ja_tex = output.get("ja_tex")
    if not isinstance(en_tex, str) or not isinstance(ja_tex, str):
        return errors + [prefix + "en_tex and ja_tex must be strings"]

    source_language = task.get("source_language", "en")
    technical_exact = task.get("validation_profile") == "technical_exact"
    source_brace_delta = source["source_tex"].count("{") - source["source_tex"].count("}")
    expected_brace_delta = source_brace_delta
    declared_changes = output.get("changes")
    if source_language == "en" and source_brace_delta and isinstance(declared_changes, list):
        # Exact-book extraction can split a malformed source brace from its
        # mate.  Permit a model to restore balance only when its complete
        # English output is reproducible from grounded, ordered repairs.  A
        # balanced source may never be made unbalanced, and unrelated
        # cross-segment brace fragments must still preserve their source delta.
        replayed = source["source_tex"]
        grounded = True
        for change in declared_changes:
            if not isinstance(change, dict):
                grounded = False
                break
            before = change.get("before")
            after = change.get("after")
            confidence = change.get("confidence")
            if (
                not isinstance(before, str)
                or not before
                or not isinstance(after, str)
                or not after
                or not isinstance(confidence, (int, float))
                or confidence < 0.85
                or before not in replayed
            ):
                grounded = False
                break
            replayed = replayed.replace(before, after, 1)
        if grounded and replayed == en_tex and en_tex.count("{") == en_tex.count("}"):
            expected_brace_delta = 0
    expected_protected = protected_token_sequence(source["source_tex"])
    for language, candidate in (("en", en_tex), ("ja", ja_tex)):
        if "\ufffd" in candidate or HTML_RE.search(candidate):
            errors.append(prefix + f"{language}_tex contains replacement/HTML text")
        candidate_protected = protected_token_sequence(candidate)
        if language == "en":
            if candidate_protected != expected_protected:
                errors.append(prefix + "en_tex changed protected token sequence")
        elif Counter(candidate_protected) != Counter(expected_protected):
            errors.append(prefix + "ja_tex changed protected token inventory")
        if technical_exact:
            if structural_command_signature(candidate) != source["structural_command_signature"]:
                errors.append(prefix + f"{language}_tex changed structural TeX command sequence")
        elif command_signature(candidate) != source["command_signature"]:
            errors.append(prefix + f"{language}_tex changed TeX command sequence")
        candidate_numbers = numeric_signature(candidate)
        same_language_transcription = source_language == "en" and language == "en"
        if (
            same_language_transcription
            and not numeric_signature_matches(source["numeric_signature"], candidate)
            and not has_grounded_numeric_repair(
                source["source_tex"], output.get("changes")
            )
        ):
            errors.append(prefix + f"{language}_tex changed numeric facts/counts")
        # A translated number can be faithfully reformatted (2.87 million ->
        # 287万).  Its semantic value is checked by the reviewer rather than by
        # raw digit equality, which caused large false-positive retry storms.
        if source["kind"] == "table" and table_signature(candidate) != source["table_signature"]:
            errors.append(prefix + f"{language}_tex changed table structure")
        candidate_brace_delta = candidate.count("{") - candidate.count("}")
        if candidate_brace_delta != expected_brace_delta:
            errors.append(prefix + f"{language}_tex changed brace balance")
    if technical_exact and Counter(
        normalized_substantive_math_signature(en_tex)
    ) != Counter(normalized_substantive_math_signature(ja_tex)):
        errors.append(prefix + "English/Japanese math inventory differs")

    visible = visible_text_with_math if technical_exact else visible_text
    source_plain = visible(source["source_tex"])
    en_plain = visible(en_tex)
    ja_plain = visible(ja_tex)
    source_len = max(1, len(source_plain))
    if source_language == "en":
        if len(en_plain) < source_len * 0.62 or len(en_plain) > source_len * 1.45:
            errors.append(prefix + "English length suggests omission or unsupported expansion")
        similarity = SequenceMatcher(
            None,
            source_plain.lower(),
            en_plain.lower(),
            autojunk=False,
        ).ratio()
        if source_len >= 80 and similarity < 0.52:
            errors.append(prefix + f"English is not conservative enough (similarity={similarity:.3f})")
    elif source_len >= 40 and (len(en_plain) < source_len * 0.20 or len(en_plain) > source_len * 4.0):
        errors.append(prefix + "translated English length suggests omission or unsupported expansion")
    if source_len >= 40 and (len(ja_plain) < source_len * 0.20 or len(ja_plain) > source_len * 3.20):
        errors.append(prefix + "Japanese length suggests omission or unsupported expansion")
    if (
        source_len >= 40
        and not source_is_notation_only(source["source_tex"])
        and not japanese_translation_optional(source_plain, source["source_tex"])
        and japanese_kana_required(source["source_tex"], source_plain)
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
        replayed_english = source["source_tex"]
        replay_errors = False
        for change in changes:
            if not isinstance(change, dict):
                errors.append(prefix + "change entry is not an object")
                replay_errors = True
                continue
            before = change.get("before", "")
            after = change.get("after", "")
            confidence = change.get("confidence")
            if not before or before not in source["source_tex"]:
                errors.append(prefix + "change.before is not grounded in source_tex")
                replay_errors = True
            if not after:
                errors.append(prefix + "change.after is empty")
                replay_errors = True
            if before and after and before in replayed_english:
                replayed_english = replayed_english.replace(before, after)
            elif before and after and after not in replayed_english:
                errors.append(prefix + "change cannot be replayed in declared order")
                replay_errors = True
            if not isinstance(confidence, (int, float)) or confidence < 0.85:
                errors.append(prefix + "English corrections require confidence >= 0.85")
                replay_errors = True
        if source_language == "en" and changes and not replay_errors and replayed_english != en_tex:
            errors.append(prefix + "ordered English repair replay does not equal en_tex")
        if source_language == "en" and en_tex != source["source_tex"] and not changes:
            errors.append(prefix + "changed English lacks an evidence record")
    unresolved = output.get("unresolved")
    if not isinstance(unresolved, list):
        errors.append(prefix + "unresolved must be an array")
    return errors


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
        errors.extend(validate_segment_output(task, source, output))
    return errors


def machine_review_observations(
    task: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, str]]:
    """Surface semantic risks without turning them into retry-causing guesses."""

    observations: list[dict[str, str]] = []
    actual = result.get("segments", [])
    if not isinstance(actual, list):
        return observations
    for source, output in zip(task["segments"], actual):
        if not isinstance(output, dict) or not isinstance(output.get("ja_tex"), str):
            continue
        source_numbers = source["numeric_signature"]
        target_numbers = numeric_signature(output["ja_tex"])
        if Counter(source_numbers) != Counter(target_numbers):
            observations.append(
                {
                    "segment_id": source["segment_id"],
                    "message": (
                        "Japanese numeric notation differs from the source digit inventory; "
                        f"verify semantic values explicitly (source={source_numbers}, "
                        f"target={target_numbers})."
                    ),
                }
            )
    return observations


def restored_segment_output(task_segment: dict[str, Any], output: dict[str, Any], language: str) -> str:
    return restore_inline(output[f"{language}_tex"], task_segment["protected"])


def inventory(tex: str) -> dict[str, Any]:
    graphics: list[str] = []
    for match in INCLUDEGRAPHICS_TOKEN_RE.finditer(tex):
        argument = match.group("argument")
        detokenized = re.fullmatch(r"\\detokenize\{([^{}]*)\}", argument)
        graphics.append(detokenized.group(1) if detokenized else argument)
    environments = Counter(
        re.findall(
            r"\\begin\{(longtable|tabular\*?|tabularx|equation\*?|align\*?|"
            r"gather\*?|multline\*?|displaymath|tikzpicture|picture|figure\*?|"
            r"lstlisting)\}",
            tex,
        )
    )
    return {
        "includegraphics": tex.count(r"\includegraphics"),
        "graphics_paths": sorted(graphics),
        "captions": tex.count(r"\caption"),
        "longtable": tex.count(r"\begin{longtable}"),
        "tabular": tex.count(r"\begin{tabular}"),
        "display_math": tex.count(r"\[") + len(re.findall(r"\\begin\{(?:equation|align|gather|multline)", tex)),
        "technical_environments": dict(sorted(environments.items())),
        "labels": sorted(re.findall(r"\\label\{([^{}]+)\}", tex)),
        "refs": sorted(re.findall(r"\\(?:ref|eqref|pageref)\{([^{}]+)\}", tex)),
        "citations": sorted(re.findall(r"\\cite(?:\[[^\]]*\])?\{([^{}]+)\}", tex)),
    }


def compare_inventory(source: str, candidate: str) -> list[str]:
    expected = inventory(source)
    actual = inventory(candidate)
    return [f"{key}: expected {expected[key]!r}, got {actual[key]!r}" for key in expected if expected[key] != actual[key]]
