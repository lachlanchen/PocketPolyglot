#!/usr/bin/env python3
"""Generic low-cost autorepair companion for long tmux jobs.

The companion is intentionally task-neutral.  It watches a primary tmux
session, a cheap health command, and artifact paths.  It restarts deterministic
work when that is enough, and launches a scoped ``codex exec`` repair session
only when there is strong evidence that pipeline code or orchestration is
broken.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

ERROR_PATTERNS = re.compile(
    r"(?i)(traceback|syntaxerror|moduleNotFoundError|importError|nameError|"
    r"typeError|keyError|fileNotFoundError|no such file or directory|"
    r"command not found|jq: error|latex error|emergency stop)"
)

USAGE_LIMIT_BACKOFF_PATTERNS = re.compile(
    r"(?i)(codex usage limit detected; sleeping \d+s? before retry|"
    r"usage limit detected; sleeping|"
    r"usage limit.*before retry)"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_shell(command: str, *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def run_args(command: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
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
    pattern = re.compile(r"([A-Za-z0-9_.-]+)=([^=]*?)(?=\s+[A-Za-z0-9_.-]+=|$)")
    for line in text.splitlines():
        for key, value in pattern.findall(line):
            values[key.strip()] = value.strip()
    return values


def sha256_short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit // 2] + "\n...[truncated]...\n" + text[-limit // 2 :]


def expand_paths(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        if any(char in pattern for char in "*?[]"):
            paths.extend(sorted(ROOT.glob(pattern)))
        else:
            paths.append(ROOT / pattern if not Path(pattern).is_absolute() else Path(pattern))
    return paths


def latest_mtime(patterns: list[str]) -> float:
    latest = 0.0
    for path in expand_paths(patterns):
        if not path.exists():
            continue
        if path.is_file():
            latest = max(latest, path.stat().st_mtime)
            continue
        for item in path.rglob("*"):
            if item.is_file():
                latest = max(latest, item.stat().st_mtime)
    return latest


def recent_usage_limit_backoff(log_text: str, log_mtime: float, *, active_seconds: int) -> bool:
    """Return True when workers are recently waiting for external Codex quota.

    Active quota backoff intentionally produces no chunk artifacts for long
    periods. Treating that as a pipeline stall launches unnecessary repair
    agents, so suppress only while matching logs are still fresh.
    """
    if active_seconds <= 0:
        return False
    if not USAGE_LIMIT_BACKOFF_PATTERNS.search(log_text[-8000:]):
        return False
    return bool(log_mtime and time.time() - log_mtime <= active_seconds)


def tail_logs(patterns: list[str], *, lines: int, max_chars: int) -> str:
    chunks: list[str] = []
    for path in expand_paths(patterns):
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
        except OSError:
            continue
        chunks.append(f"== {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path} ==\n" + "\n".join(text))
    return truncate("\n\n".join(chunks), max_chars)


def py_compile(paths: list[str], timeout: int) -> tuple[bool, str]:
    if not paths:
        return True, ""
    existing = [str(path) for path in expand_paths(paths) if path.exists() and path.is_file()]
    if not existing:
        return True, ""
    proc = run_args(["python", "-m", "py_compile", *existing], timeout=timeout)
    return proc.returncode == 0, proc.stdout


def split_assignment(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got {value!r}")
    key, expected = value.split("=", 1)
    return key.strip(), expected.strip()


def complete_from_keys(report: dict[str, str], key_values: list[tuple[str, str]], key_eq: list[tuple[str, str]], ratios: list[str]) -> bool:
    if not (key_values or key_eq or ratios):
        return False
    for key, expected in key_values:
        if report.get(key) != expected:
            return False
    for left, right in key_eq:
        if not report.get(left) or report.get(left) != report.get(right):
            return False
    for key in ratios:
        value = report.get(key, "")
        if "/" not in value:
            return False
        done, total = value.split("/", 1)
        if total in {"", "0"} or done != total:
            return False
    return True


def progress_fingerprint(args: argparse.Namespace, report: dict[str, str], health_stdout: str, watched_mtime: float, complete: bool) -> dict[str, Any]:
    if args.progress_key:
        return {
            "progress": {key: report.get(key, "") for key in args.progress_key},
            "watched_mtime": int(watched_mtime),
            "complete": complete,
        }
    return {
        "health_hash": sha256_short(health_stdout),
        "watched_mtime": int(watched_mtime),
        "complete": complete,
    }


def first_missing_index(report: dict[str, str]) -> str:
    value = report.get("first_missing", "")
    if not value:
        return ""
    first = value.split(",", 1)[0].strip()
    match = re.search(r"(\d+)(?!.*\d)", first)
    if not match:
        return ""
    return str(int(match.group(1)))


def render_command_template(template: str, report: dict[str, str]) -> str:
    rendered = template.replace("{first_missing_index}", shlex.quote(first_missing_index(report)))
    rendered = rendered.replace("{first_missing}", shlex.quote(report.get("first_missing", "").split(",", 1)[0].strip()))
    for key, value in report.items():
        rendered = rendered.replace("{health." + key + "}", shlex.quote(value))
    return rendered


def classify_reasoning(state: dict[str, Any], reason: str, *, max_reasoning: str) -> str:
    order = ["low", "medium", "high", "xhigh"]
    max_index = order.index(max_reasoning) if max_reasoning in order else order.index("high")
    repair_count = len(state.get("repairs", []))
    if "py_compile" in reason or "crashed" in reason or "start command failed" in reason:
        index = 0 if repair_count == 0 else 1
    elif "active stall" in reason:
        index = 1 if repair_count < 2 else 2
    else:
        index = 1
    if repair_count >= 3:
        index = max(index, 2)
    if repair_count >= 5:
        index = max(index, 3)
    return order[min(index, max_index)]


def launch_repair(args: argparse.Namespace, state: dict[str, Any], reason: str, facts: dict[str, Any]) -> str:
    if not args.allow_repair:
        return "repair_skipped=disabled"
    if len(state.get("repairs", [])) >= args.max_repairs:
        return f"repair_skipped=max_repairs_reached({args.max_repairs})"
    if args.repair_session and tmux_active(args.repair_session):
        return f"repair_skipped=session_active({args.repair_session})"

    now = time.time()
    last = float(state.get("last_repair_started_at", 0) or 0)
    if now - last < args.repair_cooldown_seconds:
        return f"repair_skipped=cooldown({int(now - last)}/{args.repair_cooldown_seconds})"

    reasoning = classify_reasoning(state, reason, max_reasoning=args.max_repair_reasoning)
    session = args.repair_session or f"{args.name}-autorepair-fix"
    repair_root = Path(args.state_dir) / "repairs"
    repair_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prompt_path = repair_root / f"{stamp}.prompt.md"
    run_path = repair_root / f"{stamp}.run.sh"
    log_path = repair_root / f"{stamp}.log"
    last_message = repair_root / f"{stamp}.last-message.md"

    facts_text = truncate(json.dumps(facts, ensure_ascii=False, indent=2), args.max_evidence_chars)
    prompt = f"""You are a Codex repair agent for this repository.

