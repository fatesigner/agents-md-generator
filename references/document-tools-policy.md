# Python 与文档处理工具专项规则

本文件是模板维护参考；普通任务优先使用 `$document-tools-routing` skill，不同时加载本文件和 skill 细则。

## 解释器与路由

- `[MUST]` 文档、OCR、Office、Excel、YAML、`SKILL.md`、`openai.yaml` 或技能辅助脚本任务使用专用环境，不用系统 `python` / `python3` / `py`。
- macOS / Unix：核心 `/Users/jeremy/.python-tools/.runtime/.venv/bin/python`；增强 `/Users/jeremy/.python-tools/.runtime/.venv-advanced/bin/python`；重型 AI `/Users/jeremy/.python-tools/.runtime/.venv-heavy-ai/bin/python`；Tika `/Users/jeremy/.python-tools/.runtime/tika/tika-app.jar`。
- Windows：核心 `C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe`；增强 `C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv-advanced\Scripts\python.exe`；重型 AI `C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv-heavy-ai\Scripts\python.exe`。
- PDF 文本：核心 + `PyMuPDF`；扫描 PDF OCR：核心 + `ocrmypdf` / `Tesseract`；Word：核心 + `python-docx` / `mammoth`；PowerPoint：核心 + `python-pptx`。
- Excel 轻量读取：核心 + `openpyxl`；Excel dataframe 级 `merge` / `groupby` / `pivot_table` / 清洗 / 多 sheet 联表：增强 + `pandas`。
- PDF 表格、长尾格式、结构化分块：增强 + `pdfplumber` / `unstructured`，必要时 `Camelot` / `tabula-py`。
- 高级 OCR、复杂版面、高质量 Markdown/JSON：重型 AI + `PaddleOCR` / `Docling` / `Marker`。
- 旧版 Office 或兼容性差文件：先用 LibreOffice 无界面转换；路径优先 `/Applications/LibreOffice.app/Contents/MacOS/soffice`、`C:\Program Files\LibreOffice\program\soffice.exe`、`soffice`。
- `[MUST]` 工具不可用时明确报告；只有确认 fallback 环境可用后才切换。
