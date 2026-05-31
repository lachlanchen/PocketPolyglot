#!/usr/bin/env python3
"""OCR a fixed-layout image EPUB into page-based Markdown."""

from __future__ import annotations

import argparse
import posixpath
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from PIL import Image, ImageOps


XHTML_NS = {"xhtml": "http://www.w3.org/1999/xhtml"}
OPF_NS = {"opf": "http://www.idpf.org/2007/opf"}


def find_rootfile(epub: ZipFile) -> str:
    xml = ET.fromstring(epub.read("META-INF/container.xml"))
    rootfile = xml.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
    if rootfile is None:
        raise ValueError("container.xml has no rootfile")
    return rootfile.attrib["full-path"]


def spine_text_paths(epub: ZipFile, opf_path: str) -> list[str]:
    root = ET.fromstring(epub.read(opf_path))
    base = PurePosixPath(opf_path).parent
    manifest: dict[str, str] = {}
    for item in root.findall(".//opf:manifest/opf:item", OPF_NS):
        item_id = item.attrib.get("id")
        href = item.attrib.get("href")
        if item_id and href:
            manifest[item_id] = str(base / href)

    paths: list[str] = []
    for itemref in root.findall(".//opf:spine/opf:itemref", OPF_NS):
        href = manifest.get(itemref.attrib.get("idref", ""))
        if href and href.lower().endswith((".xhtml", ".html", ".htm")):
            paths.append(href)
    return paths


def nav_titles(epub: ZipFile) -> dict[str, str]:
    nav_candidates = [name for name in epub.namelist() if name.lower().endswith("nav.xhtml")]
    if not nav_candidates:
        return {}
    nav_path = nav_candidates[0]
    base = PurePosixPath(nav_path).parent
    root = ET.fromstring(epub.read(nav_path))
    titles: dict[str, str] = {}
    for link in root.findall(".//xhtml:a", XHTML_NS):
        href = link.attrib.get("href", "").split("#", 1)[0]
        title = "".join(link.itertext()).strip()
        if href and title:
            titles[str(base / href)] = title.replace("・", " ")
    return titles


def image_for_page(epub: ZipFile, page_path: str) -> str | None:
    root = ET.fromstring(epub.read(page_path))
    image = root.find(".//xhtml:img", XHTML_NS)
    if image is None:
        return None
    src = image.attrib.get("src")
    if not src:
        return None
    return posixpath.normpath(str(PurePosixPath(page_path).parent / src))


def preprocess_image(source: Path, target: Path, *, scale: int, threshold: int) -> None:
    image = Image.open(source)
    image = ImageOps.grayscale(image)
    if scale != 1:
        image = image.resize((image.width * scale, image.height * scale))
    image = ImageOps.autocontrast(image)
    if threshold:
        image = image.point(lambda pixel: 255 if pixel > threshold else 0)
    image.save(target)


def run_tesseract(image: Path, *, lang: str, psm: int) -> str:
    proc = subprocess.run(
        ["tesseract", str(image), "stdout", "-l", lang, "--psm", str(psm)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return clean_ocr(proc.stdout)


def clean_ocr(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        line = re.sub(r"[ \t]+", " ", line)
        if line:
            lines.append(line)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epub")
    parser.add_argument("--output", required=True)
    parser.add_argument("--title", default="こころ")
    parser.add_argument("--lang", default="jpn_vert")
    parser.add_argument("--psm", type=int, default=5)
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--threshold", type=int, default=0, help="0 disables thresholding")
    parser.add_argument("--start-title", default="")
    parser.add_argument("--max-pages", type=int, default=0, help="0 means all pages")
    args = parser.parse_args()

    epub_path = Path(args.epub)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(epub_path) as epub:
        opf_path = find_rootfile(epub)
        pages = spine_text_paths(epub, opf_path)
        titles = nav_titles(epub)
        if args.start_title:
            start_at = None
            for index, page in enumerate(pages):
                if titles.get(page, "") == args.start_title:
                    start_at = index
                    break
            if start_at is not None:
                pages = pages[start_at:]
        if args.max_pages:
            pages = pages[: args.max_pages]

        out: list[str] = [f"# {args.title}", ""]
        with tempfile.TemporaryDirectory(prefix="zhjpbook-ocr-") as tmp:
            tmp_path = Path(tmp)
            for index, page in enumerate(pages, 1):
                page_title = titles.get(page)
                if page_title and not page_title.startswith("（"):
                    out.extend([f"## {page_title}", ""])

                image_path = image_for_page(epub, page)
                if not image_path:
                    continue
                suffix = Path(image_path).suffix or ".png"
                extracted = tmp_path / f"page-{index:04d}{suffix}"
                processed = tmp_path / f"page-{index:04d}.png"
                extracted.write_bytes(epub.read(image_path))
                preprocess_image(extracted, processed, scale=args.scale, threshold=args.threshold)
                text = run_tesseract(processed, lang=args.lang, psm=args.psm)
                if text:
                    out.extend(
                        [
                            f"<!-- page: {page} image: {image_path} -->",
                            "",
                            text,
                            "",
                        ]
                    )

    output.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
