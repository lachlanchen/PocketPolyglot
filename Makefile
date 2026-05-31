PDF ?= sources/中国民间故事集成 四川卷 上 10978512.pdf
PAGES ?= 60-62
DPI ?= 300
OCR_LANG ?= chi_sim
PSM ?= 4
WORKERS ?= 4
INTERLINEAR_DATA ?= data/interlinear/sample.json
PAIRED_DATA ?= data/paired/source.md
JP_MAIN_AUTHOR ?= 夏目漱石
JP_MAIN_CURATOR ?= AgInTiFlow curated
JP_MAIN_URL ?= https://flow.lazying.art
JP_MAIN_POWERED_BY ?= powered by LazyingArt
JP_MAIN_COVER ?=

.PHONY: sample paired interlinear interlinear-run interlinear-jp-main compare export-books readme-previews edition-comparison sentence-showcase readme-assets kokoro-md kokoro-tmux kokoro-bilingual-md kokoro-bilingual-tmux kokoro-compile kokoro-jp-ocr-md snow-country-prepare snow-country-tmux snow-country-after-kokoro snow-country-compile ocr-sample ocr-all clean

sample: paired

paired: build/paired/book.pdf

interlinear: build/interlinear-block/book.pdf

interlinear-run: build/interlinear-run/book.pdf

interlinear-jp-main: build/interlinear-jp-main/book.pdf

compare: interlinear interlinear-run interlinear-jp-main

export-books:
	python scripts/books/export_flat_build_pdfs.py

readme-previews: export-books
	python scripts/books/generate_readme_previews.py

edition-comparison: export-books
	python scripts/books/generate_edition_comparison.py --book-id kokoro --page 20

sentence-showcase: export-books
	python scripts/books/generate_sentence_showcase.py

readme-assets: readme-previews edition-comparison sentence-showcase

kokoro-md:
	python scripts/books/epub_to_markdown.py sources/心.epub --raw-output books/kokoro/markdown/book.raw.md --clean-output books/kokoro/markdown/book.md --start-heading 总序

kokoro-tmux:
	prompt_tools/interlinear-book/start-book-tmux.sh --no-attach -- --epub sources/心.epub --book-id kokoro --title-zh 心 --title-zh-reading xīn --title-ja 心 --title-ja-reading こころ --model gpt-5.5 --reasoning high

kokoro-bilingual-md:
	python scripts/books/epub_to_markdown.py sources/心.epub --raw-output books/kokoro/markdown/book.raw.md --clean-output books/kokoro/markdown/book.md --start-heading 总序
	python scripts/books/epub_to_markdown.py "sources/夏目 漱石 作品全集.epub" --raw-output books/natsume-complete/markdown/book.raw.md --clean-output books/natsume-complete/markdown/book.md
	python scripts/books/extract_markdown_section.py books/kokoro/markdown/book.md --start-heading 心 --output books/kokoro/markdown/zh.md
	python scripts/books/extract_markdown_section.py books/natsume-complete/markdown/book.md --start-heading "第25章 こころ (新字新仮名)" --output books/kokoro/markdown/ja.section.md
	python scripts/books/normalize_kokoro_jp_markdown.py books/kokoro/markdown/ja.section.md --output books/kokoro/markdown/ja.md --title こころ

kokoro-bilingual-tmux:
	prompt_tools/interlinear-book/start-bilingual-book-tmux.sh --no-attach -- --zh-epub sources/心.epub --jp-epub "sources/夏目 漱石 作品全集.epub" --book-id kokoro --title-zh 心 --title-zh-reading xīn --title-ja こころ --title-ja-reading こころ --model gpt-5.5 --reasoning xhigh --output-pdf "build/kokoro/zh-main/color/心（こころ）.pdf"

kokoro-compile:
	bash scripts/interlinear/compile_kokoro_both_previews.sh

kokoro-jp-ocr-md:
	python scripts/books/ocr_image_epub_to_markdown.py sources/こころ.epub --output books/kokoro-jp/markdown/book.md --title こころ --lang jpn_vert --psm 5

snow-country-prepare:
	bash scripts/interlinear/prepare_snow_country_sources.sh

