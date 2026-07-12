#!/usr/bin/env python3
"""Compile exact/pocket textbook layers with a deterministic repair loop.

This wrapper is for OCR-heavy technical/music books. It runs the normal
``compile_textbook_exact_layers.py`` command, reads the first concrete LaTeX
failure, applies narrow persistent TeX fixes when the failure is recognizable,
and retries. If deterministic repair cannot classify the failure, it can launch
a small ``codex exec`` repair session with low reasoning when ``--allow-codex``
is set.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def run(cmd: list[str], *, check: bool = False, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=check,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def output_root(book_id: str, mode: str) -> Path:
    return ROOT / "build" / f"{book_id}-{mode}-exact-book"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compile_cmd(args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable,
        "scripts/interlinear/compile_textbook_exact_layers.py",
        "--mode",
        args.mode,
        "--book-id",
        args.book_id,
        "--passes",
        str(args.passes),
    ]
    if args.force_marker:
        cmd.append("--force-marker")
    if args.page_range:
        cmd.extend(["--page-range", args.page_range])
    return cmd


def latest_compile_log(book_id: str, mode: str) -> Path | None:
    root = output_root(book_id, mode)
    candidates = [
        root / "exact" / "compile-pass-1.log",
        root / "pocket" / "compile-pass-1.log",
        root / "exact" / f"{book_id}-{mode}-exact.log",
        root / "pocket" / f"{book_id}-{mode}-pocket.log",
    ]
    existing = [p for p in candidates if p.exists()]
    if not existing:
        logs = sorted(root.glob("**/*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        return logs[0] if logs else None
    return max(existing, key=lambda p: p.stat().st_mtime)


def parse_error(log_path: Path | None) -> dict[str, Any]:
    if log_path is None:
        return {"error": "no_compile_log"}
    text = log_path.read_text(encoding="utf-8", errors="replace")
    errors = list(re.finditer(r"(?m)^! (?P<error>.+)$", text))
    if not errors:
        return {"log": str(log_path.relative_to(ROOT)), "error": "unknown_compile_failure"}
    match = errors[-1]
    tail = text[match.start() : match.start() + 1400]
    line_match = re.search(r"(?m)^l\.(?P<line>\d+)\s*(?P<snippet>.*)$", tail)
    return {
        "log": str(log_path.relative_to(ROOT)),
        "error": match.group("error").strip(),
        "line": int(line_match.group("line")) if line_match else None,
        "snippet": line_match.group("snippet").strip() if line_match else "",
        "tail": tail.strip(),
    }


def body_path(book_id: str, mode: str) -> Path:
    return output_root(book_id, mode) / "work" / "body.tex"


def append_tex_fix(book_id: str, source: str, target: str, reason: str) -> bool:
    if not source or source == target:
        return False
    path = ROOT / "books" / book_id / "local-exact-tex-fixes.json"
    data = load_json(path)
    data.setdefault("generated_by", "compile_textbook_exact_autorepair.py")
    data.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    replacements = data.setdefault("replacements", [])
    for item in replacements:
        if item.get("from") == source and item.get("to") == target:
            return False
    replacements.append(
        {
            "from": source,
            "to": target,
            "regex": False,
            "reason": reason,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(path, data)
    return True


def wrap_text_mode_music_commands(text: str) -> str:
    commands = [r"\rightarrow", r"\leftarrow"]
    out: list[str] = []
    i = 0
    math_mode = False
    while i < len(text):
        pair = text[i : i + 2]
        if pair in {r"\(", r"\["}:
            math_mode = True
            out.append(pair)
            i += 2
            continue
        if pair in {r"\)", r"\]"}:
            math_mode = False
            out.append(pair)
            i += 2
            continue
        matched = False
        for command in commands:
            if text.startswith(command, i):
                out.append(command if math_mode else rf"\({command}\)")
                i += len(command)
                matched = True
                break
        if matched:
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def repair_music_line(line: str) -> str:
    repaired = line
    repaired = repaired.replace(r"\$\frac{1}{2}\$", r"\(\flat\)")
    repaired = repaired.replace(r"\frac{1}{2}\$", r"\(\flat\)")
    repaired = repaired.replace(r"\$\frac{4}{4}\$", r"\(\sharp\)")
    repaired = repaired.replace(r"\frac{4}{4}\$", r"\(\sharp\)")
    repaired = repaired.replace(r"\textbackslash sqrt\{", r"\(\flat")
    repaired = repaired.replace(r"\textbackslash\$5", r"5\)")
    repaired = repaired.replace(r"\sqrt{5}", r"\(\flat5\)")
    repaired = repaired.replace(r"\sqrt{VImaj7-vii}\^{}7", r"\(\flat\)VImaj7-vii°7")
    repaired = re.sub(r"\\\(\\flat([IVX]+)", r"\\(\\flat\\)\1", repaired)
    repaired = repaired.replace(r"IIImaj75\)", r"IIImaj7\(\sharp5\)")
    repaired = repaired.replace(r"\$\display\$", r"\(\flat9\)")
    repaired = repaired.replace(r"\$\frac{\*}{9}\$7", r"\#°7")
    repaired = repaired.replace(r"\$\frac{\*}{9}\$", r"\#")
    repaired = repaired.replace(r"\$9th", r"\(\flat9\)th")
    repaired = repaired.replace(r"\$5th", r"\(\flat5\)th")
    repaired = repaired.replace(r"\$7th\$", r"\(\flat7\)")
    repaired = wrap_text_mode_music_commands(repaired)
    repaired = repaired.replace(r"\ni", "i")
    repaired = re.sub(r"(?<!\\)#", r"\\#", repaired)
    repaired = repaired.translate(str.maketrans({"β": "♭", "Þ": "♭", "þ": "♭", "₽": "♭", "‡": "#", "μ": "♭"}))
    return repaired


def deterministic_repair(args: argparse.Namespace, error: dict[str, Any]) -> str:
    body = body_path(args.book_id, args.mode)
    if not body.exists():
        return "no_body_tex"
    line_no = error.get("line")
    if not isinstance(line_no, int):
        return "no_error_line"
    lines = body.read_text(encoding="utf-8", errors="replace").splitlines()
    if line_no < 1 or line_no > len(lines):
        return f"line_out_of_range={line_no}"
    original = lines[line_no - 1]
    repaired = repair_music_line(original)
    if repaired != original:
        added = append_tex_fix(args.book_id, original, repaired, f"{error.get('error')} at body line {line_no}")
        return "tex_fix_added" if added else "tex_fix_already_present"
    return "no_deterministic_rule"


def codex_prompt(args: argparse.Namespace, error: dict[str, Any], body_context: str) -> str:
    return f"""You are repairing an OCR-heavy textbook TeX compile pipeline.

