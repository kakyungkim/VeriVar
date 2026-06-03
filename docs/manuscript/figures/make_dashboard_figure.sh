#!/usr/bin/env bash
# Build Figure 8 — a screenshot of the decision-support dashboard view.
#
# Renders _dashboard_demo.html (populated from real committed data:
# data/outputs/cohort_interpretation.json — BRAF V600E grounded + APC R1450*
# abstention) with headless Chrome at 2x, then trims whitespace.
#
# Usage:  ./make_dashboard_figure.sh
set -euo pipefail
cd "$(dirname "$0")"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PY="../../../venv/bin/python"

[ -x "$CHROME" ] || { echo "[!] Google Chrome not found at $CHROME"; exit 1; }

"$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-sandbox \
  --force-device-scale-factor=2 --window-size=1220,1640 \
  --default-background-color=FFFFFFFF \
  --screenshot="F6_dashboard.png" "file://$PWD/_dashboard_demo.html"

# trim surrounding whitespace
"$PY" - <<'PYEOF'
from PIL import Image, ImageChops
im = Image.open("F6_dashboard.png").convert("RGB")
diff = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255)))
bbox = diff.getbbox()
if bbox:
    l, t, r, b = bbox; m = 24
    im.crop((max(0, l - m), max(0, t - m),
             min(im.size[0], r + m), min(im.size[1], b + m))).save("F6_dashboard.png")
print("F6_dashboard.png", Image.open("F6_dashboard.png").size)
PYEOF
echo "[*] Figure 7 written: F6_dashboard.png"