snow-country-tmux:
	bash scripts/interlinear/start_snow_country_parallel_json_tmux.sh

snow-country-after-kokoro:
	bash scripts/interlinear/start_snow_country_after_kokoro_tmux.sh

snow-country-compile:
	bash scripts/interlinear/compile_snow_country_both_previews.sh

build/paired/source.tex: $(PAIRED_DATA) scripts/paired/md_to_tex.py
	python scripts/paired/md_to_tex.py $(PAIRED_DATA) -o build/paired/source.tex

build/paired/book.pdf: build/paired/source.tex tex/paired/book.tex tex/paired/style.tex
	mkdir -p build/paired
	xelatex -interaction=nonstopmode -halt-on-error -output-directory=build/paired tex/paired/book.tex
	xelatex -interaction=nonstopmode -halt-on-error -output-directory=build/paired tex/paired/book.tex

build/interlinear-block/source.tex: $(INTERLINEAR_DATA) scripts/interlinear/json_to_block_tex.py
	python scripts/interlinear/json_to_block_tex.py $(INTERLINEAR_DATA) -o build/interlinear-block/source.tex

build/interlinear-block/book.pdf: build/interlinear-block/source.tex tex/interlinear-block/book.tex tex/interlinear-block/style.tex
	mkdir -p build/interlinear-block
	xelatex -interaction=nonstopmode -halt-on-error -output-directory=build/interlinear-block tex/interlinear-block/book.tex
	xelatex -interaction=nonstopmode -halt-on-error -output-directory=build/interlinear-block tex/interlinear-block/book.tex

build/interlinear-run/source.tex: $(INTERLINEAR_DATA) scripts/interlinear/json_to_run_tex.py
	python scripts/interlinear/json_to_run_tex.py $(INTERLINEAR_DATA) -o build/interlinear-run/source.tex

build/interlinear-run/book.pdf: build/interlinear-run/source.tex tex/interlinear-run/book.tex tex/interlinear-run/style.tex
	mkdir -p build/interlinear-run
	xelatex -interaction=nonstopmode -halt-on-error -output-directory=build/interlinear-run tex/interlinear-run/book.tex
	xelatex -interaction=nonstopmode -halt-on-error -output-directory=build/interlinear-run tex/interlinear-run/book.tex

build/interlinear-jp-main/source.tex: $(INTERLINEAR_DATA) scripts/interlinear/json_to_jp_main_tex.py
	python scripts/interlinear/json_to_jp_main_tex.py $(INTERLINEAR_DATA) -o build/interlinear-jp-main/source.tex --author "$(JP_MAIN_AUTHOR)" --curated-by "$(JP_MAIN_CURATOR)" --curated-url "$(JP_MAIN_URL)" --powered-by "$(JP_MAIN_POWERED_BY)" --cover-image "$(JP_MAIN_COVER)"

build/interlinear-jp-main/book.pdf: build/interlinear-jp-main/source.tex tex/interlinear-jp-main/book.tex tex/interlinear-jp-main/style.tex
	mkdir -p build/interlinear-jp-main
	xelatex -interaction=nonstopmode -halt-on-error -output-directory=build/interlinear-jp-main tex/interlinear-jp-main/book.tex
	xelatex -interaction=nonstopmode -halt-on-error -output-directory=build/interlinear-jp-main tex/interlinear-jp-main/book.tex

ocr-sample:
	python scripts/ocr/pdf_to_markdown.py "$(PDF)" --pages "$(PAGES)" --lang "$(OCR_LANG)" --psm "$(PSM)" --dpi "$(DPI)" --workers "$(WORKERS)" --output ocr/sample-pages.md

ocr-all:
	python scripts/ocr/pdf_to_markdown.py "$(PDF)" --pages all --lang "$(OCR_LANG)" --psm "$(PSM)" --dpi "$(DPI)" --workers "$(WORKERS)" --output ocr/book.md

clean:
	rm -rf build/paired build/interlinear-block build/interlinear-run build/interlinear-jp-main build/legacy build/preview
	rm -f build/*.aux build/*.log build/*.out build/*.toc build/*.xdv build/*.fls build/*.fdb_latexmk build/*.pdf build/*.tex
	rm -rf scripts/**/__pycache__