Repository: {ROOT}
Book: {args.book_id}
Mode: {args.mode}

Goal:
- Make the compile command succeed by adding a narrow deterministic repair.
- Prefer editing books/{args.book_id}/local-exact-tex-fixes.json.
- Only edit scripts/interlinear/compile_textbook_exact_layers.py if the repair is broadly reusable.
- Do not touch sources/ or delete generated work.
- Run python3 -m py_compile on any edited Python file.

Compile command:
{shlex.join(compile_cmd(args))}

Observed LaTeX error:
{json.dumps(error, ensure_ascii=False, indent=2)}

Body context:
```tex
{body_context}
```

Return a concise summary of changed files and verification.
"""


def run_codex_repair(args: argparse.Namespace, error: dict[str, Any]) -> str:
    body = body_path(args.book_id, args.mode)
    line_no = error.get("line") if isinstance(error.get("line"), int) else 1
    lines = body.read_text(encoding="utf-8", errors="replace").splitlines() if body.exists() else []
    start = max(1, int(line_no) - 12)
    end = min(len(lines), int(line_no) + 12)
    context = "\n".join(f"{idx}: {lines[idx - 1]}" for idx in range(start, end + 1))
    repair_root = ROOT / "books" / args.book_id / "work" / "local-exact" / "autorepair"
    repair_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prompt_path = repair_root / f"{stamp}.prompt.md"
    log_path = repair_root / f"{stamp}.codex.log"
    last_message = repair_root / f"{stamp}.last-message.md"
    prompt = codex_prompt(args, error, context)
    prompt_path.write_text(prompt, encoding="utf-8")
    proc = run(
        [
            "codex",
            "exec",
            "-C",
            str(ROOT),
            "-m",
            args.codex_model,
            "-c",
            f'model_reasoning_effort="{args.codex_reasoning}"',
            "-s",
            "danger-full-access",
            "-a",
            "never",
            "-o",
            str(last_message),
            "-",
        ],
        input_text=prompt,
    )
    log_path.write_text(proc.stdout, encoding="utf-8", errors="replace")
    return f"codex_repair_exit={proc.returncode} log={log_path.relative_to(ROOT)}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--mode", choices=["mathpix", "local"], required=True)
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--force-marker", action="store_true")
    parser.add_argument("--page-range", default="")
    parser.add_argument("--max-rounds", type=int, default=8)
    parser.add_argument("--allow-codex", action="store_true")
    parser.add_argument("--codex-model", default=os.environ.get("TEXTBOOK_REPAIR_MODEL", "gpt-5.5"))
    parser.add_argument("--codex-reasoning", default=os.environ.get("TEXTBOOK_REPAIR_REASONING", "low"))
    args = parser.parse_args()

    history: list[dict[str, Any]] = []
    for round_no in range(1, args.max_rounds + 1):
        proc = run(compile_cmd(args))
        history.append({"round": round_no, "returncode": proc.returncode, "stdout_tail": proc.stdout[-1600:]})
        if proc.returncode == 0:
            print(proc.stdout)
            write_json(output_root(args.book_id, args.mode) / "autorepair-history.json", {"status": "ok", "history": history})
            return 0
        error = parse_error(latest_compile_log(args.book_id, args.mode))
        action = deterministic_repair(args, error)
        history[-1]["error"] = error
        history[-1]["action"] = action
        print(f"round={round_no} failed action={action} error={error.get('error')} line={error.get('line')}", flush=True)
        if action == "tex_fix_added":
            continue
        if args.allow_codex:
            codex_action = run_codex_repair(args, error)
            history[-1]["codex_action"] = codex_action
            print(codex_action, flush=True)
            continue
        break
    write_json(output_root(args.book_id, args.mode) / "autorepair-history.json", {"status": "failed", "history": history})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
