#!/usr/bin/env bash
# Build Supplementary Figure S1 (figS1_dashboard.png): the decision-support dashboard view.
#
# Step 1 regenerates _dashboard_demo.html from real outputs via make_dashboard_demo.py
# (cohort_interpretation.json for the two modes, the SOP-strict VICC engine for the rule
# arm, _dashboard_demo_chat.json for the verbatim grounded-chat answers). Step 2 renders
# it with headless Chrome at 2x and trims whitespace. The window is tall enough for the
# whole page; the trim step fails loudly if content touches the bottom edge (clipping).
#
# Usage:  ./make_dashboard_figure.sh
set -euo pipefail
cd "$(dirname "$0")"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PY="../../../venv/bin/python"

[ -x "$CHROME" ] || { echo "[!] Google Chrome not found at $CHROME"; exit 1; }

"$PY" make_dashboard_demo.py

"$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-sandbox \
  --force-device-scale-factor=2 --window-size=1220,2400 \
  --default-background-color=FFFFFFFF \
  --screenshot="figS1_dashboard.png" "file://$PWD/_dashboard_demo.html"

# trim surrounding whitespace
"$PY" - <<'PYEOF'
from PIL import Image, ImageChops
im = Image.open("figS1_dashboard.png").convert("RGB")
diff = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255)))
bbox = diff.getbbox()
if bbox and bbox[3] >= im.size[1] - 2:
    raise SystemExit("[!] content reaches the bottom edge: enlarge --window-size height")
if bbox:
    l, t, r, b = bbox; m = 24
    im.crop((max(0, l - m), max(0, t - m),
             min(im.size[0], r + m), min(im.size[1], b + m))).save("figS1_dashboard.png")
print("figS1_dashboard.png", Image.open("figS1_dashboard.png").size)
PYEOF
echo "[*] Supplementary Figure S1 written: figS1_dashboard.png"
