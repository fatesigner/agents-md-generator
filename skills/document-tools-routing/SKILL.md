---
name: document-tools-routing
description: Route PDF, OCR, Office, Excel, PowerPoint, YAML, SKILL.md, and openai.yaml work to the right local document toolchain.
---

# Document Tools Routing

Use the lightest reliable local document toolchain. Do not use system `python`, `python3`, `py`, or global Python for document or skill-template processing.

Routing-only questions should use this file only. Read `references/policy.md` only for execution fallback, Windows paths, LibreOffice paths, or environment repair.

## Environments

- Core: `/Users/jeremy/.python-tools/.runtime/.venv/bin/python`
- Advanced: `/Users/jeremy/.python-tools/.runtime/.venv-advanced/bin/python`
- Heavy AI: `/Users/jeremy/.python-tools/.runtime/.venv-heavy-ai/bin/python`
- Tika jar: `/Users/jeremy/.python-tools/.runtime/tika/tika-app.jar`

Prefer `.../bin/python -m <module>` when wrapper paths may drift.

## Routes

- PDF text/page count: core + PyMuPDF.
- Scanned PDF OCR: core + OCRmyPDF/Tesseract, then PyMuPDF.
- PDF tables, long-tail formats, structured chunking: advanced + pdfplumber/unstructured.
- Excel light reads: core + openpyxl.
- Excel dataframe work (`merge`, `groupby`, `pivot_table`, missing values, multi-sheet joins, batch aggregation): advanced + pandas/openpyxl.
- Word docx to Markdown/text: core + python-docx, mammoth, or pandoc.
- PowerPoint text: core + python-pptx.
- Advanced OCR, complex layout, high-quality Markdown/JSON: heavy AI + PaddleOCR/Docling/Marker.
- `SKILL.md` / `openai.yaml` validation: core + YAML/frontmatter/schema checks unless a local helper declares another environment.

For routing answers, state that no files, dependencies, or tool availability were verified unless you actually checked them.
