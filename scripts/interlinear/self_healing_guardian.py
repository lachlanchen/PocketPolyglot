#!/usr/bin/env python3
"""Guardian monitor for long interlinear book pipelines.

The guardian is intentionally conservative. It keeps normal worker scripts
moving with deterministic actions, and only launches a separate Codex repair
session when the pipeline code itself appears broken.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

CRITICAL_SCRIPTS = [
    "scripts/interlinear/codex_chunk_worker.py",
    "scripts/interlinear/codex_bilingual_parallel_json_worker.py",
    "scripts/interlinear/codex_parallel_review_worker.py",
    "scripts/interlinear/codex_sanitize_interlinear_range_worker.py",
    "scripts/interlinear/merge_parallel_json_candidates.py",
    "scripts/interlinear/merge_reviewed_chunks.py",
    "scripts/interlinear/repair_mechanical_furigana_candidate.py",
    "scripts/interlinear/repair_mechanical_furigana_prefix.py",
    "scripts/interlinear/monitor_interlinear_pipeline.py",
    "scripts/interlinear/monitor_sichuan_then_start_batch.py",
    "scripts/interlinear/self_healing_guardian.py",
]


@dataclass(frozen=True)
class BookProfile:
    book_id: str
    manifest: Path
    chunks_jsonl: Path
    raw_dir: Path
    reviewed_dir: Path
    gen_candidate_dir: Path
    gen_merged_dir: Path
    review_candidate_dir: Path
    review_merged_dir: Path
    review_rejected_dir: Path
    worker_session: str
    review_session: str
    sanitizer_session: str
    start_command: str
    sanitizer_command: str
    compile_command: str
    commit_command: str
    no_reviewed_stage: bool = False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(
    command: list[str] | str,
    *,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
    shell: bool | None = None,
) -> subprocess.CompletedProcess[str]:
    use_shell = isinstance(command, str) if shell is None else shell
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        shell=use_shell,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def tmux_active(session: str) -> bool:
    if not session:
        return False
    return (
        subprocess.run(
            ["tmux", "has-session", "-t", f"={session}"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def chunk_index(chunk_id: str) -> int | None:
    match = re.search(r"-chunk-(\d+)$", chunk_id)
    if not match:
        return None
    return int(match.group(1))


def report_progress(manifest: Path, chunk_dir: Path) -> dict[str, str]:
    if not manifest.exists():
        return {"manifest_chunks": "0", "valid_chunks": "0", "missing_chunks": "0", "error": f"missing {manifest}"}
    proc = run(
        [
            "python",
            "scripts/interlinear/report_interlinear_progress.py",
            "--manifest",
            str(manifest),
            "--chunk-dir",
            str(chunk_dir),
        ]
    )
    report = parse_key_values(proc.stdout)
    if proc.returncode:
        report["error"] = proc.stdout.strip()
    return report


def is_complete(report: dict[str, str]) -> bool:
    return (
        report.get("manifest_chunks") not in ("", "0", None)
        and report.get("manifest_chunks") == report.get("valid_chunks")
        and report.get("missing_chunks") == "0"
        and report.get("stale_chunks") == "0"
    )


def latest_mtime(paths: list[Path]) -> float:
    latest = 0.0
    for root in paths:
        if root.is_file():
            latest = max(latest, root.stat().st_mtime)
            continue
        if not root.exists():
            continue
        for item in root.rglob("*"):
            if item.is_file():
                latest = max(latest, item.stat().st_mtime)
    return latest


def profile_for(book_id: str) -> BookProfile:
    work = Path("books") / book_id / "work" / "bilingual"
    plan_path = Path("books") / book_id / "book-plan.json"
    worker_session = f"zhjpbook-{book_id}-json"

    if book_id == "sichuan-folk-stories-vol1":
        return BookProfile(
            book_id=book_id,
            manifest=work / "chunks" / "manifest.json",
            chunks_jsonl=work / "chunks" / "chunks.jsonl",
            raw_dir=work / "interlinear" / "chunks",
            reviewed_dir=work / "reviewed" / "chunks",
            gen_candidate_dir=work / "parallel-json" / "candidates",
            gen_merged_dir=work / "parallel-json" / "merged",
            review_candidate_dir=work / "parallel-review" / "candidates",
            review_merged_dir=work / "parallel-review" / "merged",
            review_rejected_dir=work / "parallel-review" / "merge-rejected",
            worker_session="zhjpbook-sichuan-folk-json",
            review_session="zhjpbook-sichuan-folk-json",
            sanitizer_session="",
            start_command="bash scripts/interlinear/start_sichuan_folk_parallel_json_tmux.sh zhjpbook-sichuan-folk-json",
            sanitizer_command="",
            compile_command="bash scripts/interlinear/compile_sichuan_folk_both_previews.sh",
            commit_command="bash scripts/interlinear/commit_sichuan_folk_progress.sh",
        )

    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        return BookProfile(
            book_id=book_id,
            manifest=Path(plan.get("chunks_manifest") or plan["manifest"]),
            chunks_jsonl=Path(plan["chunks_jsonl"]),
            raw_dir=Path(plan["raw_chunk_dir"]),
            reviewed_dir=Path(plan["reviewed_chunk_dir"]),
            gen_candidate_dir=work / "parallel-json" / "candidates",
            gen_merged_dir=work / "parallel-json" / "merged",
            review_candidate_dir=work / "parallel-review" / "candidates",
            review_merged_dir=work / "parallel-review" / "merged",
            review_rejected_dir=work / "parallel-review" / "merge-rejected",
            worker_session=worker_session,
            review_session=worker_session,
            sanitizer_session="",
            start_command=f"bash scripts/interlinear/start_prepared_book_parallel_json_tmux.sh {book_id} {worker_session}",
            sanitizer_command="",
            compile_command=f"bash scripts/interlinear/compile_prepared_book_both_previews.sh {book_id}",
            commit_command=f"bash scripts/interlinear/commit_prepared_book_progress.sh {book_id}",
        )

    raise SystemExit(f"No guardian profile for book: {book_id}")


def apply_overrides(profile: BookProfile, args: argparse.Namespace) -> BookProfile:
    updates: dict[str, Any] = {}
    for attr in (
        "worker_session",
        "review_session",
        "sanitizer_session",
        "start_command",
        "sanitizer_command",
        "compile_command",
        "commit_command",
    ):
        value = getattr(args, attr)
        if value:
            updates[attr] = value
    return replace(profile, **updates) if updates else profile


def compile_critical_scripts() -> tuple[bool, str]:
    scripts = [path for path in CRITICAL_SCRIPTS if (ROOT / path).exists()]
    proc = run(["python", "-m", "py_compile", *scripts])
    return proc.returncode == 0, proc.stdout


def merge(profile: BookProfile, compile_on_review_merge: bool) -> dict[str, Any]:
    for path in (
        profile.raw_dir,
        profile.gen_merged_dir,
        profile.reviewed_dir,
        profile.review_merged_dir,
        profile.review_rejected_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)

    raw_cmd = [
        "python",
        "scripts/interlinear/merge_parallel_json_candidates.py",
        "--chunks-jsonl",
        str(profile.chunks_jsonl),
        "--candidate-dir",
        str(profile.gen_candidate_dir),
        "--canonical-dir",
        str(profile.raw_dir),
        "--merged-dir",
        str(profile.gen_merged_dir),
    ]
    raw = run(raw_cmd)

    review_cmd = [
        "python",
        "scripts/interlinear/merge_reviewed_chunks.py",
        "--chunks-jsonl",
        str(profile.chunks_jsonl),
        "--candidate-dir",
        str(profile.review_candidate_dir),
        "--final-dir",
        str(profile.reviewed_dir),
        "--merged-dir",
        str(profile.review_merged_dir),
        "--rejected-dir",
        str(profile.review_rejected_dir),
    ]
    if compile_on_review_merge and profile.compile_command:
        review_cmd.extend(["--after-merge-command", profile.compile_command])
    reviewed = run(review_cmd)

    raw_values = parse_key_values(raw.stdout)
    reviewed_values = parse_key_values(reviewed.stdout)
    return {
        "raw_returncode": raw.returncode,
        "review_returncode": reviewed.returncode,
        "raw_output": raw.stdout[-8000:],
        "review_output": reviewed.stdout[-8000:],
        "raw_waiting_for": raw_values.get("waiting_for", ""),
        "review_waiting_for": reviewed_values.get("waiting_for", ""),
        "raw_merged_count": int(raw_values.get("merged_count", "0") or 0),
        "review_merged_count": int(reviewed_values.get("merged_reviewed_count", "0") or 0),
    }


def start_worker(profile: BookProfile, args: argparse.Namespace, first_missing: str) -> str:
    env = os.environ.copy()
    env.update({"MODEL": args.model, "REASONING": args.reasoning, "RETRY_FAILED": "1"})
    index = chunk_index(first_missing)
    if index:
        env["START_INDEX"] = str(index)
    proc = run(profile.start_command, env=env)
    return proc.stdout[-4000:]


def start_sanitizer(profile: BookProfile, args: argparse.Namespace, start_index: int, end_index: int) -> str:
    if not profile.sanitizer_command:
        return "no sanitizer command for this profile"
    env = os.environ.copy()
    env.update(
        {
            "START_INDEX": str(start_index),
            "END_INDEX": str(end_index),
            "SANITIZER_WORKERS": str(args.sanitizer_workers),
            "MODEL": args.model,
            "REASONING": args.reasoning,
            "RETRY_FAILED": "1",
        }
    )
    proc = run(profile.sanitizer_command, env=env)
    return proc.stdout[-4000:]


def state_marker(raw: dict[str, str], reviewed: dict[str, str], profile: BookProfile) -> dict[str, Any]:
    return {
        "raw": {key: raw.get(key, "") for key in ("valid_chunks", "missing_chunks", "stale_chunks", "first_missing", "last_valid")},
        "reviewed": {
            key: reviewed.get(key, "") for key in ("valid_chunks", "missing_chunks", "stale_chunks", "first_missing", "last_valid")
        },
        "worker_active": tmux_active(profile.worker_session),
        "review_active": tmux_active(profile.review_session),
        "sanitizer_active": tmux_active(profile.sanitizer_session) if profile.sanitizer_session else False,
        "latest_mtime": latest_mtime(
            [
                profile.raw_dir,
                profile.reviewed_dir,
                profile.gen_candidate_dir,
                profile.review_candidate_dir,
                Path("books") / profile.book_id / "work" / "logs",
            ]
        ),
    }


def launch_self_repair(
    profile: BookProfile,
    args: argparse.Namespace,
    state: dict[str, Any],
    reason: str,
    facts: dict[str, Any],
) -> str:
    if not args.allow_self_repair:
        return "self repair disabled"

    session = args.repair_session or f"zhjpbook-{profile.book_id}-guardian-repair"
    if tmux_active(session):
        return f"repair session already active: {session}"

    now = time.time()
    last = float(state.get("last_repair_started_at", 0) or 0)
    if now - last < args.repair_cooldown_seconds:
        return f"repair cooldown active: {int(now - last)}s/{args.repair_cooldown_seconds}s"

    repair_dir = Path("books") / profile.book_id / "work" / "guardian" / "self-repair"
    repair_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prompt_path = repair_dir / f"repair_{stamp}.md"
    message_path = repair_dir / f"repair_{stamp}.last-message.md"
    log_path = repair_dir / f"repair_{stamp}.log"
    run_path = repair_dir / f"repair_{stamp}.run.sh"

    prompt = f"""You are a Codex maintenance agent for /home/lachlan/ProjectsLFS/ZhJpBook.

