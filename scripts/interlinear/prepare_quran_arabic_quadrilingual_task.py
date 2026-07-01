#!/usr/bin/env python3
"""Prepare the Quran as an Arabic-spine quadrilingual task.

The output is a source task, not a finished rendered book. It preserves Arabic
Wikisource ayah units, attaches approximate word-level Arabic ruby
transliteration for later rendering, and points writer workers at available
English, Japanese, and Chinese reference mirrors.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from prepare_classical_quadrilingual_task import clean_reference_text, sha256


ROOT = Path(__file__).resolve().parents[2]
ARABIC_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")
SPACE_RE = re.compile(r"\s+")
AR_WORD_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]+|[^\s\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]+")
USTRIP_RE = re.compile(r"[\u0610-\u061a\u06d6-\u06ed]")


SURA_ORDER = [
    ("الفاتحة", "Al-Fatihah", "開端章", "开端章"),
    ("البقرة", "Al-Baqarah", "雌牛章", "黄牛章"),
    ("آل عمران", "Ali Imran", "イムラーン家の章", "仪姆兰的家属章"),
    ("النساء", "An-Nisa", "婦人章", "妇女章"),
    ("المائدة", "Al-Ma'idah", "食卓章", "筵席章"),
    ("الأنعام", "Al-An'am", "家畜章", "牲畜章"),
    ("الأعراف", "Al-A'raf", "高壁章", "高处章"),
    ("الأنفال", "Al-Anfal", "戦利品章", "战利品章"),
    ("التوبة", "At-Tawbah", "悔悟章", "忏悔章"),
    ("يونس", "Yunus", "ユーヌス章", "尤努斯章"),
    ("هود", "Hud", "フード章", "呼德章"),
    ("يوسف", "Yusuf", "ユースフ章", "优素福章"),
    ("الرعد", "Ar-Ra'd", "雷電章", "雷霆章"),
    ("إبراهيم", "Ibrahim", "イブラーヒーム章", "易卜拉欣章"),
    ("الحجر", "Al-Hijr", "ヒジュル章", "石谷章"),
    ("النحل", "An-Nahl", "蜜蜂章", "蜜蜂章"),
    ("الإسراء", "Al-Isra", "夜の旅章", "夜行章"),
    ("الكهف", "Al-Kahf", "洞窟章", "山洞章"),
    ("مريم", "Maryam", "マルヤム章", "麦尔彦章"),
    ("طه", "Ta-Ha", "ター・ハー章", "塔哈章"),
    ("الأنبياء", "Al-Anbiya", "預言者章", "众先知章"),
    ("الحج", "Al-Hajj", "巡礼章", "朝觐章"),
    ("المؤمنون", "Al-Mu'minun", "信者たち章", "信士章"),
    ("النور", "An-Nur", "光章", "光明章"),
    ("الفرقان", "Al-Furqan", "識別章", "准则章"),
    ("الشعراء", "Ash-Shu'ara", "詩人たち章", "众诗人章"),
    ("النمل", "An-Naml", "蟻章", "蚂蚁章"),
    ("القصص", "Al-Qasas", "物語章", "故事章"),
    ("العنكبوت", "Al-'Ankabut", "蜘蛛章", "蜘蛛章"),
    ("الروم", "Ar-Rum", "ローマ章", "罗马人章"),
    ("لقمان", "Luqman", "ルクマーン章", "鲁格曼章"),
    ("السجدة", "As-Sajdah", "跪拝章", "叩头章"),
    ("الأحزاب", "Al-Ahzab", "部族連合章", "同盟军章"),
    ("سبأ", "Saba", "サバア章", "赛伯邑章"),
    ("فاطر", "Fatir", "創造者章", "创造者章"),
    ("يس", "Ya-Sin", "ヤー・スィーン章", "雅辛章"),
    ("الصافات", "As-Saffat", "整列者章", "列班者章"),
    ("ص", "Sad", "サード章", "萨德章"),
    ("الزمر", "Az-Zumar", "集団章", "队伍章"),
    ("غافر", "Ghafir", "赦す方章", "赦宥者章"),
    ("فصلت", "Fussilat", "詳説章", "奉绥来特章"),
    ("الشورى", "Ash-Shura", "相談章", "协商章"),
    ("الزخرف", "Az-Zukhruf", "金の装飾章", "金饰章"),
    ("الدخان", "Ad-Dukhan", "煙霧章", "烟雾章"),
    ("الجاثية", "Al-Jathiyah", "跪く者章", "屈膝章"),
    ("الأحقاف", "Al-Ahqaf", "砂丘章", "沙丘章"),
    ("محمد", "Muhammad", "ムハンマド章", "穆罕默德章"),
    ("الفتح", "Al-Fath", "勝利章", "胜利章"),
    ("الحجرات", "Al-Hujurat", "部屋章", "寝室章"),
    ("ق", "Qaf", "カーフ章", "戛弗章"),
    ("الذاريات", "Adh-Dhariyat", "撒き散らすもの章", "播种者章"),
    ("الطور", "At-Tur", "山章", "山岳章"),
    ("النجم", "An-Najm", "星章", "星宿章"),
    ("القمر", "Al-Qamar", "月章", "月亮章"),
    ("الرحمن", "Ar-Rahman", "慈悲あまねき方章", "至仁主章"),
    ("الواقعة", "Al-Waqi'ah", "出来事章", "大事章"),
    ("الحديد", "Al-Hadid", "鉄章", "铁章"),
    ("المجادلة", "Al-Mujadilah", "抗弁する女章", "辩诉者章"),
    ("الحشر", "Al-Hashr", "集合章", "放逐章"),
    ("الممتحنة", "Al-Mumtahanah", "試される女章", "受考验的妇人章"),
    ("الصف", "As-Saff", "戦列章", "列阵章"),
    ("الجمعة", "Al-Jumu'ah", "金曜章", "聚礼章"),
    ("المنافقون", "Al-Munafiqun", "偽信者たち章", "伪信者章"),
    ("التغابن", "At-Taghabun", "損得章", "相欺章"),
    ("الطلاق", "At-Talaq", "離婚章", "离婚章"),
    ("التحريم", "At-Tahrim", "禁止章", "禁戒章"),
    ("الملك", "Al-Mulk", "王権章", "国权章"),
    ("القلم", "Al-Qalam", "筆章", "笔章"),
    ("الحاقة", "Al-Haqqah", "真実章", "真灾章"),
    ("المعارج", "Al-Ma'arij", "階段章", "天梯章"),
    ("نوح", "Nuh", "ヌーフ章", "努哈章"),
    ("الجن", "Al-Jinn", "ジン章", "精灵章"),
    ("المزمل", "Al-Muzzammil", "衣を纏う者章", "披衣的人章"),
    ("المدثر", "Al-Muddaththir", "包まる者章", "盖被的人章"),
    ("القيامة", "Al-Qiyamah", "復活章", "复活章"),
    ("الإنسان", "Al-Insan", "人間章", "人章"),
    ("المرسلات", "Al-Mursalat", "遣わされるもの章", "天使章"),
    ("النبأ", "An-Naba", "消息章", "消息章"),
    ("النازعات", "An-Nazi'at", "引き抜くもの章", "急掣章"),
    ("عبس", "'Abasa", "眉をひそめた章", "皱眉章"),
    ("التكوير", "At-Takwir", "巻き上げ章", "黯黮章"),
    ("الانفطار", "Al-Infitar", "裂ける章", "破裂章"),
    ("المطففين", "Al-Mutaffifin", "量を減らす者章", "称量不公章"),
    ("الانشقاق", "Al-Inshiqaq", "割れる章", "破裂章"),
    ("البروج", "Al-Buruj", "星座章", "宫分章"),
    ("الطارق", "At-Tariq", "夜訪れるもの章", "启明星章"),
    ("الأعلى", "Al-A'la", "至高者章", "至尊章"),
    ("الغاشية", "Al-Ghashiyah", "覆うもの章", "大灾章"),
    ("الفجر", "Al-Fajr", "暁章", "黎明章"),
    ("البلد", "Al-Balad", "町章", "地方章"),
    ("الشمس", "Ash-Shams", "太陽章", "太阳章"),
    ("الليل", "Al-Layl", "夜章", "黑夜章"),
    ("الضحى", "Ad-Duha", "朝章", "上午章"),
    ("الشرح", "Ash-Sharh", "胸を広げる章", "开拓章"),
    ("التين", "At-Tin", "無花果章", "无花果章"),
    ("العلق", "Al-'Alaq", "凝血章", "血块章"),
    ("القدر", "Al-Qadr", "みいつ章", "高贵章"),
    ("البينة", "Al-Bayyinah", "明証章", "明证章"),
    ("الزلزلة", "Az-Zalzalah", "地震章", "地震章"),
    ("العاديات", "Al-'Adiyat", "疾走する馬章", "奔跑者章"),
    ("القارعة", "Al-Qari'ah", "打ち叩くもの章", "大难章"),
    ("التكاثر", "At-Takathur", "富の競争章", "竞赛富庶章"),
    ("العصر", "Al-'Asr", "時章", "时光章"),
    ("الهمزة", "Al-Humazah", "中傷者章", "诽谤者章"),
    ("الفيل", "Al-Fil", "象章", "象章"),
    ("قريش", "Quraysh", "クライシュ章", "古来氏章"),
    ("الماعون", "Al-Ma'un", "日用品章", "什物章"),
    ("الكوثر", "Al-Kawthar", "潤沢章", "多福章"),
    ("الكافرون", "Al-Kafirun", "不信者たち章", "不信道者章"),
    ("النصر", "An-Nasr", "援助章", "援助章"),
    ("المسد", "Al-Masad", "棕櫚縄章", "火焰章"),
    ("الإخلاص", "Al-Ikhlas", "純正章", "忠诚章"),
    ("الفلق", "Al-Falaq", "黎明章", "曙光章"),
    ("الناس", "An-Nas", "人々章", "世人章"),
]

ARABIC_TRANSLIT = {
    "ا": "a",
    "أ": "a",
    "إ": "i",
    "آ": "a",
    "ٱ": "a",
    "ء": "'",
    "ؤ": "u'",
    "ئ": "i'",
    "ب": "b",
    "ت": "t",
    "ث": "th",
    "ج": "j",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "dh",
    "ر": "r",
    "ز": "z",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "d",
    "ط": "t",
    "ظ": "z",
    "ع": "`",
    "غ": "gh",
    "ف": "f",
    "ق": "q",
    "ك": "k",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "ه": "h",
    "ة": "h",
    "و": "w",
    "ى": "a",
    "ي": "y",
    "َ": "a",
    "ِ": "i",
    "ُ": "u",
    "ً": "an",
    "ٍ": "in",
    "ٌ": "un",
    "ْ": "",
    "ۡ": "",
    "ٰ": "a",
    "ٓ": "",
    "ٔ": "'",
    "ۢ": "",
    "ۭ": "",
    "ۥ": "hu",
    "ۦ": "hi",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compact(text: str) -> str:
    return SPACE_RE.sub(" ", str(text or "")).strip()


def title_tail(title: str) -> str:
    return str(title).rsplit("/", 1)[-1].removeprefix("سورة ").strip()


def source_url(item: dict[str, Any]) -> str:
    return str(item.get("source_url") or "")


def read_html(source_dir: Path, item: dict[str, Any]) -> str:
    rel = item.get("html") or item.get("html_path")
    if not rel:
        return ""
    return (source_dir / rel).read_text(encoding="utf-8", errors="replace")


def arabic_number_to_int(text: str) -> int:
    table = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    digits = str(text).translate(table)
    digits = re.sub(r"\D+", "", digits)
    return int(digits) if digits else 0


def transliterate_arabic_word(word: str) -> str:
    out: list[str] = []
    last_consonant = ""
    for char in word:
        if char == "ّ":
            if last_consonant:
                out.append(last_consonant)
            continue
        mapped = ARABIC_TRANSLIT.get(char)
        if mapped is None:
            continue
        out.append(mapped)
        if mapped and char not in {"َ", "ِ", "ُ", "ً", "ٍ", "ٌ", "ْ", "ۡ", "ٰ", "ٓ", "ٔ"}:
            last_consonant = mapped[-1]
    reading = "".join(out)
    reading = re.sub(r"aa+", "a", reading)
    return reading or USTRIP_RE.sub("", word)


def arabic_tokens(text: str) -> list[dict[str, str]]:
    tokens: list[dict[str, str]] = []
    for match in AR_WORD_RE.finditer(text):
        piece = match.group(0)
        if ARABIC_RE.search(piece):
            tokens.append({"t": piece, "r": transliterate_arabic_word(piece)})
        else:
            tokens.append({"t": piece})
    return tokens


def append_text(buffer: list[str], text: str) -> None:
    text = compact(text)
    if text:
        buffer.append(text)


def parse_sura_ayahs(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    block = soup.select_one(".soura-block")
    if block is None:
        return []
    ayahs: list[dict[str, Any]] = []
    buffer: list[str] = []

    def record(number: int) -> None:
        text = compact(" ".join(buffer))
        buffer.clear()
        if text:
            ayahs.append({"ayah": number, "ar": text, "ar_tokens": arabic_tokens(text)})

    def walk(node: Tag | NavigableString) -> None:
        if isinstance(node, NavigableString):
            append_text(buffer, str(node))
            return
        if not isinstance(node, Tag):
            return
        classes = set(node.get("class") or [])
        if "end-of-aya" in classes:
            number_tag = node.select_one(".aya-num")
            record(arabic_number_to_int(number_tag.get_text("", strip=True) if number_tag else "0"))
            return
        if node.name in {"style", "script", "link"}:
            return
        if node.name == "center" and not node.select_one(".end-of-aya"):
            text = compact(node.get_text(" ", strip=True))
            if text:
                ayahs.append({"ayah": 0, "ar": text, "ar_tokens": arabic_tokens(text)})
            return
        for child in node.children:
            walk(child)

    for child in block.children:
        walk(child)
    if buffer:
        record(0)
    return [ayah for ayah in ayahs if ayah["ar"]]


def manifest_pages(source_dir: Path) -> list[dict[str, Any]]:
    manifest = load_json(source_dir / "manifest.json")
    return [page for page in manifest.get("pages", []) if page.get("status") == "ok"]


def source_inventory(path: Path) -> dict[str, Any]:
    manifest = path / "manifest.json"
    if not manifest.exists():
        return {"path": str(path.relative_to(ROOT)), "available": False, "page_count": 0}
    data = load_json(manifest)
    pages = [p for p in data.get("pages", []) if p.get("status") == "ok"]
    return {
        "path": str(path.relative_to(ROOT)),
        "available": bool(pages),
        "page_count": len(pages),
        "sha256": sha256(manifest),
    }


def write_markdown(book_id: str, chapters: list[dict[str, Any]]) -> Path:
    path = ROOT / "books" / book_id / "markdown" / "quran-arabic-source.md"
    lines = ["# القرآن الكريم", ""]
    for chapter in chapters:
        lines.extend([f"## {chapter['number']:03d}. {chapter['title_ar']}", ""])
        for ayah in chapter["ayahs"]:
            label = f"{chapter['number']}:{ayah['ayah']}" if ayah["ayah"] else f"{chapter['number']}:0"
            lines.extend([f"{label} {ayah['ar']}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path


def prepare(*, max_ayahs_per_chunk: int, force: bool) -> None:
    book_id = "quran"
    ar_dir = ROOT / "sources/quran/ar/wikisource-hafs-madina"
    if not (ar_dir / "manifest.json").exists():
        raise FileNotFoundError(ar_dir / "manifest.json")

    out_root = ROOT / "books" / book_id
    chunk_dir = out_root / "work" / "arabic-quadrilingual" / "chunks"
    chunks_jsonl = chunk_dir / "chunks.jsonl"
    manifest_path = chunk_dir / "manifest.json"
    plan_path = out_root / "book-plan.json"
    if chunks_jsonl.exists() and manifest_path.exists() and plan_path.exists() and not force:
        print("quran: already prepared")
        return

    page_by_tail = {title_tail(page.get("actual_title") or page.get("title") or ""): page for page in manifest_pages(ar_dir)}
    chunks: list[dict[str, Any]] = []
    chapters: list[dict[str, Any]] = []
    chunk_counter = 0
    missing_suras: list[str] = []
    source_dirs = {
        "arabic_wikisource_hafs_madina": ar_dir,
        "english_wikisource_pickthall_1930": ROOT / "sources/quran/en/wikisource-pickthall-1930",
        "english_wikisource_rodwell": ROOT / "sources/quran/en/wikisource-rodwell",
        "japanese_wikisource_quran_partial": ROOT / "sources/quran/ja/wikisource-quran",
        "chinese_wikisource_hanyigulanjing": ROOT / "sources/quran/zh/wikisource-hanyigulanjing",
        "chinese_wikisource_gulanjing_yijie_partial": ROOT / "sources/quran/zh/wikisource-gulanjing-yijie",
        "chinese_wikisource_gulanjing_dayi": ROOT / "sources/quran/zh/wikisource-gulanjing-dayi",
    }
    references = {key: source_inventory(path) for key, path in source_dirs.items()}

    for sura_number, (title_ar, title_en, title_ja, title_zh) in enumerate(SURA_ORDER, start=1):
        item = page_by_tail.get(title_ar)
        if not item:
            missing_suras.append(title_ar)
            continue
        ayahs = parse_sura_ayahs(read_html(ar_dir, item))
        if not ayahs:
            missing_suras.append(title_ar)
            continue
        chapters.append({"number": sura_number, "title_ar": title_ar, "ayahs": ayahs})
        for start in range(0, len(ayahs), max_ayahs_per_chunk):
            group = ayahs[start : start + max_ayahs_per_chunk]
            chunk_counter += 1
            first = group[0]["ayah"]
            last = group[-1]["ayah"]
            chunk_id = f"quran-chunk-{chunk_counter:04d}"
            paragraph_id = f"quran-p{chunk_counter:05d}"
            chunk = {
                "schema_version": 1,
                "task_type": "arabic_quadrilingual",
                "book_id": book_id,
                "chunk_id": chunk_id,
                "chapter_id": f"quran-sura-{sura_number:03d}",
                "chapter_number": sura_number,
                "chapter_title_ar": title_ar,
                "chapter_title_en": f"Sura {sura_number}: {title_en}",
                "chapter_title_ja": f"第{sura_number}章 {title_ja}",
                "chapter_title_zh": f"第{sura_number}章 {title_zh}",
                "chapter_part_en": f"{sura_number}:{first}" if first == last else f"{sura_number}:{first}-{last}",
                "source_spine_lang": "ar",
                "paragraphs": [
                    {
                        "id": paragraph_id,
                        "ar": " ".join(unit["ar"] for unit in group),
                        "units": [
                            {
                                "unit_id": f"quran-{sura_number:03d}-{unit['ayah']:03d}",
                                "ayah": unit["ayah"],
                                "ar": unit["ar"],
                                "ar_tokens": unit["ar_tokens"],
                            }
                            for unit in group
                        ],
                    }
                ],
                "reference": {
                    "source_url": source_url(item),
                    "sura": {
                        "number": sura_number,
                        "ar": title_ar,
                        "en": title_en,
                        "ja": title_ja,
                        "zh": title_zh,
                        "ayah_range": f"{first}" if first == last else f"{first}-{last}",
                    },
                    "reference_sources": references,
                    "writer_requirements": [
                        "Preserve Arabic exactly; do not rewrite Arabic source text.",
                        "Use ar_tokens/r as initial Arabic ruby/transliteration, but improve only if the target schema allows a verified better reading.",
                        "Generate or align English, modern Japanese, and modern Chinese for every Arabic unit.",
                        "Add normalized grammar role g to Arabic, English, Japanese, and Chinese tokens where the renderer/schema supports it.",
                    ],
                },
            }
            chunks.append(chunk)

    markdown = write_markdown(book_id, chapters)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunks_jsonl.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")

    source_paths = {key: value["path"] for key, value in references.items()}
    source_paths["arabic_markdown"] = str(markdown.relative_to(ROOT))
    prepared_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": 1,
        "book_id": book_id,
        "status": "prepared",
        "task_mode": "arabic_quadrilingual_main",
        "source_spine_lang": "ar",
        "book_title_ar": "القرآن الكريم",
        "book_title_en": "The Quran",
        "book_title_ja": "クルアーン",
        "book_title_zh": "古蘭經",
        "author": "",
        "chunk_count": len(chunks),
        "chapter_count": len(chapters),
        "missing_suras": missing_suras,
        "chunks": [{"chunk_id": chunk["chunk_id"], "paragraph_ids": [p["id"] for p in chunk["paragraphs"]]} for chunk in chunks],
        "source_paths": source_paths,
        "source_inventory": references,
        "source_sha256": {str(markdown.relative_to(ROOT)): sha256(markdown)},
        "required_features": ["arabic_ruby", "grammar_roles", "english", "modern_japanese", "modern_chinese"],
        "source_note": (
            "Arabic Hafs/Madina Wikisource is the exact source spine. English Pickthall 1930 and Rodwell, "
            "Japanese Wikisource, and Chinese Wikisource mirrors are attached as references where available; "
            "Japanese and Chinese mirrors are partial, so missing units should be generated from Arabic/English references."
        ),
        "prepared_at": prepared_at,
    }
    write_json(manifest_path, manifest)
    plan = {
        "schema_version": 1,
        "book_id": book_id,
        "status": "prepared",
        "launchable": False,
        "task_mode": "arabic_quadrilingual_main",
        "source_language": "ar",
        "book_title_ar": "القرآن الكريم",
        "book_title_en": "The Quran",
        "book_title_ja": "クルアーン",
        "book_title_zh": "古蘭經",
        "book_description": "Arabic Quran source with English, modern Japanese, and modern Chinese aligned learner-book overlays.",
        "chapter_count": len(chapters),
        "chunk_count": len(chunks),
        "missing_suras": missing_suras,
        "source_paths": source_paths,
        "chunks_jsonl": str(chunks_jsonl.relative_to(ROOT)),
        "chunks_manifest": str(manifest_path.relative_to(ROOT)),
        "raw_chunk_dir": "books/quran/work/arabic-quadrilingual/interlinear/chunks",
        "assembled_json": "books/quran/work/arabic-quadrilingual/preview/quran.partial.json",
        "build_root": "build/quran",
        "required_pipeline_work": [
            "Add arabic_quadrilingual writer/validator or extend generic multilingual writer.",
            "Add Arabic ruby/token rendering in XeLaTeX with RTL-safe layout.",
            "Add Arabic grammar-role coloring and validation.",
            "Compile color and blackwhite large-font PDFs after generated chunks validate.",
        ],
        "prepared_at": prepared_at,
    }
    write_json(plan_path, plan)
    print(f"quran: chapters={len(chapters)} chunks={len(chunks)} missing_suras={len(missing_suras)}")
    print(plan_path.relative_to(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-ayahs-per-chunk", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    prepare(max_ayahs_per_chunk=args.max_ayahs_per_chunk, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
