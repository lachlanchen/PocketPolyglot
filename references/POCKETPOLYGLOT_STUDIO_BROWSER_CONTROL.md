# PocketPolyglot Studio Browser Control

PocketPolyglot Studio has a dedicated persistent browser identity. Reuse it for
all future Studio web-app supervision instead of launching temporary Chrome
profiles.

## Canonical Runtime

| Component | Value |
| --- | --- |
| tmux session | `pocketpolyglot-studio-browser` |
| X display | `:95` |
| VNC | `127.0.0.1:5925` |
| noVNC | `http://127.0.0.1:6125/vnc_lite.html?host=127.0.0.1&port=6125&autoconnect=1&resize=remote` |
| Chrome CDP | `http://127.0.0.1:9365` |
| Chrome profile | `~/.cache/pocketpolyglot-studio-chrome` |
| Studio URL | `http://127.0.0.1:8766` |
| persisted config | `.pocketpolyglot-studio/browser/config.json` |

All network listeners are bound to localhost. The profile is private runtime
state and must never be committed, deleted during repair, or replaced with a
temporary profile.

## Operator Commands

```sh
./studio/pocketpolyglot browser start
./studio/pocketpolyglot browser status
./studio/pocketpolyglot browser pages
./studio/pocketpolyglot browser refresh --project technical-pocket-polished-seven
./studio/pocketpolyglot browser progress --project technical-pocket-polished-seven
./studio/pocketpolyglot browser screenshot --output /tmp/studio.png
./studio/pocketpolyglot browser chat technical-pocket-polished-seven \
  --read-only --profile fast "Check queue health and current progress."
```

`browser start` reuses the persisted configuration and running tmux session.
Use `browser stop` only when explicitly requested; stopping preserves the
Chrome profile.

## Evidence Contract

A healthy browser requires all of the following:

- the managed tmux session exists;
- VNC, noVNC, and CDP ports answer on localhost;
- Chrome exposes a Studio page;
- the Studio `/api/health` endpoint reports `ok`.

`browser progress` obtains active job details from the visible Studio page.
`browser chat` selects the requested project, configures reasoning and agent
mode, submits through the React chat form, waits until the visible assistant
response is complete, and saves a screenshot. This verifies the actual web-app
path rather than bypassing it with a direct chat API call.

## Recovery

The tmux supervisor restarts the full Xvfb/x11vnc/noVNC/Chrome stack if any
component exits. Runtime state and component logs are under:

```text
.pocketpolyglot-studio/browser/
```

Inspect `runtime.json` and `supervisor.log` before changing ports or profiles.
Port or display changes must be made once with explicit `browser start`
arguments; subsequent starts reuse the saved values.
