#!/usr/bin/env bash
# Assemble the medRxiv submission PDF from the manuscript.
#
#   1. render docs/manuscript/preprint.md to HTML (scripts/build_preprint_html.sh)
#   2. print that HTML to an A4 PDF with headless Chrome; figures are embedded
#   3. report the page count and write a page-1 PNG for the title-page check
#      (medRxiv wants title, authors, affiliation and abstract on the first page)
#
# Output goes to docs/manuscript/submission/, which is gitignored: the PDF is a
# derived artefact and is rebuilt from the markdown before every submission.
# Usage (from the repo root):  bash scripts/build_submission_pdf.sh
set -euo pipefail
cd "$(dirname "$0")/.."
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
[ -x "$CHROME" ] || { echo "[!] Google Chrome not found at $CHROME"; exit 1; }
command -v pdfinfo >/dev/null || { echo "[!] pdfinfo (poppler) not found"; exit 1; }

STAMP=$(date +%Y%m%d)
OUTDIR=docs/manuscript/submission
PDF="$PWD/$OUTDIR/VeriVar_preprint_medRxiv_${STAMP}.pdf"
mkdir -p "$OUTDIR"

bash scripts/build_preprint_html.sh en >/dev/null
"$CHROME" --headless=new --disable-gpu --no-sandbox --no-pdf-header-footer \
  --virtual-time-budget=20000 --print-to-pdf="$PDF" \
  "file://$PWD/docs/manuscript/preprint.html" 2>/dev/null

pages=$(pdfinfo "$PDF" | awk '/^Pages:/{print $2}')
size=$(pdfinfo "$PDF" | awk -F': *' '/^Page size:/{print $2}')
pdftoppm -png -r 80 -f 1 -l 1 -singlefile "$PDF" "$OUTDIR/page1_check"
echo "[*] $PDF"
echo "    pages: $pages   page size: $size"
echo "    title-page proof: $OUTDIR/page1_check.png"
