#!/usr/bin/env python3
"""Register the 2026-07-12 imported history, leadership, and classics batch.

This script copies curated files from ../Books into this repo's ignored
sources/ tree and writes launchable PocketPolyglot queue files. It does not
start model workers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BOOKS_ROOT = ROOT.parent / "Books"
SOURCE_ROOT = BOOKS_ROOT / "resources/curated-books"
NOW = datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def copy_source(src_rel: str, dst_rel: str) -> dict[str, str]:
    src = BOOKS_ROOT / src_rel
    dst = ROOT / dst_rel
    if not src.exists():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    status = "existing_same"
    if not dst.exists() or hashlib.sha256(dst.read_bytes()).digest() != hashlib.sha256(src.read_bytes()).digest():
        shutil.copy2(src, dst)
        status = "copied"
    return {
        "source": str(src.relative_to(BOOKS_ROOT)),
        "destination": dst_rel,
        "status": status,
        "size_bytes": str(dst.stat().st_size),
        "sha256_16": sha16(dst),
    }


def task(
    *,
    priority: int,
    book_id: str,
    title_en: str,
    title_zh: str,
    title_ja: str,
    author: str,
    source_path: str,
    source_from_books: str,
    title_zh_reading: str = "",
    title_ja_reading: str = "",
    author_reading_zh: str = "",
    author_reading_ja: str = "",
    description: str = "",
    min_chunk_count: int = 10,
    source_refs: dict[str, str] | None = None,
    copy_refs: dict[str, str] | None = None,
    stop_markers: list[str] | None = None,
    start_marker: str = "",
    body_start_markers: list[str] | None = None,
    task_mode: str = "trilingual_modern_nonfiction_en_source_generated_zh_ja",
    translation_contract: dict[str, str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    copies = [copy_source(source_from_books, source_path)]
    reference_paths: dict[str, str] = {}
    for key, value in (source_refs or {}).items():
        reference_paths[key] = value
    for key, dst_rel in (copy_refs or {}).items():
        src_rel = key
        copies.append(copy_source(src_rel, dst_rel))
        reference_paths[Path(src_rel).stem[:64]] = dst_rel

    item: dict[str, Any] = {
        "priority": priority,
        "book_id": book_id,
        "title_en": title_en,
        "title_zh": title_zh,
        "title_ja": title_ja,
        "title_zh_reading": title_zh_reading,
        "title_ja_reading": title_ja_reading,
        "author": author,
        "author_reading_zh": author_reading_zh,
        "author_reading_ja": author_reading_ja,
        "source_path": source_path,
        "start_marker": start_marker,
        "reference_paths": reference_paths,
        "reference_notes": "Supplemental files were copied from ../Books when available. The English spine remains the only chunk-alignment source until a later reference-alignment pass is explicitly run.",
        "stop_markers": stop_markers or [
            "Notes",
            "Endnotes",
            "Bibliography",
            "References",
            "Further Reading",
            "Acknowledgments",
            "Acknowledgements",
            "Index",
        ],
        "description": description or f"{author}, {title_en}. English source is the alignment spine; generate modern Japanese and Chinese.",
        "min_chunk_count": min_chunk_count,
        "task_mode": task_mode,
    }
    if body_start_markers:
        item["body_start_markers"] = body_start_markers
    if translation_contract:
        item["translation_contract"] = translation_contract
    return item, copies


HISTORY_CONTRACT = {
    "style": "Accurate, complete, modern, readable historical translation.",
    "alignment": "Translate each source unit faithfully; keep chronology, names, dates, and causal claims precise.",
    "japanese": "Use natural modern Japanese. Do not output Chinese prose in the Japanese field.",
    "chinese": "Use natural modern Chinese. Preserve specialized historical terms and provide readable equivalents.",
    "grammar": "Grammar-role analysis is required later; keep sentence units clear for role tagging.",
}

LEADERSHIP_CONTRACT = {
    "style": "Accurate, practical, modern business/leadership translation.",
    "alignment": "Preserve examples, advice, conceptual distinctions, and tone without summary or unsupported additions.",
    "japanese": "Use natural modern Japanese suitable for business readers.",
    "chinese": "Use clear modern Chinese suitable for business readers.",
    "grammar": "Grammar-role analysis is required later; keep sentence units clear for role tagging.",
}

LITERARY_CONTRACT = {
    "style": "Faithful literary translation with natural, elegant modern Japanese and Chinese.",
    "alignment": "Preserve paragraph-by-paragraph meaning, imagery, dialogue, character names, and narrative sequence. Do not summarize.",
    "japanese": "Use readable modern Japanese literary prose. Do not output Chinese prose in the Japanese field.",
    "chinese": "Use polished modern Chinese literary prose.",
    "grammar": "Grammar-role analysis is required later; preserve clean sentence units for role tagging.",
}


def build_history() -> tuple[dict[str, Any], list[dict[str, str]]]:
    copies: list[dict[str, str]] = []
    tasks: list[dict[str, Any]] = []
    specs = [
        dict(
            priority=1,
            book_id="rise-fall-ancient-egypt",
            title_en="The Rise and Fall of Ancient Egypt",
            title_zh="古埃及的兴衰",
            title_ja="古代エジプトの興亡",
            author="Toby Wilkinson",
            source_path="sources/world-history/ancient-egypt/en/The Rise and Fall of Ancient Egypt - Toby Wilkinson.pdf",
            source_from_books="resources/curated-books/grand-empire-history/egypt/en/user-downloads/Toby Wilkinson - The Rise and Fall of Ancient Egypt - Random House 2011.pdf",
            min_chunk_count=120,
        ),
        dict(
            priority=2,
            book_id="lost-enlightenment-central-asia",
            title_en="Lost Enlightenment: Central Asia's Golden Age from the Arab Conquest to Tamerlane",
            title_zh="失落的启蒙：从阿拉伯征服到帖木儿时代的中亚黄金时代",
            title_ja="失われた啓蒙：アラブ征服からティムールまでの中央アジア黄金時代",
            author="S. Frederick Starr",
            source_path="sources/world-history/central-asia/en/Lost Enlightenment - S Frederick Starr.pdf",
            source_from_books="resources/curated-books/grand-empire-history/central-asia/en/user-downloads/S Frederick Starr - Lost Enlightenment - Princeton 2013.pdf",
            body_start_markers=["The Center of the World"],
            min_chunk_count=160,
        ),
    ]
    for spec in specs:
        item, item_copies = task(**spec, translation_contract=HISTORY_CONTRACT)
        tasks.append(item)
        copies.extend(item_copies)
    return queue(
        queue_id="imported-history-trilingual-20260712",
        model="gpt-5.3-codex-spark",
        reasoning="low",
        workers=10,
        tasks=tasks,
        contract="History books imported from ../Books on 2026-07-12. Generate EN-JP-ZH modern trilingual PocketPolyglot tasks.",
    ), copies


def build_leadership() -> tuple[dict[str, Any], list[dict[str, str]]]:
    copies: list[dict[str, str]] = []
    tasks: list[dict[str, Any]] = []
    specs = [
        dict(
            priority=1,
            book_id="seven-habits-effective-people",
            title_en="The 7 Habits of Highly Effective People",
            title_zh="高效能人士的七个习惯",
            title_ja="7つの習慣",
            author="Stephen R. Covey and Sean Covey",
            source_path="sources/leadership/7-habits/en/The 7 Habits of Highly Effective People - Stephen R Covey and Sean Covey.epub",
            source_from_books="resources/curated-books/leadership/modern/7-habits/Stephen R Covey and Sean Covey - The 7 Habits of Highly Effective People - 30th Anniversary 2020.epub",
            copy_refs={
                "resources/curated-books/leadership/modern/7-habits/Stephen R Covey and Sean Covey - The 7 Habits of Highly Effective People - 30th Anniversary 2020.pdf": "sources/leadership/7-habits/en/The 7 Habits of Highly Effective People - Stephen R Covey and Sean Covey.pdf",
            },
            min_chunk_count=120,
        ),
        dict(
            priority=2,
            book_id="multipliers-leadership",
            title_en="Multipliers",
            title_zh="乘数效应",
            title_ja="メンバーの力を引き出すリーダー",
            author="Liz Wiseman",
            source_path="sources/leadership/multipliers/en/Multipliers - Liz Wiseman.pdf",
            source_from_books="resources/curated-books/leadership/modern/multipliers/Liz Wiseman - Multipliers - Revised and Updated 2017.pdf",
            min_chunk_count=90,
        ),
        dict(
            priority=3,
            book_id="five-dysfunctions-team",
            title_en="The Five Dysfunctions of a Team",
            title_zh="团队协作的五大障碍",
            title_ja="チームの五つの機能不全",
            author="Patrick Lencioni",
            source_path="sources/leadership/five-dysfunctions-team/en/The Five Dysfunctions of a Team - Patrick Lencioni.pdf",
            source_from_books="resources/curated-books/leadership/modern/five-dysfunctions-team/Patrick Lencioni - The Five Dysfunctions of a Team - Jossey-Bass 2002.pdf",
            copy_refs={
                "resources/curated-books/leadership/modern/five-dysfunctions-team/Patrick Lencioni - The Five Dysfunctions of a Team - large-pdf.pdf": "sources/leadership/five-dysfunctions-team/en/The Five Dysfunctions of a Team - Patrick Lencioni - large reference.pdf",
            },
            min_chunk_count=50,
        ),
        dict(
            priority=4,
            book_id="leadership-21-laws",
            title_en="The 21 Irrefutable Laws of Leadership",
            title_zh="领导力21法则",
            title_ja="リーダーシップ21の法則",
            author="John C. Maxwell",
            source_path="sources/leadership/21-irrefutable-laws/en/The 21 Irrefutable Laws of Leadership - John C Maxwell.pdf",
            source_from_books="resources/curated-books/leadership/modern/21-irrefutable-laws/John C Maxwell - The 21 Irrefutable Laws of Leadership - HarperCollins 2007.pdf",
            min_chunk_count=60,
            start_marker="Every book is a conversation between the author",
        ),
        dict(
            priority=5,
            book_id="good-to-great-leadership",
            title_en="Good to Great",
            title_zh="从优秀到卓越",
            title_ja="ビジョナリー・カンパニー2 飛躍の法則",
            author="Jim Collins",
            source_path="sources/leadership/good-to-great/en/Good to Great - Jim Collins.pdf",
            source_from_books="resources/curated-books/leadership/modern/good-to-great/Jim Collins - Good to Great - HarperBusiness 2001.pdf",
            min_chunk_count=60,
        ),
        dict(
            priority=6,
            book_id="radical-candor",
            title_en="Radical Candor",
            title_zh="绝对坦率",
            title_ja="ラディカル・キャンダー",
            author="Kim Scott",
            source_path="sources/leadership/radical-candor/en/Radical Candor - Kim Scott.pdf",
            source_from_books="resources/curated-books/leadership/modern/radical-candor/Kim Scott - Radical Candor - 2019.pdf",
            min_chunk_count=100,
        ),
        dict(
            priority=7,
            book_id="leadership-self-deception",
            title_en="Leadership and Self-Deception",
            title_zh="领导力与自欺",
            title_ja="リーダーシップと自己欺瞞",
            author="The Arbinger Institute",
            source_path="sources/leadership/leadership-and-self-deception/en/Leadership and Self-Deception - The Arbinger Institute.pdf",
            source_from_books="resources/curated-books/leadership/modern/leadership-and-self-deception/The Arbinger Institute - Leadership and Self-Deception - Fourth Edition 2024.pdf",
            min_chunk_count=50,
        ),
        dict(
            priority=8,
            book_id="leadership-challenge",
            title_en="The Leadership Challenge",
            title_zh="领导力挑战",
            title_ja="リーダーシップ・チャレンジ",
            author="James M. Kouzes and Barry Z. Posner",
            source_path="sources/leadership/leadership-challenge/en/The Leadership Challenge - Kouzes and Posner.epub",
            source_from_books="resources/curated-books/leadership/modern/leadership-challenge/Kouzes and Posner - The Leadership Challenge - Jossey-Bass 2017.epub",
            copy_refs={
                "resources/curated-books/leadership/modern/leadership-challenge/Kouzes and Posner - The Leadership Challenge - Jossey-Bass 2017.pdf": "sources/leadership/leadership-challenge/en/The Leadership Challenge - Kouzes and Posner.pdf",
            },
            min_chunk_count=120,
        ),
        dict(
            priority=9,
            book_id="leaders-eat-last",
            title_en="Leaders Eat Last",
            title_zh="领导者最后吃",
            title_ja="リーダーは最後に食べなさい",
            author="Simon Sinek",
            source_path="sources/leadership/leaders-eat-last/en/Leaders Eat Last - Simon Sinek.epub",
            source_from_books="resources/curated-books/leadership/modern/leaders-eat-last/Simon Sinek - Leaders Eat Last - Penguin 2014.epub",
            start_marker="I know of no case study in history",
            min_chunk_count=100,
        ),
        dict(
            priority=10,
            book_id="turn-the-ship-around",
            title_en="Turn the Ship Around!",
            title_zh="把船调过来",
            title_ja="船を立て直せ！",
            author="L. David Marquet",
            source_path="sources/leadership/turn-the-ship-around/en/Turn the Ship Around - L David Marquet.epub",
            source_from_books="resources/curated-books/leadership/modern/turn-the-ship-around/L David Marquet - Turn the Ship Around - Portfolio 2013.epub",
            min_chunk_count=70,
        ),
        dict(
            priority=11,
            book_id="on-becoming-a-leader",
            title_en="On Becoming a Leader",
            title_zh="成为领导者",
            title_ja="リーダーになる",
            author="Warren Bennis",
            source_path="sources/leadership/on-becoming-a-leader/en/On Becoming a Leader - Warren Bennis.pdf",
            source_from_books="resources/curated-books/leadership/modern/on-becoming-a-leader/Warren Bennis - On Becoming a Leader - Basic Books 2009.pdf",
            min_chunk_count=40,
        ),
        dict(
            priority=12,
            book_id="effective-executive-drucker",
            title_en="The Effective Executive",
            title_zh="卓有成效的管理者",
            title_ja="経営者の条件",
            author="Peter F. Drucker",
            source_path="sources/leadership/effective-executive/en/The Effective Executive - Peter F Drucker.pdf",
            source_from_books="resources/curated-books/leadership/modern/effective-executive/Peter F Drucker - The Effective Executive - HarperBusiness 2006.pdf",
            min_chunk_count=40,
        ),
    ]
    for spec in specs:
        item, item_copies = task(**spec, translation_contract=LEADERSHIP_CONTRACT)
        tasks.append(item)
        copies.extend(item_copies)
    return queue(
        queue_id="imported-leadership-trilingual-20260712",
        model="gpt-5.5",
        reasoning="low",
        workers=10,
        tasks=tasks,
        contract="Leadership books imported from ../Books on 2026-07-12. Generate EN-JP-ZH modern trilingual PocketPolyglot tasks.",
    ), copies


def gutenberg(slug: str, filename: str) -> str:
    source_slug = {
        "swanns-way": "in-search-of-lost-time",
    }.get(slug, slug)
    return f"resources/curated-books/public-domain-world-literature-gutenberg/{source_slug}/en-gutenberg/{filename}"


def libgen(slug: str, filename: str) -> str:
    return f"resources/curated-books/world-literature/libgen-li-downloads/{slug}/{filename}"


def build_world_classics() -> tuple[dict[str, Any], list[dict[str, str]]]:
    copies: list[dict[str, str]] = []
    tasks: list[dict[str, Any]] = []
    specs = [
        ("don-quixote", "Don Quixote", "堂吉诃德", "ドン・キホーテ", "Miguel de Cervantes", "996.epub", libgen("don-quixote", "Miguel de Cervantes - Don Quixote.pdf"), 300),
        ("robinson-crusoe", "Robinson Crusoe", "鲁滨逊漂流记", "ロビンソン・クルーソー", "Daniel Defoe", "521.epub", libgen("robinson-crusoe", "Daniel Defoe - Robinson Crusoe - Signet Classics 2008.epub"), 120),
        ("oliver-twist", "Oliver Twist", "雾都孤儿", "オリバー・ツイスト", "Charles Dickens", "730.epub", libgen("oliver-twist", "Charles Dickens - Oliver Twist - Oakshot Press.epub"), 160),
        ("pride-and-prejudice", "Pride and Prejudice", "傲慢与偏见", "高慢と偏見", "Jane Austen", "1342.epub", libgen("pride-and-prejudice", "Jane Austen - Pride and Prejudice - Cambridge Edition 2006.pdf"), 120),
        ("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "グレート・ギャツビー", "F. Scott Fitzgerald", "64317.epub", libgen("great-gatsby", "F Scott Fitzgerald - The Great Gatsby - 2021.pdf"), 50),
        ("the-stranger", "The Stranger", "局外人", "異邦人", "Albert Camus", None, libgen("the-stranger", "Albert Camus - The Stranger.pdf"), 30),
        ("old-man-and-the-sea", "The Old Man and the Sea", "老人与海", "老人と海", "Ernest Hemingway", None, libgen("old-man-and-the-sea", "Ernest Hemingway - The Old Man and the Sea - Scribner 1952.pdf"), 30),
        ("steppenwolf", "Steppenwolf", "荒原狼", "荒野のおおかみ", "Hermann Hesse", None, libgen("steppenwolf", "Hermann Hesse - Steppenwolf.pdf"), 40),
        ("swanns-way", "Swann's Way", "在斯万家那边", "スワン家のほうへ", "Marcel Proust", "7178.epub", libgen("in-search-of-lost-time", "Marcel Proust - Swanns Way - Modern Library 1992.pdf"), 180),
        ("gullivers-travels", "Gulliver's Travels", "格列佛游记", "ガリヴァー旅行記", "Jonathan Swift", "829.epub", libgen("gullivers-travels", "Jonathan Swift - Gullivers Travels - Oxford Worlds Classics 2005.pdf"), 120),
        ("david-copperfield", "David Copperfield", "大卫·科波菲尔", "デイヴィッド・コパフィールド", "Charles Dickens", "766.epub", libgen("david-copperfield", "Charles Dickens - David Copperfield - 1997.pdf"), 300),
        ("tale-of-two-cities", "A Tale of Two Cities", "双城记", "二都物語", "Charles Dickens", "98.epub", libgen("tale-of-two-cities", "Charles Dickens - A Tale of Two Cities - Bunny Books 2010.pdf"), 120),
        ("resurrection", "Resurrection", "复活", "復活", "Leo Tolstoy", "1938.epub", libgen("resurrection", "Leo Tolstoy - Resurrection - Floating Press 2011.pdf"), 180),
        ("brothers-karamazov", "The Brothers Karamazov", "卡拉马佐夫兄弟", "カラマーゾフの兄弟", "Fyodor Dostoevsky", "28054.epub", libgen("brothers-karamazov", "Fyodor Dostoevsky - The Brothers Karamazov - Planet PDF 2004.pdf"), 250),
        ("crime-and-punishment", "Crime and Punishment", "罪与罚", "罪と罰", "Fyodor Dostoevsky", "2554.epub", libgen("crime-and-punishment", "Fyodor Dostoevsky - Crime and Punishment - Barnes and Noble 1994.pdf"), 180),
        ("red-and-black", "The Red and the Black", "红与黑", "赤と黒", "Stendhal", "44747.epub", libgen("red-and-black", "Stendhal - The Red and the Black - Modern Library 2004.pdf"), 180),
        ("madame-bovary", "Madame Bovary", "包法利夫人", "ボヴァリー夫人", "Gustave Flaubert", "2413.epub", libgen("madame-bovary", "Gustave Flaubert - Madame Bovary - 2005.pdf"), 120),
        ("moon-and-sixpence", "The Moon and Sixpence", "月亮和六便士", "月と六ペンス", "W. Somerset Maugham", "222.epub", libgen("moon-and-sixpence", "W Somerset Maugham - The Moon and Sixpence - Penn State 2001.pdf"), 80),
        ("anna-karenina", "Anna Karenina", "安娜·卡列尼娜", "アンナ・カレーニナ", "Leo Tolstoy", "1399.epub", libgen("anna-karenina", "Leo Tolstoy - Anna Karenina - Yale 2014.pdf"), 300),
        ("three-musketeers", "The Three Musketeers", "三个火枪手", "三銃士", "Alexandre Dumas", "1257.epub", libgen("three-musketeers", "Alexandre Dumas - The Three Musketeers - Viking 2006.pdf"), 250),
        ("war-and-peace", "War and Peace", "战争与和平", "戦争と平和", "Leo Tolstoy", "2600.epub", libgen("war-and-peace", "Leo Tolstoy - War and Peace - 1968.pdf"), 500),
    ]
    for index, (slug, title_en, title_zh, title_ja, author, epub_name, reference, min_chunks) in enumerate(specs, start=1):
        if epub_name:
            source_from_books = gutenberg(slug, epub_name)
            suffix = ".epub"
        else:
            source_from_books = reference
            suffix = Path(reference).suffix
            reference = ""
        source_path = f"sources/world-literature/{slug}/en/{title_en.replace(':', ' -').replace('/', '-')}{suffix}"
        copy_refs = {}
        if reference:
            copy_refs[reference] = f"sources/world-literature/{slug}/en/reference/{Path(reference).name}"
        item, item_copies = task(
            priority=index,
            book_id=slug,
            title_en=title_en,
            title_zh=title_zh,
            title_ja=title_ja,
            author=author,
            source_path=source_path,
            source_from_books=source_from_books,
            copy_refs=copy_refs,
            min_chunk_count=min_chunks,
            task_mode="trilingual_world_literature_en_source_generated_zh_ja",
            translation_contract=LITERARY_CONTRACT,
        )
        tasks.append(item)
        copies.extend(item_copies)
    return queue(
        queue_id="imported-world-classics-trilingual-20260712",
        model="gpt-5.5",
        reasoning="low",
        workers=10,
        tasks=tasks,
        contract="World classics imported from ../Books on 2026-07-12. Prefer Gutenberg/public-domain spine where available and retain LibGen downloads as supplemental references.",
    ), copies


def queue(*, queue_id: str, model: str, reasoning: str, workers: int, tasks: list[dict[str, Any]], contract: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "queue_id": queue_id,
        "status": "prepared_sources",
        "model": model,
        "reasoning": reasoning,
        "workers": workers,
        "task_family": "modern_en_jp_zh_imported_20260712",
        "source_spine_lang": "en",
        "output_languages": ["en", "ja", "zh"],
        "generation_contract": {
            "translation_quality": "Accurate, complete, modern, understandable, polished Japanese and Chinese. Do not summarize or omit nuance.",
            "grammar_analysis": "Required. Use normalized grammar roles so color and black-white outputs can be compiled from the same JSON.",
            "source_quality": "Use cleaned extracted Markdown as the chunk spine. Keep supplemental sources as references, not as unaligned duplicate text.",
            "final_outputs": "After generation, compile maximum-language large-font color and black-white PDFs with cover and TOC.",
            "batch_note": contract,
        },
        "created_at": NOW,
        "tasks": tasks,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_doc(queues: dict[str, dict[str, Any]], copies: list[dict[str, str]]) -> None:
    lines = [
        "# Imported Modern Queues - 2026-07-12",
        "",
        "This records the ZhJpBook task preparation for the leadership, world classics, and history downloads first organized in `../Books`.",
        "",
        "Original files remain in `../Books` and ignored `sources/`; only queue metadata, manifests, and this reference note are tracked.",
        "",
        "## Queue Files",
        "",
        "| Queue | Model | Workers | Books | Source spine | Output languages |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for queue_path, data in queues.items():
        lines.append(
            f"| `{queue_path}` | `{data['model']} {data['reasoning']}` | {data['workers']} | "
            f"{len(data['tasks'])} | `{data['source_spine_lang']}` | `{', '.join(data['output_languages'])}` |"
        )
    lines.extend(["", "## Books", "", "| Queue | Priority | Book ID | English title | Source path | References |", "| --- | ---: | --- | --- | --- | ---: |"])
    for queue_path, data in queues.items():
        for item in data["tasks"]:
            lines.append(
                f"| `{Path(queue_path).name}` | {item['priority']} | `{item['book_id']}` | "
                f"{item['title_en']} | `{item['source_path']}` | {len(item.get('reference_paths', {}))} |"
            )
    lines.extend(["", "## Copied Source Files", "", "| Status | Destination | Size | SHA-256 |", "| --- | --- | ---: | --- |"])
    for item in copies:
        lines.append(
            f"| `{item['status']}` | `{item['destination']}` | {item['size_bytes']} | `{item['sha256_16']}` |"
        )
    lines.append("")
    path = ROOT / "references/IMPORTED_MODERN_QUEUES_2026-07-12.md"
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="copy sources and write queue files")
    args = parser.parse_args()
    if not args.write:
        raise SystemExit("pass --write to update sources and queue files")

    builders = {
        "data/source-plan/imported-history-trilingual-queue.json": build_history,
        "data/source-plan/imported-leadership-trilingual-queue.json": build_leadership,
        "data/source-plan/imported-world-classics-trilingual-queue.json": build_world_classics,
    }
    queues: dict[str, dict[str, Any]] = {}
    all_copies: list[dict[str, str]] = []
    for queue_rel, builder in builders.items():
        data, copies = builder()
        queues[queue_rel] = data
        all_copies.extend(copies)
        write_json(ROOT / queue_rel, data)
    write_doc(queues, all_copies)
    print(f"wrote {len(queues)} queues and copied/verified {len(all_copies)} source files")
    for queue_rel, data in queues.items():
        print(f"{queue_rel}: {len(data['tasks'])} tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
