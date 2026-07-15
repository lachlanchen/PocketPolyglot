from __future__ import annotations

import glob
import json
import subprocess
from pathlib import Path
from typing import Any


def _resolve(repo_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else repo_root / path


def evaluate_check(repo_root: Path, check: dict[str, Any]) -> dict[str, Any]:
    kind = check.get("type", "path_exists")
    label = check.get("label") or kind.replace("_", " ").title()
    result: dict[str, Any] = {"check_type": kind, "label": label, "passed": False, "detail": ""}

    if kind == "exit_code":
        actual = int(check.get("actual", -999))
        expected = int(check.get("expected", 0))
        result.update(passed=actual == expected, detail=f"exit_code={actual}, expected={expected}")
        return result

    if kind == "path_exists":
        path = _resolve(repo_root, check["path"])
        minimum = int(check.get("min_bytes", 1))
        passed = path.is_file() and path.stat().st_size >= minimum
        result.update(
            passed=passed,
            detail=f"{path} ({path.stat().st_size if path.exists() else 0} bytes)",
            artifact_path=str(path) if passed else "",
        )
        return result

    if kind == "glob_min":
        pattern_path = _resolve(repo_root, check["pattern"])
        matches = [Path(path) for path in glob.glob(str(pattern_path), recursive=True)]
        minimum = int(check.get("minimum", 1))
        result.update(passed=len(matches) >= minimum, detail=f"matches={len(matches)}, minimum={minimum}")
        if matches:
            result["artifact_path"] = str(matches[0])
        return result

    if kind == "json_field":
        path = _resolve(repo_root, check["path"])
        try:
            value: Any = json.loads(path.read_text(encoding="utf-8"))
            for segment in check["field"].split("."):
                value = value[segment]
            expected = check.get("equals")
            passed = value == expected
            result.update(passed=passed, detail=f"{check['field']}={value!r}, expected={expected!r}")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            result["detail"] = str(error)
        return result

    if kind == "command":
        argv = [str(item) for item in check.get("argv", [])]
        if not argv:
            result["detail"] = "missing argv"
            return result
        process = subprocess.run(
            argv,
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=int(check.get("timeout", 300)),
            check=False,
        )
        expected_text = check.get("contains", "")
        passed = process.returncode == int(check.get("returncode", 0))
        if expected_text:
            passed = passed and expected_text in process.stdout
        result.update(passed=passed, detail=process.stdout[-4000:] or f"returncode={process.returncode}")
        return result

    result["detail"] = f"unknown evidence check: {kind}"
    return result


def evaluate_all(repo_root: Path, checks: list[dict[str, Any]], exit_code: int) -> list[dict[str, Any]]:
    runtime_checks = [
        {"type": "exit_code", "label": "Command exited successfully", "actual": exit_code, "expected": 0}
    ]
    runtime_checks.extend(checks)
    return [evaluate_check(repo_root, check) for check in runtime_checks]
