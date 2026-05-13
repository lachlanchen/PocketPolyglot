PDF ?= sources/中国民间故事集成 四川卷 上 10978512.pdf
PAGES ?= 60-62
DPI ?= 300
OCR_LANG ?= chi_sim
PSM ?= 4
WORKERS ?= 4
INTERLINEAR_DATA ?= data/interlinear/sample.json
PAIRED_DATA ?= data/paired/source.md

.PHONY: sample paired interlinear interlinear-run compare kokoro-md kokoro-tmux ocr-sample ocr-all clean

sample: paired

paired: build/paired/book.pdf

interlinear: build/interlinear-block/book.pdf

interlinear-run: build/interlinear-run/book.pdf

compare: interlinear interlinear-run

kokoro-md:
	python scripts/books/epub_to_markdown.py sources/心.epub --raw-output books/kokoro/markdown/book.raw.md --clean-output books/kokoro/markdown/book.md --start-heading 总序

kokoro-tmux:
	prompt_tools/interlinear-book/start-book-tmux.sh --no-attach -- --epub sources/心.epub --book-id kokoro --title-zh 心 --title-zh-reading xīn --title-ja 心 --title-ja-reading こころ --model gpt-5.5 --reasoning high

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

ocr-sample:
	python scripts/ocr/pdf_to_markdown.py "$(PDF)" --pages "$(PAGES)" --lang "$(OCR_LANG)" --psm "$(PSM)" --dpi "$(DPI)" --workers "$(WORKERS)" --output ocr/sample-pages.md

ocr-all:
	python scripts/ocr/pdf_to_markdown.py "$(PDF)" --pages all --lang "$(OCR_LANG)" --psm "$(PSM)" --dpi "$(DPI)" --workers "$(WORKERS)" --output ocr/book.md

clean:
	rm -rf build/paired build/interlinear-block build/interlinear-run build/legacy build/preview
	rm -f build/*.aux build/*.log build/*.out build/*.toc build/*.xdv build/*.fls build/*.fdb_latexmk build/*.pdf build/*.tex
	rm -rf scripts/**/__pycache__
