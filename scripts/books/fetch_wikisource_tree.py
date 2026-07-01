#!/usr/bin/env python3
"""Mirror a Wikisource work as raw wikitext, rendered HTML, and metadata.

The script is intentionally generic: it can fetch a root page, subpages under
the root title, and optionally links from the root page that match a regex.
It records missing pages instead of failing the whole run, which is useful for
multilingual source preparation where some languages may not exist.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API_ROOTS = {
    "ar": "https://ar.wikisource.org/w/api.php",
    "zh": "https://zh.wikisource.org/w/api.php",
    "ja": "https://ja.wikisource.org/w/api.php",
    "jp": "https://ja.wikisource.org/w/api.php",
    "en": "https://en.wikisource.org/w/api.php",
}

USER_AGENT = "LinguaLeaf/0.1 (local source mirror; https://learn.lazying.art)"


def request_json(url: str, *, retries: int = 8) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in {429, 500, 502, 503, 504} and attempt + 1 < retries:
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(120, 5 * (2**attempt))
                time.sleep(delay)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(min(120, 5 * (2**attempt)))
                continue
            raise
    raise RuntimeError(f"request failed: {last_error}")


def api_url(api: str, **params: Any) -> str:
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    return api + "?" + urllib.parse.urlencode(params, doseq=True)


def safe_name(title: str) -> str:
    return (
        title.replace("/", "__")
        .replace(":", "_")
        .replace(" ", "_")
        .replace("|", "_")
    )


def get_page_info(api: str, title: str) -> dict[str, Any] | None:
    data = request_json(
        api_url(
            api,
            action="query",
            titles=title,
            prop="info",
            redirects=1,
        )
    )
    pages = data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    return pages[0]


def all_subpages(api: str, title: str, *, namespace: int, sleep_seconds: float) -> list[str]:
    prefix = f"{title}/"
    titles: list[str] = []
    cont: dict[str, Any] = {}
    while True:
        data = request_json(
            api_url(
                api,
                action="query",
                list="allpages",
                apprefix=prefix,
                apnamespace=namespace,
                aplimit="max",
                **cont,
            )
        )
        for page in data.get("query", {}).get("allpages", []):
            candidate = page.get("title")
            if candidate:
                titles.append(candidate)
        cont = data.get("continue", {})
        if not cont:
            break
        time.sleep(sleep_seconds)
    return titles


def linked_pages(api: str, title: str, *, namespace: int, sleep_seconds: float) -> list[str]:
    titles: list[str] = []
    cont: dict[str, Any] = {}
    while True:
        data = request_json(
            api_url(
                api,
                action="query",
                titles=title,
                prop="links",
                plnamespace=namespace,
                pllimit="max",
                redirects=1,
                **cont,
            )
        )
        for page in data.get("query", {}).get("pages", []):
            for link in page.get("links", []) or []:
                candidate = link.get("title")
                if candidate:
                    titles.append(candidate)
        cont = data.get("continue", {})
        if not cont:
            break
        time.sleep(sleep_seconds)
    return titles


def fetch_raw(api: str, title: str) -> tuple[str, str]:
    data = request_json(
        api_url(
            api,
            action="query",
            titles=title,
            prop="revisions",
            rvprop="content",
            rvslots="main",
            redirects=1,
        )
    )
    pages = data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        raise FileNotFoundError(title)
    page = pages[0]
    actual_title = page.get("title", title)
    revisions = page.get("revisions") or []
    if not revisions:
        return actual_title, ""
    slots = revisions[0].get("slots") or {}
    main = slots.get("main") or {}
    return actual_title, main.get("content", "")


def fetch_html(api: str, title: str) -> str:
    data = request_json(
        api_url(
            api,
            action="parse",
            page=title,
            prop="text",
            redirects=1,
            disablelimitreport=1,
            disableeditsection=1,
        )
    )
    return data.get("parse", {}).get("text", "")


def ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", required=True, choices=sorted(API_ROOTS))
    parser.add_argument("--title", required=True, help="Root Wikisource title")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--namespace", type=int, default=0)
    parser.add_argument("--include-subpages", action="store_true")
    parser.add_argument("--include-root-links", action="store_true")
    parser.add_argument("--title-regex", help="Keep only discovered titles matching this regex")
    parser.add_argument("--max-pages", type=int, default=0, help="0 means unlimited")
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    args = parser.parse_args()

    api = API_ROOTS[args.lang]
    out_dir = args.out_dir
    raw_dir = out_dir / "raw"
    html_dir = out_dir / "html"
    raw_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)

    root_info = get_page_info(api, args.title)
    requested_root = args.title
    if root_info:
        root_title = root_info.get("title", args.title)
        titles = [root_title]
        missing = []
    else:
        root_title = args.title
        titles = []
        missing = [{"title": requested_root, "reason": "root page missing"}]

    if root_info and args.include_subpages:
        for prefix_root in ordered_unique([requested_root, root_title]):
            titles.extend(all_subpages(api, prefix_root, namespace=args.namespace, sleep_seconds=args.sleep_seconds))
            time.sleep(args.sleep_seconds)

    if root_info and args.include_root_links:
        titles.extend(linked_pages(api, root_title, namespace=args.namespace, sleep_seconds=args.sleep_seconds))

    titles = ordered_unique(titles)
    if args.title_regex:
        pattern = re.compile(args.title_regex)
        titles = [title for title in titles if pattern.search(title)]
        if root_title not in titles and root_info:
            titles.insert(0, root_title)
    if args.max_pages > 0:
        titles = titles[: args.max_pages]

    manifest: list[dict[str, Any]] = []
    for index, title in enumerate(titles, start=1):
        try:
            actual_title, raw = fetch_raw(api, title)
            time.sleep(args.sleep_seconds)
            html = fetch_html(api, actual_title)
            time.sleep(args.sleep_seconds)
        except Exception as exc:  # keep the mirror resumable and informative
            manifest.append({"index": index, "title": title, "status": "error", "error": str(exc)})
            continue
        stem = f"{index:04d}-{safe_name(title)}"
        raw_path = raw_dir / f"{stem}.wiki"
        html_path = html_dir / f"{stem}.html"
        raw_path.write_text(raw, encoding="utf-8")
        html_path.write_text(html, encoding="utf-8")
        manifest.append(
            {
                "index": index,
                "title": title,
                "actual_title": actual_title,
                "status": "ok",
                "raw": str(raw_path.relative_to(out_dir)),
                "html": str(html_path.relative_to(out_dir)),
                "source_url": f"{api.rsplit('/w/', 1)[0]}/wiki/{urllib.parse.quote(actual_title.replace(' ', '_'))}",
            }
        )
        print(f"{index:04d} {title} -> {actual_title}")

    metadata = {
        "lang": "ja" if args.lang == "jp" else args.lang,
        "requested_root": requested_root,
        "root_title": root_title,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "api": api,
        "include_subpages": args.include_subpages,
        "include_root_links": args.include_root_links,
        "title_regex": args.title_regex,
        "missing": missing,
        "pages": manifest,
    }
    (out_dir / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "README.md").write_text(
        f"# Wikisource Mirror: {requested_root}\n\n"
        f"- Language: `{metadata['lang']}`\n"
        f"- Requested root: `{requested_root}`\n"
        f"- Resolved root: `{root_title}`\n"
        f"- Downloaded at: `{metadata['downloaded_at']}`\n"
        f"- OK pages: `{sum(1 for page in manifest if page.get('status') == 'ok')}`\n"
        f"- Missing root: `{bool(missing)}`\n",
        encoding="utf-8",
    )
    print(f"manifest: {out_dir / 'manifest.json'}")
    print(f"ok_pages={sum(1 for page in manifest if page.get('status') == 'ok')} missing_root={bool(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
