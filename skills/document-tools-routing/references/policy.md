# Document Tools Routing Policy

## 解释器

- `[MUST]` 文档、OCR、Office、Excel、YAML、`SKILL.md`、`openai.yaml` 或技能辅助脚本任务使用专用环境，不用系统 `python` / `python3` / `py`。
- macOS / Unix:
  - 核心：`/Users/jeremy/.python-tools/.runtime/.venv/bin/python`
  - 增强：`/Users/jeremy/.python-tools/.runtime/.venv-advanced/bin/python`
  - 重型 AI：`/Users/jeremy/.python-tools/.runtime/.venv-heavy-ai/bin/python`
  - Tika：`/Users/jeremy/.python-tools/.runtime/tika/tika-app.jar`
- Windows:
  - 核心：`C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe`
  - 增强：`C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv-advanced\Scripts\python.exe`
  - 重型 AI：`C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv-heavy-ai\Scripts\python.exe`
- `[DEFAULT]` 调用工具优先用所选解释器的 `-m <module>` 或 `-c ...`。

## 路由

- `[DEFAULT]` 普通 PDF 文本：核心 + `PyMuPDF`。
- `[DEFAULT]` 扫描 PDF OCR：核心 + `ocrmypdf` / `Tesseract`，再用 `PyMuPDF` 抽文本。
- `[DEFAULT]` Word：核心 + `python-docx`；需要 HTML/Markdown 时可用 `mammoth` 或 `pandoc`。
- `[DEFAULT]` PowerPoint：核心 + `python-pptx`。
- `[DEFAULT]` Excel 轻量读取、少量 sheet、指定列、表头、公式结果：核心 + `openpyxl`。
- `[MUST]` Excel dataframe 级处理使用增强 + `pandas`，包括 `merge`、`groupby`、`pivot_table`、缺失值清洗、多 sheet 联表、批量聚合统计。
- `[MUST]` 用户或脚本明确要求 `pandas` 时，先检查增强环境，不直接降级。
- `[DEFAULT]` PDF 表格、长尾格式、结构化分块：增强；优先 `pdfplumber`、`unstructured`，必要时 `Camelot`、`tabula-py`。
- `[DEFAULT]` 高级 OCR、复杂版面、高质量 Markdown/JSON：重型 AI；按需 `PaddleOCR`、`Docling`、`Marker`。
- `[DEFAULT]` 旧版 Office 或兼容性差文件：先用 LibreOffice 无界面转换，再进入对应 Python 解析。

## 升级与 fallback

- `[DEFAULT]` 轻量优先；基础链路足够时不升级到增强或重型 AI。
- `[DEFAULT]` 仅当格式覆盖、表格解析、版面理解或输出质量不足时升级。
- `[DEFAULT]` LibreOffice 路径优先：`/Applications/LibreOffice.app/Contents/MacOS/soffice`、`C:\Program Files\LibreOffice\program\soffice.exe`、`soffice`。
- `[MUST]` 工具不可用时明确报告；只有确认 fallback 环境可用后才切换。
