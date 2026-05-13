#!/usr/bin/env python3
"""Validate the interlinear JSON structure and source-text preservation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    return SPACE_RE.sub("", text or "")


def token_text(tokens: list[dict[str, Any]]) -> str:
    return "".join(str(token.get("t", "")) for token in tokens)


def validate_unit(unit: dict[str, Any], where: str, errors: list[str]) -> str:
    if "zh" not in unit or not isinstance(unit["zh"], list):
        errors.append(f"{where}: missing zh token list")
        return ""
    for token_index, token in enumerate(unit["zh"]):
        if not isinstance(token, dict) or "t" not in token:
            errors.append(f"{where}.zh[{token_index}]: token must contain t")
    ja = unit.get("ja")
    if not isinstance(ja, list) or len(ja) != 2:
        errors.append(f"{where}: ja must contain exactly two line arrays")
    else:
        for line_index, line in enumerate(ja):
            if not isinstance(line, list):
                errors.append(f"{where}.ja[{line_index}]: line must be a token list")
                continue
            for token_index, token in enumerate(line):
                if not isinstance(token, dict) or "t" not in token:
                    errors.append(f"{where}.ja[{line_index}][{token_index}]: token must contain t")
    zh_text = token_text(unit["zh"])
    if unit.get("source_text") and normalize(zh_text) != normalize(str(unit["source_text"])):
        errors.append(f"{where}: zh tokens do not reconstruct source_text")
    return zh_text


def validate_interlinear(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("mode") != "zh_main_ja_comment":
        errors.append("mode must be zh_main_ja_comment")
    if not isinstance(data.get("sections"), list):
        errors.append("sections must be a list")
        return errors

    for section_index, section in enumerate(data["sections"]):
        for subsection_index, subsection in enumerate(section.get("subsections", [])):
            for story_index, story in enumerate(subsection.get("stories", [])):
                for paragraph_index, paragraph in enumerate(story.get("paragraphs", [])):
                    where = f"sections[{section_index}].subsections[{subsection_index}].stories[{story_index}].paragraphs[{paragraph_index}]"
                    units = paragraph.get("units")
                    if not isinstance(units, list) or not units:
                        errors.append(f"{where}: missing units")
                        continue
                    rebuilt = "".join(validate_unit(unit, f"{where}.units[{unit_index}]", errors) for unit_index, unit in enumerate(units))
                    if paragraph.get("source_text") and normalize(rebuilt) != normalize(str(paragraph["source_text"])):
                        errors.append(f"{where}: units do not reconstruct paragraph source_text")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path")
    args = parser.parse_args()

    data = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    errors = validate_interlinear(data)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
