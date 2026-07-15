from __future__ import annotations

import argparse
import base64
import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import Settings


DEFAULT_SESSION = "pocketpolyglot-studio-browser"
DEFAULT_DISPLAY = ":95"
DEFAULT_VNC_PORT = 5925
DEFAULT_NOVNC_PORT = 6125
DEFAULT_CDP_PORT = 9365
DEFAULT_RESOLUTION = "1920x1080x24"
DEFAULT_PROFILE = Path.home() / ".cache/pocketpolyglot-studio-chrome"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class BrowserConfig:
    state_dir: Path
    session: str
    display: str
    vnc_port: int
    novnc_port: int
    cdp_port: int
    resolution: str
    profile: Path
    studio_url: str

    @property
    def config_path(self) -> Path:
        return self.state_dir / "config.json"

    @property
    def runtime_path(self) -> Path:
        return self.state_dir / "runtime.json"

    @property
    def supervisor_log(self) -> Path:
        return self.state_dir / "supervisor.log"

    @property
    def cdp_url(self) -> str:
        return f"http://127.0.0.1:{self.cdp_port}"

    @property
    def novnc_url(self) -> str:
        query = urllib.parse.urlencode(
            {
                "host": "127.0.0.1",
                "port": self.novnc_port,
                "autoconnect": 1,
                "resize": "remote",
            }
        )
        return f"http://127.0.0.1:{self.novnc_port}/vnc_lite.html?{query}"

    def serializable(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state_dir"] = str(self.state_dir)
        payload["profile"] = str(self.profile)
        payload["cdp_url"] = self.cdp_url
        payload["novnc_url"] = self.novnc_url
        return payload

    def save(self) -> None:
        self.validate()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.profile.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.config_path, self.serializable())

    def validate(self) -> None:
        if not self.display.startswith(":") or not self.display[1:].isdigit():
            raise ValueError(f"Invalid X display: {self.display}")
        ports = (self.vnc_port, self.novnc_port, self.cdp_port)
        if len(set(ports)) != len(ports) or any(port < 1024 or port > 65535 for port in ports):
            raise ValueError(f"Browser ports must be distinct unprivileged ports: {ports}")
        parsed = urllib.parse.urlparse(self.studio_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Invalid Studio URL: {self.studio_url}")

    @classmethod
    def load(cls, settings: Settings, overrides: dict[str, Any] | None = None) -> "BrowserConfig":
        state_dir = settings.state_root / "browser"
        saved = _read_json(state_dir / "config.json")
        overrides = {key: value for key, value in (overrides or {}).items() if value is not None}
        default_port = os.environ.get("POCKETPOLYGLOT_PORT", "8765")

        def value(key: str, environment: str, fallback: Any) -> Any:
            if key in overrides:
                return overrides[key]
            if environment in os.environ:
                return os.environ[environment]
            if key in saved:
                return saved[key]
            return fallback

        config = cls(
            state_dir=state_dir,
            session=str(value("session", "POCKETPOLYGLOT_BROWSER_SESSION", DEFAULT_SESSION)),
            display=str(value("display", "POCKETPOLYGLOT_BROWSER_DISPLAY", DEFAULT_DISPLAY)),
            vnc_port=int(value("vnc_port", "POCKETPOLYGLOT_BROWSER_VNC_PORT", DEFAULT_VNC_PORT)),
            novnc_port=int(value("novnc_port", "POCKETPOLYGLOT_BROWSER_NOVNC_PORT", DEFAULT_NOVNC_PORT)),
            cdp_port=int(value("cdp_port", "POCKETPOLYGLOT_BROWSER_CDP_PORT", DEFAULT_CDP_PORT)),
            resolution=str(value("resolution", "POCKETPOLYGLOT_BROWSER_RESOLUTION", DEFAULT_RESOLUTION)),
            profile=Path(value("profile", "POCKETPOLYGLOT_BROWSER_PROFILE", DEFAULT_PROFILE)).expanduser().resolve(),
            studio_url=str(
                value(
                    "studio_url",
                    "POCKETPOLYGLOT_BROWSER_STUDIO_URL",
                    f"http://127.0.0.1:{default_port}",
                )
            ).rstrip("/"),
        )
        config.validate()
        return config

    @classmethod
    def from_path(cls, path: Path) -> "BrowserConfig":
        payload = _read_json(path)
        if not payload:
            raise RuntimeError(f"Browser configuration is missing or invalid: {path}")
        config = cls(
            state_dir=Path(payload["state_dir"]),
            session=str(payload["session"]),
            display=str(payload["display"]),
            vnc_port=int(payload["vnc_port"]),
            novnc_port=int(payload["novnc_port"]),
            cdp_port=int(payload["cdp_port"]),
            resolution=str(payload["resolution"]),
            profile=Path(payload["profile"]),
            studio_url=str(payload["studio_url"]),
        )
        config.validate()
        return config


def tcp_ready(port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def url_json(url: str, timeout: float = 2.0, method: str = "GET") -> Any:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def tmux_session_exists(name: str) -> bool:
    return subprocess.run(
        ["tmux", "has-session", "-t", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def studio_ready(config: BrowserConfig) -> bool:
    try:
        health = url_json(f"{config.studio_url}/api/health")
    except (OSError, ValueError):
        return False
    return isinstance(health, dict) and health.get("status") == "ok"


def list_pages(config: BrowserConfig) -> list[dict[str, Any]]:
    try:
        pages = url_json(f"{config.cdp_url}/json/list")
    except (OSError, ValueError):
        return []
    if not isinstance(pages, list):
        return []
    return [page for page in pages if isinstance(page, dict) and page.get("type") == "page"]


def browser_status(config: BrowserConfig) -> dict[str, Any]:
    pages = list_pages(config)
    runtime = _read_json(config.runtime_path)
    status = {
        "managed": tmux_session_exists(config.session),
        "vnc_ready": tcp_ready(config.vnc_port),
        "novnc_ready": tcp_ready(config.novnc_port),
        "cdp_ready": bool(pages),
        "studio_ready": studio_ready(config),
        "pages": [
            {"id": page.get("id"), "title": page.get("title"), "url": page.get("url")}
            for page in pages
        ],
        "runtime": runtime,
        **config.serializable(),
    }
    status["healthy"] = all(
        status[key] for key in ("managed", "vnc_ready", "novnc_ready", "cdp_ready", "studio_ready")
    )
    return status


def _log_tail(path: Path, lines: int = 40) -> str:
    if not path.is_file():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def start_browser(config: BrowserConfig, wait_seconds: float = 40.0) -> dict[str, Any]:
    config.save()
    current = browser_status(config)
    if current["healthy"]:
        return current | {"reused": True}
    if not current["studio_ready"]:
        raise RuntimeError(
            f"PocketPolyglot Studio is not reachable at {config.studio_url}. Start the Studio server first."
        )
    if tmux_session_exists(config.session):
        subprocess.run(["tmux", "kill-session", "-t", config.session], check=False)
        time.sleep(1)
    occupied = [port for port in (config.vnc_port, config.novnc_port, config.cdp_port) if tcp_ready(port)]
    if occupied:
        raise RuntimeError(f"Refusing to reuse occupied browser ports without the managed session: {occupied}")

    python_path = str(Path(__file__).resolve().parents[1])
    command = shlex.join(
        [
            "env",
            f"PYTHONPATH={python_path}{os.pathsep}{os.environ.get('PYTHONPATH', '')}",
            sys.executable,
            "-m",
            "pocketpolyglot_studio.browser_control",
            "supervise",
            "--config",
            str(config.config_path),
        ]
    )
    command = f"{command} >> {shlex.quote(str(config.supervisor_log))} 2>&1"
    launched = subprocess.run(
        ["tmux", "new-session", "-d", "-s", config.session, command],
        capture_output=True,
        text=True,
        check=False,
    )
    if launched.returncode:
        raise RuntimeError(launched.stderr.strip() or "Unable to start browser tmux session")

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        status = browser_status(config)
        if status["healthy"]:
            return status | {"reused": False}
        if not status["managed"]:
            break
        time.sleep(0.5)
    raise RuntimeError(
        "Studio browser did not become healthy.\n" + _log_tail(config.supervisor_log)
    )


def stop_browser(config: BrowserConfig) -> dict[str, Any]:
    if tmux_session_exists(config.session):
        subprocess.run(["tmux", "kill-session", "-t", config.session], check=False)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if not any(tcp_ready(port) for port in (config.vnc_port, config.novnc_port, config.cdp_port)):
            break
        time.sleep(0.25)
    return browser_status(config)


def _spawn(command: list[str], log_path: Path, environment: dict[str, str] | None = None) -> tuple[subprocess.Popen[bytes], Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("ab", buffering=0)
    process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT, env=environment)
    return process, handle


def _terminate(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 5
    for process in reversed(processes):
        if process.poll() is None:
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.kill()


def supervise(config: BrowserConfig) -> int:
    stopping = False
    restart_count = 0

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    config.state_dir.mkdir(parents=True, exist_ok=True)
    config.profile.mkdir(parents=True, exist_ok=True)
    display_number = config.display.removeprefix(":")

    while not stopping:
        processes: list[subprocess.Popen[bytes]] = []
        handles: list[Any] = []
        failed_component = ""
        try:
            xvfb, handle = _spawn(
                ["Xvfb", config.display, "-screen", "0", config.resolution, "-ac", "-nolisten", "tcp"],
                config.state_dir / "xvfb.log",
            )
            processes.append(xvfb)
            handles.append(handle)
            x_socket = Path(f"/tmp/.X11-unix/X{display_number}")
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and not x_socket.exists() and xvfb.poll() is None:
                time.sleep(0.1)
            if xvfb.poll() is not None or not x_socket.exists():
                raise RuntimeError("Xvfb did not create its display socket")

            environment = os.environ.copy()
            environment["DISPLAY"] = config.display
            environment.pop("XAUTHORITY", None)
            vnc, handle = _spawn(
                [
                    "x11vnc",
                    "-display",
                    config.display,
                    "-localhost",
                    "-nopw",
                    "-forever",
                    "-shared",
                    "-noxdamage",
                    "-rfbport",
                    str(config.vnc_port),
                ],
                config.state_dir / "x11vnc.log",
                environment,
            )
            processes.append(vnc)
            handles.append(handle)
            novnc, handle = _spawn(
                [
                    "websockify",
                    f"127.0.0.1:{config.novnc_port}",
                    f"127.0.0.1:{config.vnc_port}",
                    "--web=/usr/share/novnc",
                ],
                config.state_dir / "novnc.log",
            )
            processes.append(novnc)
            handles.append(handle)
            chrome, handle = _spawn(
                [
                    "google-chrome",
                    "--remote-debugging-address=127.0.0.1",
                    f"--remote-debugging-port={config.cdp_port}",
                    "--remote-allow-origins=*",
                    f"--user-data-dir={config.profile}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-session-crashed-bubble",
                    "--disable-features=Translate,TranslateUI",
                    "--password-store=basic",
                    "--window-position=0,0",
                    "--window-size=1920,1080",
                    "--new-window",
                    config.studio_url,
                ],
                config.state_dir / "chrome.log",
                environment,
            )
            processes.append(chrome)
            handles.append(handle)
            atomic_write_json(
                config.runtime_path,
                {
                    "status": "running",
                    "started_at": utc_now(),
                    "restart_count": restart_count,
                    "pids": {
                        "xvfb": xvfb.pid,
                        "x11vnc": vnc.pid,
                        "novnc": novnc.pid,
                        "chrome": chrome.pid,
                    },
                    **config.serializable(),
                },
            )

            while not stopping:
                dead = [name for name, process in zip(("xvfb", "x11vnc", "novnc", "chrome"), processes) if process.poll() is not None]
                if dead:
                    failed_component = ",".join(dead)
                    break
                time.sleep(1)
        except Exception as error:  # Supervisor errors must remain visible in runtime.json and logs.
            failed_component = f"launch: {error}"
        finally:
            _terminate(processes)
            for handle in handles:
                handle.close()

        if stopping:
            break
        restart_count += 1
        atomic_write_json(
            config.runtime_path,
            {
                "status": "restarting",
                "updated_at": utc_now(),
                "restart_count": restart_count,
                "failed_component": failed_component,
                **config.serializable(),
            },
        )
        time.sleep(min(15, 1 + restart_count * 2))

    atomic_write_json(
        config.runtime_path,
        {"status": "stopped", "stopped_at": utc_now(), "restart_count": restart_count, **config.serializable()},
    )
    return 0


class CdpPage:
    def __init__(self, page: dict[str, Any]) -> None:
        try:
            import websocket
        except ImportError as error:
            raise RuntimeError("Install Studio browser dependencies with `make studio-install`.") from error
        self.websocket = websocket.create_connection(
            page["webSocketDebuggerUrl"],
            timeout=15,
            suppress_origin=True,
        )
        self.next_id = 0

    def close(self) -> None:
        self.websocket.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.next_id += 1
        message_id = self.next_id
        self.websocket.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.websocket.recv())
            if message.get("id") != message_id:
                continue
            if "error" in message:
                raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
            return message.get("result", {})

    def evaluate(self, javascript: str, await_promise: bool = False) -> Any:
        response = self.call(
            "Runtime.evaluate",
            {"expression": javascript, "returnByValue": True, "awaitPromise": await_promise},
        )
        if response.get("exceptionDetails"):
            raise RuntimeError(json.dumps(response["exceptionDetails"], ensure_ascii=False))
        result = response.get("result", {})
        return result.get("value", result)

    def screenshot(self, output: Path) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = self.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        output.write_bytes(base64.b64decode(payload["data"]))
        return output

    def bring_to_front(self) -> None:
        self.call("Page.bringToFront")

    def reload(self, timeout: float = 20) -> None:
        self.call("Page.reload", {"ignoreCache": True})
        wait_for(
            lambda: self.evaluate("document.readyState === 'complete'"),
            timeout,
            "Studio page reload",
        )


def studio_page(config: BrowserConfig) -> CdpPage:
    pages = list_pages(config)
    candidate = next((page for page in pages if str(page.get("url", "")).startswith(config.studio_url)), None)
    if candidate is None:
        encoded = urllib.parse.quote(config.studio_url, safe="")
        candidate = url_json(f"{config.cdp_url}/json/new?{encoded}", method="PUT")
    page = CdpPage(candidate)
    page.bring_to_front()
    return page


def wait_for(check: Callable[[], Any], timeout: float, label: str, interval: float = 0.4) -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = check()
        if last:
            return last
        time.sleep(interval)
    raise TimeoutError(f"Timed out waiting for {label}; last state: {last!r}")


def select_project(page: CdpPage, title: str, timeout: float = 15) -> None:
    encoded = json.dumps(title)

    def select() -> bool:
        return bool(
            page.evaluate(
                f"""
                (() => {{
                  const title = {encoded};
                  const selected = document.querySelector('.breadcrumbs strong')?.textContent?.trim();
                  if (selected === title) return true;
                  const row = [...document.querySelectorAll('.project-row')]
                    .find((item) => item.querySelector('strong')?.textContent?.trim() === title);
                  if (!row) return false;
                  row.click();
                  return false;
                }})()
                """
            )
        )

    wait_for(select, timeout, f"project {title}")


def inspect_progress(page: CdpPage) -> dict[str, Any]:
    return page.evaluate(
        """
        (async () => {
          const jobs = await fetch('/api/jobs?limit=150').then((response) => response.json());
          const active = jobs.filter((job) => ['queued','starting','running'].includes(job.status));
          const details = await Promise.all(active.map((job) =>
            fetch(`/api/jobs/${job.id}`).then((response) => response.json())
          ));
          return {
            inspected_at: new Date().toISOString(),
            page: {title: document.title, url: location.href},
            selected_project: document.querySelector('.breadcrumbs strong')?.textContent?.trim() || '',
            visible_status: [...document.querySelectorAll('.status-mark')]
              .map((node) => node.textContent.trim()).filter(Boolean),
            active_jobs: details.map((job) => ({
              id: job.id,
              title: job.title,
              status: job.status,
              progress: job.progress,
              heartbeat_at: job.heartbeat_at,
              progress_detail: job.progress_detail || null,
            })),
          };
        })()
        """,
        await_promise=True,
    )


def summarize_progress(progress: dict[str, Any]) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    for job in progress.get("active_jobs", []):
        detail = job.get("progress_detail") or {}
        runtime = detail.get("runtime") or {}
        current_book = detail.get("current_book")
        current_detail = (detail.get("books") or {}).get(current_book, {}) if current_book else {}
        if job.get("status") in {"blocked", "failed", "interrupted"}:
            health = "blocked"
        elif runtime.get("jammed") or not runtime.get("active_codex_calls"):
            health = "attention"
        else:
            health = "healthy"
        summaries.append(
            {
                "id": job.get("id"),
                "title": job.get("title"),
                "status": job.get("status"),
                "progress": detail.get("progress", job.get("progress", 0)),
                "accepted_segments": detail.get("accepted_segments"),
                "total_segments": detail.get("total_segments"),
                "current_book": current_book,
                "current_book_progress": current_detail.get("progress"),
                "current_book_valid_chunks": current_detail.get("valid_chunks"),
                "current_book_total_chunks": current_detail.get("total_chunks"),
                "current_book_invalid_chunks": current_detail.get("invalid_chunks"),
                "current_book_failed_chunks": current_detail.get("failed_chunks"),
                "active_codex_calls": runtime.get("active_codex_calls"),
                "desired_concurrency": runtime.get("desired_concurrency"),
                "network_mbps": runtime.get("network_mbps"),
                "jammed": runtime.get("jammed"),
                "health": health,
                "heartbeat_at": job.get("heartbeat_at"),
            }
        )
    return {
        "inspected_at": progress.get("inspected_at"),
        "selected_project": progress.get("selected_project"),
        "jobs": summaries,
    }


def chat_in_ui(
    page: CdpPage,
    project_title: str,
    message: str,
    profile: str,
    agent_mode: bool,
    timeout: float,
) -> dict[str, Any]:
    select_project(page, project_title)
    profile_labels = {"auto": "Auto", "fast": "Fast", "balanced": "Balanced", "deep": "Deep", "ultra": "Ultra"}
    setup = page.evaluate(
        f"""
        (() => {{
          const desiredProfile = {json.dumps(profile_labels[profile])};
          if (!document.querySelector('.chat-panel')) {{
            const button = [...document.querySelectorAll('button')]
              .find((item) => item.textContent.trim() === 'Codex');
            button?.click();
            return {{ready:false}};
          }}
          const profileButton = [...document.querySelectorAll('.profile-control button')]
            .find((item) => item.textContent.trim() === desiredProfile);
          profileButton?.click();
          const checkbox = document.querySelector('.chat-context input[type=checkbox]');
          const desiredAgent = {str(agent_mode).lower()};
          if (checkbox && checkbox.checked !== desiredAgent) checkbox.click();
          return {{
            ready: Boolean(document.querySelector('.chat-composer textarea')),
            assistants: document.querySelectorAll('.chat-message.assistant').length,
          }};
        }})()
        """
    )
    if not setup.get("ready"):
        wait_for(lambda: page.evaluate("Boolean(document.querySelector('.chat-composer textarea'))"), 10, "chat panel")
        setup = page.evaluate("({assistants: document.querySelectorAll('.chat-message.assistant').length})")
    before = int(setup.get("assistants", 0))
    inserted = page.evaluate(
        f"""
        (() => {{
          const textarea = document.querySelector('.chat-composer textarea');
          if (!textarea) return false;
          const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
          setter.call(textarea, {json.dumps(message)});
          textarea.dispatchEvent(new Event('input', {{bubbles:true}}));
          textarea.focus();
          return true;
        }})()
        """
    )
    if not inserted:
        raise RuntimeError("Studio chat composer is not available")
    wait_for(
        lambda: page.evaluate("!document.querySelector('.chat-composer .send-button')?.disabled"),
        5,
        "enabled chat send button",
    )
    submitted = page.evaluate(
        """
        (() => {
          const form = document.querySelector('.chat-composer');
          if (!form) return false;
          form.requestSubmit();
          return true;
        })()
        """
    )
    if not submitted:
        raise RuntimeError("Unable to submit Studio chat form")

    def completed() -> dict[str, Any] | None:
        state = page.evaluate(
            """
            (() => {
              const assistants = [...document.querySelectorAll('.chat-message.assistant')];
              const latest = assistants.at(-1);
              return {
                count: assistants.length,
                pending: Boolean(latest?.querySelector('.message-spinner')),
                text: latest?.querySelector('.message-body')?.innerText?.trim() || '',
                route: document.querySelector('.chat-header span')?.textContent?.trim() || '',
              };
            })()
            """
        )
        if state["count"] > before and not state["pending"] and state["text"]:
            return state
        return None

    result = wait_for(completed, timeout, "Studio Codex response", interval=0.75)
    return {
        "project": project_title,
        "profile": profile,
        "agent_mode": agent_mode,
        "route": result["route"],
        "response": result["text"],
    }


def _supervisor_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["supervise"])
    parser.add_argument("--config", type=Path, required=True)
    return parser


def main() -> int:
    args = _supervisor_parser().parse_args()
    return supervise(BrowserConfig.from_path(args.config))


if __name__ == "__main__":
    raise SystemExit(main())