Repository: {ROOT}
Companion: {args.name}
Reason: {reason}

Evidence:
{facts_text}

Repair rules:
- Fix the general pipeline/orchestration code when the evidence points to a code fault.
- Prefer small deterministic fixes over prompt churn or broad rewrites.
- Do not edit or commit original PDFs/EPUBs or anything under sources/.
- Do not delete generated work artifacts, accepted candidates, or chunk JSON.
- Keep the fix scoped to tracked scripts, templates, documentation, or directly related task metadata.
- Validate touched Python with python -m py_compile.
- If tracked files change, commit with a short imperative message.
- If no code change is justified, explain the safe resume command instead.
"""
    prompt_path.write_text(prompt, encoding="utf-8")
    reasoning_config = f'model_reasoning_effort="{reasoning}"'
    run_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"cd {shlex.quote(str(ROOT))}",
                "codex exec "
                f"--cd {shlex.quote(str(ROOT))} "
                f"-m {shlex.quote(args.repair_model)} "
                f"-c {shlex.quote(reasoning_config)} "
                "--dangerously-bypass-approvals-and-sandbox "
                f"--output-last-message {shlex.quote(str(last_message))} "
                f"- < {shlex.quote(str(prompt_path))} "
                f"2>&1 | tee {shlex.quote(str(log_path))}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run_path.chmod(0o755)
    proc = run_args(["tmux", "new-session", "-d", "-s", session, "-n", "repair", "bash", str(run_path)])
    if proc.returncode:
        return f"repair_start_failed={truncate(proc.stdout, 1000)}"
    record = {"time": now_iso(), "reason": reason, "session": session, "model": args.repair_model, "reasoning": reasoning}
    state.setdefault("repairs", []).append(record)
    state["last_repair_started_at"] = now
    return f"repair_started={session} model={args.repair_model} reasoning={reasoning}"


def load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def companion_once(args: argparse.Namespace, state: dict[str, Any]) -> dict[str, Any]:
    actions: list[str] = []
    failures: list[str] = []

    health_stdout = ""
    health_returncode = 0
    health_error = ""
    if args.health_command:
        try:
            health = run_shell(args.health_command, timeout=args.health_timeout_seconds)
            health_stdout = health.stdout
            health_returncode = health.returncode
        except subprocess.TimeoutExpired as exc:
            health_returncode = 124
            health_stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            health_error = f"health_timeout={args.health_timeout_seconds}"

    report = parse_key_values(health_stdout)
    complete = complete_from_keys(report, args.complete_key, args.complete_key_eq, args.complete_ratio)
    active = tmux_active(args.primary_session)
    watched_mtime = latest_mtime(args.watch)
    log_mtime = latest_mtime(args.log)
    fingerprint = progress_fingerprint(args, report, health_stdout, watched_mtime, complete)
    if state.get("progress_fingerprint") != fingerprint:
        state["progress_fingerprint"] = fingerprint
        state["progress_since"] = time.time()
    unchanged_for = int(time.time() - float(state.get("progress_since", time.time())))

    compile_ok, compile_output = py_compile(args.py_compile, args.command_timeout_seconds)
    health_ok = health_returncode == 0 or args.health_nonzero_ok
    if not health_ok:
        failures.append(f"health_returncode={health_returncode}")
    if health_error:
        failures.append(health_error)
    if not compile_ok:
        failures.append("py_compile_failed")
    recent_logs = tail_logs(args.log, lines=args.evidence_lines, max_chars=args.max_evidence_chars)
    usage_limit_backoff = recent_usage_limit_backoff(
        recent_logs,
        log_mtime,
        active_seconds=args.usage_limit_active_seconds,
    )
    error_like = bool(ERROR_PATTERNS.search("\n".join([health_stdout[-4000:], recent_logs[-4000:], compile_output[-4000:]])))

    if complete:
        actions.append("complete=1")
    elif not compile_ok:
        facts = {
            "health": {"returncode": health_returncode, "stdout": truncate(health_stdout, 4000), "parsed": report},
            "py_compile": truncate(compile_output, 6000),
            "logs": recent_logs,
            "git_status": run_args(["git", "status", "--short"], timeout=30).stdout,
        }
        actions.append(launch_repair(args, state, "py_compile failed", facts))
    elif not active and args.start_command:
        last_start = float(state.get("last_start_at", 0) or 0)
        if time.time() - last_start >= args.start_cooldown_seconds:
            start_command = render_command_template(args.start_command, report)
            start = run_shell(start_command, timeout=args.start_timeout_seconds)
            state["last_start_at"] = time.time()
            actions.append(f"start_command_returncode={start.returncode}")
            actions.append(truncate(start.stdout, 2000))
            if start.returncode:
                facts = {
                    "health": {"returncode": health_returncode, "stdout": truncate(health_stdout, 4000), "parsed": report},
                    "start_command": start_command,
                    "start_output": truncate(start.stdout, 5000),
                    "logs": recent_logs,
                }
                actions.append(launch_repair(args, state, "start command failed", facts))
        else:
            actions.append("start_skipped=cooldown")
    elif failures and error_like:
        facts = {
            "health": {"returncode": health_returncode, "stdout": truncate(health_stdout, 5000), "parsed": report},
            "logs": recent_logs,
            "failures": failures,
        }
        actions.append(launch_repair(args, state, "health command crashed", facts))
    elif not complete and usage_limit_backoff and active:
        actions.append(f"usage_limit_backoff active=1 unchanged_for={unchanged_for}s")
    elif not complete and unchanged_for >= args.active_stall_seconds and active:
        facts = {
            "health": {"returncode": health_returncode, "stdout": truncate(health_stdout, 5000), "parsed": report},
            "primary_session": args.primary_session,
            "unchanged_for": unchanged_for,
            "watched_paths": args.watch,
            "logs": recent_logs,
            "ps": run_shell(f"ps -eo pid,ppid,stat,etime,cmd | rg {shlex.quote(args.name)} || true", timeout=30).stdout,
        }
        actions.append(launch_repair(args, state, "active stall without artifact progress", facts))
    elif not complete and unchanged_for >= args.stall_seconds:
        actions.append(f"stall_observed={unchanged_for}s active={int(active)}")
    else:
        actions.append(f"healthy_wait active={int(active)} unchanged_for={unchanged_for}s")

    result = {
        "timestamp": now_iso(),
        "name": args.name,
        "primary_session": args.primary_session,
        "active": active,
        "complete": complete,
        "health_returncode": health_returncode,
        "health": report,
        "watched_mtime": watched_mtime,
        "log_mtime": log_mtime,
        "usage_limit_backoff": usage_limit_backoff,
        "unchanged_for": unchanged_for,
        "failures": failures,
        "actions": actions,
    }
    state["last_result"] = result
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--primary-session", default="")
    parser.add_argument("--health-command", default="")
    parser.add_argument("--health-nonzero-ok", action="store_true")
    parser.add_argument("--complete-key", action="append", type=split_assignment, default=[])
    parser.add_argument("--complete-key-eq", action="append", type=split_assignment, default=[])
    parser.add_argument("--complete-ratio", action="append", default=[])
    parser.add_argument("--progress-key", action="append", default=[], help="Health report keys that define forward progress")
    parser.add_argument("--watch", action="append", default=[])
    parser.add_argument("--log", action="append", default=[])
    parser.add_argument("--py-compile", action="append", default=[])
    parser.add_argument("--start-command", default="")
    parser.add_argument("--allow-repair", action="store_true")
    parser.add_argument("--repair-session", default="")
    parser.add_argument("--repair-model", default=os.environ.get("AUTOREPAIR_MODEL", "gpt-5.5"))
    parser.add_argument("--max-repair-reasoning", default=os.environ.get("AUTOREPAIR_MAX_REASONING", "high"))
    parser.add_argument("--max-repairs", type=int, default=int(os.environ.get("AUTOREPAIR_MAX_REPAIRS", "8")))
    parser.add_argument("--interval-seconds", type=int, default=int(os.environ.get("AUTOREPAIR_INTERVAL_SECONDS", "600")))
    parser.add_argument("--stall-seconds", type=int, default=int(os.environ.get("AUTOREPAIR_STALL_SECONDS", "1800")))
    parser.add_argument("--active-stall-seconds", type=int, default=int(os.environ.get("AUTOREPAIR_ACTIVE_STALL_SECONDS", "7200")))
    parser.add_argument(
        "--usage-limit-active-seconds",
        type=int,
        default=int(os.environ.get("AUTOREPAIR_USAGE_LIMIT_ACTIVE_SECONDS", "14400")),
        help="Suppress active-stall repair while recent logs show Codex usage-limit retry backoff.",
    )
    parser.add_argument("--repair-cooldown-seconds", type=int, default=int(os.environ.get("AUTOREPAIR_COOLDOWN_SECONDS", "7200")))
    parser.add_argument("--start-cooldown-seconds", type=int, default=int(os.environ.get("AUTOREPAIR_START_COOLDOWN_SECONDS", "1200")))
    parser.add_argument("--health-timeout-seconds", type=int, default=120)
    parser.add_argument("--start-timeout-seconds", type=int, default=600)
    parser.add_argument("--command-timeout-seconds", type=int, default=120)
    parser.add_argument("--evidence-lines", type=int, default=120)
    parser.add_argument("--max-evidence-chars", type=int, default=12000)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    state_path = Path(args.state_dir) / "state.json"
    state = load_state(state_path)
    while True:
        result = companion_once(args, state)
        save_state(state_path, state)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        else:
            print(
                f"timestamp={result['timestamp']} name={args.name} active={int(result['active'])} "
                f"complete={int(result['complete'])} unchanged_for={result['unchanged_for']} "
                f"health_returncode={result['health_returncode']}",
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