Goal: fix the interlinear pipeline scripts so the book generation can continue safely.

Reason:
{reason}

Facts:
{json.dumps(facts, ensure_ascii=False, indent=2)}

Rules:
- Do not edit or commit original PDFs/EPUBs in sources/.
- Do not delete work artifacts or generated chunks.
- Prefer deterministic fixes to prompt churn.
- Validate script edits with python -m py_compile on the touched Python files.
- If you change tracked files, commit with a short imperative message.
- Keep the fix scoped to scripts/interlinear/, references/, or directly related tracked pipeline files.
- After fixing, report the verification commands and the next safe resume command.
"""
    prompt_path.write_text(prompt, encoding="utf-8")
    reasoning_config = f'model_reasoning_effort="{args.reasoning}"'
    run_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"cd {shlex.quote(str(ROOT))}",
                "codex exec "
                f"--cd {shlex.quote(str(ROOT))} "
                f"-m {shlex.quote(args.model)} "
                f"-c {shlex.quote(reasoning_config)} "
                "--dangerously-bypass-approvals-and-sandbox "
                f"--output-last-message {shlex.quote(str(message_path))} "
                f"- < {shlex.quote(str(prompt_path))} "
                f"2>&1 | tee {shlex.quote(str(log_path))}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run_path.chmod(0o755)
    proc = run(["tmux", "new-session", "-d", "-s", session, "-n", "repair", "bash", str(run_path)])
    if proc.returncode == 0:
        state["last_repair_started_at"] = now
        return f"started repair session: {session}"
    return f"failed to start repair session: {proc.stdout[-2000:]}"


def load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def complete_compile_marker(profile: BookProfile, reviewed: dict[str, str]) -> str:
    return json.dumps(
        {
            "book_id": profile.book_id,
            "manifest_chunks": reviewed.get("manifest_chunks", ""),
            "valid_chunks": reviewed.get("valid_chunks", ""),
            "last_valid": reviewed.get("last_valid", ""),
            "compile_command": profile.compile_command,
            "reviewed_mtime": latest_mtime([profile.reviewed_dir, profile.manifest]),
        },
        sort_keys=True,
    )


def guardian_once(args: argparse.Namespace, profile: BookProfile, state: dict[str, Any]) -> dict[str, Any]:
    actions: list[str] = []
    failures: list[str] = []

    compiled, compile_output = compile_critical_scripts()
    if not compiled:
        failures.append("critical Python script py_compile failed")
        actions.append(
            launch_self_repair(
                profile,
                args,
                state,
                "Critical Python scripts failed py_compile.",
                {"py_compile_output": compile_output},
            )
        )

    merge_result = merge(profile, args.compile_on_review_merge)
    if merge_result["raw_returncode"] or merge_result["review_returncode"]:
        failures.append("merge command failed")

    raw = report_progress(profile.manifest, profile.raw_dir)
    reviewed = raw if profile.no_reviewed_stage else report_progress(profile.manifest, profile.reviewed_dir)
    marker = state_marker(raw, reviewed, profile)
    marker_text = json.dumps(marker, sort_keys=True)
    now = time.time()
    if state.get("marker") != marker_text:
        state["marker"] = marker_text
        state["marker_since"] = now
    unchanged_for = int(now - float(state.get("marker_since", now)))
    reviewed_complete = is_complete(reviewed)

    if reviewed_complete and args.compile_when_complete and profile.compile_command and not failures:
        marker_for_compile = complete_compile_marker(profile, reviewed)
        if state.get("complete_compile_marker") != marker_for_compile:
            proc = run(profile.compile_command)
            actions.append(proc.stdout[-4000:])
            if proc.returncode:
                failures.append("compile_when_complete failed")
                actions.append(f"compile_when_complete_returncode={proc.returncode}")
            else:
                state["complete_compile_marker"] = marker_for_compile

    if not reviewed_complete:
        reviewed_valid = int(reviewed.get("valid_chunks", "0") or 0)
        waiting_for = merge_result.get("review_waiting_for") or merge_result.get("raw_waiting_for") or ""
        waiting_index = chunk_index(waiting_for)
        if (
            waiting_index
            and reviewed_valid >= waiting_index
            and profile.sanitizer_command
            and not tmux_active(profile.sanitizer_session)
        ):
            actions.append(f"start sanitizer {waiting_index}-{reviewed_valid}")
            actions.append(start_sanitizer(profile, args, waiting_index, reviewed_valid))

        if not tmux_active(profile.worker_session):
            first_missing = raw.get("first_missing") or reviewed.get("first_missing") or ""
            actions.append(f"start worker from {first_missing or 'default'}")
            actions.append(start_worker(profile, args, first_missing))

    facts = {
        "raw": raw,
        "reviewed": reviewed,
        "complete": reviewed_complete,
        "merge": merge_result,
        "marker": marker,
        "tmux": {
            "worker": tmux_active(profile.worker_session),
            "review": tmux_active(profile.review_session),
            "sanitizer": tmux_active(profile.sanitizer_session) if profile.sanitizer_session else False,
        },
    }
    if failures:
        actions.append(launch_self_repair(profile, args, state, "Pipeline command failed.", facts))

    if not reviewed_complete and unchanged_for >= args.stall_seconds:
        facts["unchanged_for"] = unchanged_for
        if not tmux_active(profile.worker_session) or failures:
            actions.append(launch_self_repair(profile, args, state, "Pipeline stalled or failed.", facts))
        elif unchanged_for >= args.active_stall_repair_seconds:
            actions.append(launch_self_repair(profile, args, state, "Pipeline remained unchanged while sessions stayed active.", facts))
        else:
            actions.append(f"stall observed but workers are active; gentle wait unchanged_for={unchanged_for}s")

    result = {
        "timestamp": now_iso(),
        "book_id": profile.book_id,
        "raw": raw,
        "reviewed": reviewed,
        "complete": reviewed_complete,
        "merge": merge_result,
        "marker": marker,
        "unchanged_for": unchanged_for,
        "actions": actions,
        "failures": failures,
    }
    state["last_result"] = result
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", default="sichuan-folk-stories-vol1")
    parser.add_argument("--interval-seconds", type=int, default=1800)
    parser.add_argument("--stall-seconds", type=int, default=3600)
    parser.add_argument("--active-stall-repair-seconds", type=int, default=21600)
    parser.add_argument("--model", default=os.environ.get("MODEL", "gpt-5.5"))
    parser.add_argument("--reasoning", default=os.environ.get("REASONING", "medium"))
    parser.add_argument("--sanitizer-workers", type=int, default=int(os.environ.get("SANITIZER_WORKERS", "4")))
    parser.add_argument("--worker-session", default="")
    parser.add_argument("--review-session", default="")
    parser.add_argument("--sanitizer-session", default="")
    parser.add_argument("--start-command", default="")
    parser.add_argument("--sanitizer-command", default="")
    parser.add_argument("--compile-command", default="")
    parser.add_argument("--commit-command", default="")
    parser.add_argument("--compile-on-review-merge", action="store_true")
    parser.add_argument("--compile-when-complete", action="store_true")
    parser.add_argument("--allow-self-repair", action="store_true")
    parser.add_argument("--repair-session", default="")
    parser.add_argument("--repair-cooldown-seconds", type=int, default=21600)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    profile = apply_overrides(profile_for(args.book_id), args)
    state_path = Path("books") / profile.book_id / "work" / "guardian" / "state.json"
    state = load_state(state_path)

    while True:
        result = guardian_once(args, profile, state)
        save_state(state_path, state)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        else:
            raw = result["raw"]
            reviewed = result["reviewed"]
            print(
                f"timestamp={result['timestamp']} book={profile.book_id} "
                f"raw={raw.get('valid_chunks','0')}/{raw.get('manifest_chunks','0')} "
                f"reviewed={reviewed.get('valid_chunks','0')}/{reviewed.get('manifest_chunks','0')} "
                f"waiting={result['merge'].get('review_waiting_for') or result['merge'].get('raw_waiting_for')} "
                f"unchanged_for={result['unchanged_for']} complete={int(result['complete'])}",
                flush=True,
            )
            for action in result["actions"]:
                print(f"action={action}", flush=True)
            for failure in result["failures"]:
                print(f"failure={failure}", flush=True)
        if args.once:
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
