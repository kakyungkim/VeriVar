#!/usr/bin/env bash
# Build the A0 portrait poster for the Chuncheon x KNU x K-BioX summit (2026-11-14).
#
#   1. regenerate the SVG charts from the committed result JSONs
#   2. render poster.html to PDF with headless Chrome (vector, no raster figures)
#   3. rasterise the PDF to a 300-dpi JPG, which is the other format the
#      secretariat accepts, and to a 100-dpi PNG for on-screen proofreading
#
# The secretariat prints the poster, so the only deliverables are out/*.pdf and
# out/*.jpg. Usage (from this directory):  ./build.sh
set -euo pipefail
cd "$(dirname "$0")"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PY="../../../venv/bin/python"
OUT=out
NAME=VeriVar_KBioX2026_poster

[ -x "$CHROME" ] || { echo "[!] Google Chrome not found at $CHROME"; exit 1; }
command -v pdftoppm >/dev/null || { echo "[!] pdftoppm (poppler) not found"; exit 1; }
mkdir -p "$OUT"

echo "[1/3] charts"
"$PY" make_poster_figures.py

echo "[2/3] PDF"
"$CHROME" --headless=new --disable-gpu --no-sandbox --no-pdf-header-footer \
  --print-to-pdf-no-header --virtual-time-budget=20000 \
  --print-to-pdf="$OUT/$NAME.pdf" "file://$PWD/poster.html" 2>/dev/null
"$PY" - <<'PYEOF'
import re, subprocess, sys
info = subprocess.run(["pdfinfo", "out/VeriVar_KBioX2026_poster.pdf"],
                      capture_output=True, text=True).stdout
pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
size = re.search(r"Page size:\s+([\d.]+) x ([\d.]+) pts", info)
w_mm, h_mm = (float(size.group(1)) * 25.4 / 72, float(size.group(2)) * 25.4 / 72)
print(f"      {pages} page(s), {w_mm:.1f} x {h_mm:.1f} mm")
if pages != 1:
    sys.exit(f"[!] expected 1 page, got {pages}: content overflows the sheet")
if not (abs(w_mm - 841) < 2 and abs(h_mm - 1189) < 2):
    sys.exit(f"[!] expected A0 portrait 841 x 1189 mm, got {w_mm:.1f} x {h_mm:.1f}")
PYEOF

echo "[3/3] JPG (300 dpi) and proof PNG (100 dpi)"
pdftoppm -jpeg -r 300 -jpegopt quality=92 -singlefile "$OUT/$NAME.pdf" "$OUT/$NAME"
pdftoppm -png  -r 100 -singlefile "$OUT/$NAME.pdf" "$OUT/${NAME}_proof"
"$PY" -c "
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
for f in ('$OUT/$NAME.jpg', '$OUT/${NAME}_proof.png'):
    im = Image.open(f); print('     ', f, im.size)
"
echo "[*] done — submit $OUT/$NAME.pdf (or .jpg) to the secretariat's Google form"
