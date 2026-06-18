#!/usr/bin/env python3
"""Prepare phase-specific manifests for incremental overlay backfill.

This does not run any model. It derives smaller global manifests from
data/source-plan/incremental-english-modern-japanese.json so workers can run
one phase at a time while preserving the additive overlay policy.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GLOBAL = ROOT / "data" / "source-plan" / "incremental-english-modern-japanese.json"
OUT_ROOT = ROOT / "data" / "source-plan" / "incremental-backfill-phases"

PHASE_ORDER = [
    "phase-1-normal-english",
    "phase-2-shiji-en-ja-modern",
    "phase-3-sishu-zhmodern-en-ja-modern",
]

PHASE_DESCRIPTIONS = {
    "phase-1-normal-english": "Normal modern bilingual books; add English only. Existing completed overlays are reused and skipped.",
    "phase-2-shiji-en-ja-modern": "Sima Qian Shiji; add English and readable modern Japanese from existing zh_modern.",
    "phase-3-sishu-zhmodern-en-ja-modern": "Sishu Jizhu; add modern Chinese bridge, then English and readable modern Japanese.",
}


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def phase_manifest(base: dict[str, Any], phase: str) -> dict[str, Any]:
    books = [
        book
        for book in sorted(base.get("books", []), key=lambda item: item.get("priority", 9999))
        if book.get("phase") == phase
    ]
    return {
        "schema_version": base.get("schema_version", 1),
        "task_family": f"{base.get('task_family', 'incremental_overlay')}.{phase}",
        "phase": phase,
        "phase_description": PHASE_DESCRIPTIONS.get(phase, ""),
        "old_json_is_read_only": True,
        "output_root": base.get("output_root"),
        "durable_overlay_root": base.get("durable_overlay_root"),
        "recommended_model": "gpt-5.5",
        "recommended_reasoning": "medium",
        "recommended_run_command": (
            f"MODEL=gpt-5.5 REASONING=medium GLOBAL_MANIFEST={rel(OUT_ROOT / (phase + '.json'))} "
            f"bash scripts/interlinear/start_incremental_overlay_tmux.sh zhjpbook-backfill-{phase}"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "books": books,
        "worker_contract": {
            **dict(base.get("worker_contract", {})),
            "run_one_phase_at_a_time": True,
            "phase_order": PHASE_ORDER,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--global-manifest", default=rel(DEFAULT_GLOBAL))
    parser.add_argument("--phase", action="append", choices=PHASE_ORDER)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base = load_json(ROOT / args.global_manifest)
    phases = args.phase or PHASE_ORDER
    for phase in phases:
        manifest = phase_manifest(base, phase)
        path = OUT_ROOT / f"{phase}.json"
        if not args.dry_run:
            write_json(path, manifest)
        total = sum(int(book.get("chunk_count", 0)) for book in manifest["books"])
        print(f"prepared {phase} books={len(manifest['books'])} chunks={total} manifest={rel(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
