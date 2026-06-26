#!/usr/bin/env bash
# Build the full knowledge base from the source PDF + XLSX, then the vector index.
# Override PDF_PATH / XLSX_PATH env vars to point at your local copies.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Parsing PDF rules document"
python3 src/ingest_pdf.py

echo "==> Parsing XLSX Q&A document"
python3 src/ingest_xlsx.py

echo "==> Building vector index"
python3 src/kb.py

echo "Done. Records + images in data/kb, index in data/index."
