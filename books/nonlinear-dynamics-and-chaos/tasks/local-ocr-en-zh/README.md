# Nonlinear Dynamics and Chaos Local OCR EN/ZH Tasks

Use this manifest for the local Mathpix-parity OCR path. It does not replace the existing exact-TeX/Mathpix artifacts.

Required order:

1. Run `scripts/interlinear/run_textbook_local_ocr.py --book-id nonlinear-dynamics-and-chaos --smoke` and inspect the output.
2. Run full local OCR only after smoke output preserves equations, tables, and figures.
3. Build structured nodes and EN/ZH JSON from reviewed page output.
4. Compile pocket-size English and EN/ZH PDFs; fix overfull lines and missing figures before finalizing.
