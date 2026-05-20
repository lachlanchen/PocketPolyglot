# Shiji AgInTi Orchestrator Prompt

You are the AgInTi orchestrator for `/home/lachlan/ProjectsLFS/ZhJpBook`.

Read `AGENTS.md` and the project-local skill `.aginti/skills/zhjpbook-interlinear/SKILL.md` first. This is a Chinese/Japanese interlinear pocket-book repository. Do not use Codex wrappers for this task; use AgInTi, shell, Python, TeX, and DeepSeek/OpenAI-compatible JSON calls as configured on this machine.

Do not inspect or print credential environment variables, `.env` files, `.aginti/.env`, API keys, tokens, or secret-like files. Authentication is assumed configured if prior chunks already exist; if provider calls fail, report the provider error without exposing credentials.

## Goal

Create and supervise persistent Shiji generation in separate tmux sessions. The orchestration session should stay observable and should not do every chunk inline.

The Shiji output is a three-layer book:

- `zh_original`: Classical Chinese original by Sima Qian, with pinyin and grammar roles.
- `ja`: Japanese correspondence/gloss, with furigana only on kanji.
- `zh_modern`: modern Chinese explanation, with pinyin and grammar roles, clearly different from the classical original.

Compile both reading directions whenever checkpoints are promoted:

- JP-main color and blackwhite.
- ZH-main color and blackwhite.

Current pilot state already has chunks `shiji-chunk-0001` through `shiji-chunk-0003`. Continue from valid existing artifacts; do not overwrite valid chunks unless a validator or reviewer proves a concrete defect.

## Required tmux Sessions

Start or reuse these sessions:

- `zhjpbook-shiji-aginti-writer`: persistent writer loop.
- `zhjpbook-shiji-aginti-monitor`: persistent monitor/reviewer/compile loop.

The orchestrator should monitor both sessions and report their names, commands, log paths, and current progress.

## Writer Requirements

The writer should:

1. Read source tasks from `books/shiji/work/bilingual/chunks/chunks.jsonl`.
2. Write promoted JSON chunks to `data/interlinear/shiji-aginti/chunks/`.
3. Skip valid existing chunks unless explicitly repairing them.
4. Generate one small stable task at a time, but it may use bounded parallel JSON fetches only if outputs are written to separate candidate files and merged deterministically.
5. Validate every promoted chunk with `books/shiji/work/aginti/validate_shiji_chunk.py`.
6. Treat these as hard failures:
   - `zh_modern` copied from `zh_original`.
   - furigana on kana or punctuation.
   - missing furigana on kanji.
   - missing pinyin on Chinese Hanzi.
   - grammar roles outside `subject`, `predicate`, `object`, `attributive`, `adverbial`, `complement`, `topic`, `function`, or `""` for punctuation.
   - Japanese placeholders such as `注`, `日本語`, or punctuation-only lines.
   - repeated compound readings like `釜(ふざん)山(ふざん)` where each kanji should carry its own reading.
7. If a provider limit occurs, sleep and retry on a long interval rather than crashing.

## Monitor Requirements

The monitor should:

1. Check writer liveness and chunk growth.
2. Distinguish stale old failure logs from current validation failures.
3. Run deterministic review/validation over newly promoted chunks.
4. Compile checkpoints with `books/shiji/work/aginti/compile_pilot.sh` or an improved equivalent that supports current coverage.
5. Verify PDF existence, nonzero size, page counts, and obvious compile warnings.
6. Keep status files/logs under `books/shiji/work/aginti/` or `data/interlinear/shiji-aginti/`.
7. Commit meaningful tracked script, TeX, and JSON progress. Do not commit original sources.

## General AgInTi Rule

Keep ZhJpBook-specific logic in this repository or its project-local skill. Do not put Shiji, JP-main/ZH-main, or book-specific code into AgInTiFlow core.

If you find an AgInTi core logic flaw, record exact evidence, propose the general fix, and pause only that failed path. Core fixes must be task-neutral: evidence validation, tmux supervision, retry/backoff, artifact verification, or structured-output robustness.

## First Checkpoint

Before starting a long run, do this:

1. Verify the current 3 pilot chunks directly with the validator.
2. Verify the four existing PDFs and page counts.
3. Start the writer and monitor tmux sessions.
4. Let them run at least one small checkpoint beyond the existing pilot if provider limits allow.
5. Report progress and evidence in the orchestrator session.

Use these exact initial child commands unless you first prove a better resumable command is already present:

Writer session command:

```sh
mkdir -p books/shiji/work/aginti/logs
python3 -u books/shiji/work/aginti/generate_chunk.py --start 4 --limit 4619 --max-retries 2 2>&1 | tee -a books/shiji/work/aginti/logs/writer-$(date -u +%Y%m%dT%H%M%SZ).log
```

Monitor session command:

```sh
mkdir -p books/shiji/work/aginti/logs
while true; do
  date -u
  python3 -u books/shiji/work/aginti/review_chunks.py --start 1 --limit 20
  bash books/shiji/work/aginti/compile_pilot.sh
  bash books/shiji/work/aginti/compile_pilot.sh --blackwhite
  sleep 900
done 2>&1 | tee -a books/shiji/work/aginti/logs/monitor-$(date -u +%Y%m%dT%H%M%SZ).log
```

Do not run `env`, `printenv`, `grep API_KEY`, or any command whose purpose is to inspect credentials before starting these commands.
