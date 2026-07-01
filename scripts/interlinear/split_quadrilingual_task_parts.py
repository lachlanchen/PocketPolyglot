#!/usr/bin/env python3
"""Split a prepared quadrilingual task into chapter-contiguous launch parts."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def chapter_groups(chunks: list[dict]) -> list[tuple[int, dict]]:
    groups: OrderedDict[int, dict] = OrderedDict()
    for index, chunk in enumerate(chunks, start=1):
        chapter = int(chunk["chapter_number"])
        item = groups.setdefault(
            chapter,
            {
                "count": 0,
                "first_index": index,
                "last_index": index,
                "first_chunk_id": chunk["chunk_id"],
                "last_chunk_id": chunk["chunk_id"],
                "chapter_title_wenyan": chunk.get("chapter_title_wenyan"),
            },
        )
        item["count"] += 1
        item["last_index"] = index
        item["last_chunk_id"] = chunk["chunk_id"]
    return list(groups.items())


def split_balanced(groups: list[tuple[int, dict]], parts: int) -> list[tuple[int, int]]:
    if parts < 1:
        raise ValueError("parts must be >= 1")
    if parts > len(groups):
        raise ValueError("parts cannot exceed chapter count")
    ranges: list[tuple[int, int]] = []
    start = 0
    for part_no in range(1, parts):
        remaining_parts = parts - part_no + 1
        remaining_count = sum(group["count"] for _, group in groups[start:])
        target = remaining_count / remaining_parts
        best: tuple[float, int] | None = None
        acc = 0
        max_end = len(groups) - remaining_parts
        for end in range(start, max_end + 1):
            acc += groups[end][1]["count"]
            score = abs(acc - target)
            if best is None or score < best[0]:
                best = (score, end)
        assert best is not None
        ranges.append((start, best[1]))
        start = best[1] + 1
    ranges.append((start, len(groups) - 1))
    return ranges


def launch_script(
    *,
    book_id: str,
    part_no: int,
    total_parts: int,
    part_dir: Path,
    start_index: int,
    end_index: int,
) -> str:
    part = f"part-{part_no:02d}"
    manifest = part_dir / "manifest.json"
    work_root = part_dir / "parallel-json"
    return f"""#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git -C "$(dirname "${{BASH_SOURCE[0]}}")" rev-parse --show-toplevel)"
cd "$ROOT"

SESSION="${{1:-zhjpbook-{book_id}-{part}-100-low}}"

WORKERS="${{WORKERS:-100}}" \\
MODEL="${{MODEL:-gpt-5.5}}" \\
REASONING="${{REASONING:-low}}" \\
CLAIM_TTL_SECONDS="${{CLAIM_TTL_SECONDS:-1800}}" \\
CODEX_TIMEOUT_SECONDS="${{CODEX_TIMEOUT_SECONDS:-1200}}" \\
CODEX_EXEC_IGNORE_USER_CONFIG="${{CODEX_EXEC_IGNORE_USER_CONFIG:-1}}" \\
CODEX_EXEC_IGNORE_RULES="${{CODEX_EXEC_IGNORE_RULES:-1}}" \\
MAIN_LAYERS="${{MAIN_LAYERS:-wenyan}}" \\
START_INDEX="{start_index}" \\
END_INDEX="{end_index}" \\
MANIFEST_OVERRIDE="{manifest.as_posix()}" \\
WORK_ROOT_OVERRIDE="{work_root.as_posix()}" \\
scripts/interlinear/start_quadrilingual_wenyan_tmux.sh "{book_id}" "$SESSION"
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_id")
    parser.add_argument("--parts", type=int, default=3)
    parser.add_argument("--output-root")
    args = parser.parse_args()

    book_id = args.book_id
    plan_path = Path("books") / book_id / "book-plan.json"
    plan = load_json(plan_path)
    chunks_jsonl = Path(plan["chunks_jsonl"])
    full_manifest_path = Path(plan["chunks_manifest"])
    full_manifest = load_json(full_manifest_path)
    chunks = load_jsonl(chunks_jsonl)
    groups = chapter_groups(chunks)
    ranges = split_balanced(groups, args.parts)
    output_root = Path(args.output_root or f"books/{book_id}/work/quadrilingual/parts")
    generated_at = datetime.now(timezone.utc).isoformat()

    summary = {
        "schema_version": 1,
        "book_id": book_id,
        "parts": args.parts,
        "source_manifest": full_manifest_path.as_posix(),
        "source_chunks_jsonl": chunks_jsonl.as_posix(),
        "generated_at": generated_at,
        "part_manifests": [],
    }

    for number, (group_start, group_end) in enumerate(ranges, start=1):
        selected_groups = groups[group_start : group_end + 1]
        first = selected_groups[0][1]
        last = selected_groups[-1][1]
        start_index = int(first["first_index"])
        end_index = int(last["last_index"])
        selected_chunks = chunks[start_index - 1 : end_index]
        part_dir = output_root / f"part-{number:02d}"

        manifest = dict(full_manifest)
        manifest["status"] = "prepared_part"
        manifest["part"] = {
            "part_number": number,
            "part_count": args.parts,
            "start_index": start_index,
            "end_index": end_index,
            "first_chunk_id": selected_chunks[0]["chunk_id"],
            "last_chunk_id": selected_chunks[-1]["chunk_id"],
            "first_chapter_number": selected_groups[0][0],
            "last_chapter_number": selected_groups[-1][0],
            "first_chapter_title_wenyan": first.get("chapter_title_wenyan"),
            "last_chapter_title_wenyan": last.get("chapter_title_wenyan"),
            "source_manifest": full_manifest_path.as_posix(),
            "source_chunks_jsonl": chunks_jsonl.as_posix(),
        }
        manifest["chunk_count"] = len(selected_chunks)
        manifest["chapter_count"] = len(selected_groups)
        manifest["chunks"] = [
            {"chunk_id": chunk["chunk_id"], "chapter_number": chunk["chapter_number"]}
            for chunk in selected_chunks
        ]
        write_json(part_dir / "manifest.json", manifest)

        script_path = part_dir / "start_part.sh"
        script_path.write_text(
            launch_script(
                book_id=book_id,
                part_no=number,
                total_parts=args.parts,
                part_dir=part_dir,
                start_index=start_index,
                end_index=end_index,
            ),
            encoding="utf-8",
        )
        script_path.chmod(0o755)

        summary["part_manifests"].append(
            {
                "part": number,
                "manifest": (part_dir / "manifest.json").as_posix(),
                "start_script": script_path.as_posix(),
                "start_index": start_index,
                "end_index": end_index,
                "chunk_count": len(selected_chunks),
                "chapter_count": len(selected_groups),
                "chapter_range": [selected_groups[0][0], selected_groups[-1][0]],
                "first_chapter_title_wenyan": first.get("chapter_title_wenyan"),
                "last_chapter_title_wenyan": last.get("chapter_title_wenyan"),
                "chunk_range": [selected_chunks[0]["chunk_id"], selected_chunks[-1]["chunk_id"]],
            }
        )

    write_json(output_root / "split-summary.json", summary)
    for item in summary["part_manifests"]:
        print(
            f"part-{item['part']:02d}: chapters {item['chapter_range'][0]}-{item['chapter_range'][1]} "
            f"chunks {item['chunk_count']} indices {item['start_index']}-{item['end_index']}"
        )
    print(f"summary={output_root / 'split-summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
