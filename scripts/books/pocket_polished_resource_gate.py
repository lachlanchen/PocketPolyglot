#!/usr/bin/env python3
"""Cross-process capacity gate and lightweight host/network telemetry."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_network_bytes() -> int:
    total = 0
    try:
        lines = Path("/proc/net/dev").read_text(encoding="utf-8").splitlines()[2:]
    except OSError:
        return 0
    for line in lines:
        interface, values = line.split(":", 1)
        if interface.strip() == "lo":
            continue
        fields = values.split()
        if len(fields) >= 9:
            total += int(fields[0]) + int(fields[8])
    return total


def read_available_memory_mb() -> float:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def active_slots(state_path: Path) -> int:
    slots = state_path.parent / f"{state_path.stem}.slots"
    count = 0
    for path in slots.glob("slot-*.lock"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            pid = int(payload.get("pid", 0))
        except (OSError, ValueError, json.JSONDecodeError, AttributeError):
            pid = 0
        if pid and process_is_alive(pid):
            count += 1
        else:
            path.unlink(missing_ok=True)
    return count


@dataclass
class AdaptiveGovernor:
    state_path: Path
    max_concurrency: int
    network_limit_mbps: float = 100.0
    load_limit_ratio: float = 1.25
    memory_floor_mb: float = 2048.0

    def __post_init__(self) -> None:
        self.max_concurrency = max(1, self.max_concurrency)
        self._last_at = time.monotonic()
        self._last_network_bytes = read_network_bytes()
        self._busy_samples = 0
        self._clear_samples = 0

    def sample(self) -> dict:
        now = time.monotonic()
        network_bytes = read_network_bytes()
        elapsed = max(0.001, now - self._last_at)
        network_mbps = max(
            0.0,
            (network_bytes - self._last_network_bytes) * 8 / elapsed / 1_000_000,
        )
        self._last_at = now
        self._last_network_bytes = network_bytes

        cpu_count = max(1, os.cpu_count() or 1)
        try:
            load_1m = os.getloadavg()[0]
        except OSError:
            load_1m = 0.0
        load_ratio = load_1m / cpu_count
        memory_mb = read_available_memory_mb()
        reasons: list[str] = []
        if self.network_limit_mbps > 0 and network_mbps > self.network_limit_mbps:
            reasons.append("network")
        if load_ratio > self.load_limit_ratio:
            reasons.append("load")
        if memory_mb and memory_mb < self.memory_floor_mb:
            reasons.append("memory")

        if reasons:
            self._busy_samples += 1
            self._clear_samples = 0
        else:
            self._clear_samples += 1
            self._busy_samples = 0

        desired = self.max_concurrency
        jammed = self._busy_samples >= 2
        if jammed:
            desired = max(1, self.max_concurrency // 2)
            if "memory" in reasons:
                desired = 1
        elif self._clear_samples < 2:
            try:
                previous = json.loads(self.state_path.read_text(encoding="utf-8"))
                desired = max(
                    1,
                    min(self.max_concurrency, int(previous.get("desired_concurrency", desired))),
                )
            except (OSError, ValueError, json.JSONDecodeError, AttributeError):
                pass

        payload = {
            "schema_version": 1,
            "updated_at_unix": time.time(),
            "max_concurrency": self.max_concurrency,
            "desired_concurrency": desired,
            "active_codex_calls": active_slots(self.state_path),
            "network_mbps": round(network_mbps, 3),
            "network_limit_mbps": self.network_limit_mbps,
            "network_state": "busy" if "network" in reasons else "clear",
            "load_1m": round(load_1m, 3),
            "load_ratio": round(load_ratio, 3),
            "memory_available_mb": round(memory_mb, 1),
            "jammed": jammed,
            "jam_reasons": reasons if jammed else [],
        }
        atomic_write_json(self.state_path, payload)
        return payload


def _read_capacity(state_path: Path) -> int:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        desired = int(payload.get("desired_concurrency", 1))
        maximum = int(payload.get("max_concurrency", desired))
        updated = float(payload.get("updated_at_unix", 0))
    except (OSError, ValueError, json.JSONDecodeError, AttributeError, TypeError):
        return 1
    if updated and time.time() - updated > 180:
        return max(1, maximum)
    return max(1, min(desired, maximum))


@contextmanager
def codex_call_slot(state_path_value: str | None) -> Iterator[None]:
    """Wait for one shared Codex slot, then release it after the request."""

    if not state_path_value:
        yield
        return
    state_path = Path(state_path_value)
    slot_root = state_path.parent / f"{state_path.stem}.slots"
    slot_root.mkdir(parents=True, exist_ok=True)
    acquired: Path | None = None
    while acquired is None:
        desired = _read_capacity(state_path)
        active_slots(state_path)
        for index in range(1, desired + 1):
            candidate = slot_root / f"slot-{index:02d}.lock"
            try:
                descriptor = os.open(
                    candidate,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o644,
                )
            except FileExistsError:
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "acquired_at": time.time()}, handle)
            acquired = candidate
            break
        if acquired is None:
            time.sleep(2)
    try:
        yield
    finally:
        acquired.unlink(missing_ok=True)
