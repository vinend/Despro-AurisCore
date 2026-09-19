# Initial workspace inspection

Before implementation, the workspace contained 30 files: 10 PDFs, 9 DOCX files, 2 LaTeX sources, 2 AUX files, 2 logs, 1 OUT, 2 XML fragments, 1 Markdown README and 1 Python script. There was no local `.git` directory, and Git was not available on PATH. No commit or push was performed.

- `tools/generate_ai_architecture_docs.py`: existing document/diagram generator using Pillow and python-docx. It is not an acquisition, signal-processing or model-training implementation.
- `docs/ai_architecture/README.md` and related PDF/DOCX/LaTeX: earlier multi-mode architecture proposals, including smartphone inference, Wi-Fi and a future TinyML alternative.
- `terbaru/`: proposal sources, reports, individual contributions and course rubrics; extracted XML fragments were already present.
- Root documents: project presentation and weekly-report templates/reports.
- The weekly group report describes September 2026 hardware schematics and planned dataset/app work, but includes no executable PCG pipeline. Its mention of a GitHub repository does not establish a Git checkout in this local workspace.
- No root README, audio datasets, manifests, notebooks, ML configurations, runtime dependency definition, tests or firmware were found.
- `python` resolved to a Windows Store alias, not a usable interpreter. A local ignored Python 3.12.10 runtime was installed under `.runtime/` for this execution.

All pre-existing files are preserved. The new implementation reuses the existing project naming and smartphone/PC SVM concept. Historical design documents remain historical; the root README records the current ESP32-S3 acquisition/BLE/smartphone architecture and heart-only scope.

Implementation sequence: research original datasets; acquire and verify CirCor; parse metadata and link repeated participants; audit quality; split independent participants; preprocess and extract features; fit a fixed training-only-scaled SVM; evaluate validation and held-out test data; test and document the executable workflow.
