#!/usr/bin/env bash
# Render docs/manuscript/preprint{,_ko}.md to standalone, responsive HTML with pandoc.
#
# The page style is docs/manuscript/style_paper.html (a <style> block: Pretendard/Noto Sans KR
# body font, max-width column, responsive images and tables). Figures are referenced
# relatively (figures/*.png), so the HTML must stay next to the markdown.
#
# Usage (from the repo root):  bash scripts/build_preprint_html.sh [en|ko|all]
set -euo pipefail
cd "$(dirname "$0")/../docs/manuscript"
command -v pandoc >/dev/null || { echo "[!] pandoc not found"; exit 1; }
which=${1:-all}
tmp_open=$(mktemp); tmp_close=$(mktemp); trap 'rm -f "$tmp_open" "$tmp_close"' EXIT
build() {
  local src=$1 out=$2 lang=$3
  # document-css=false drops pandoc's default stylesheet (fixed 36em column + 50px
  # padding, which overflows a phone screen); style_paper.html expects a .wrap container.
  printf '<div class="wrap">\n' > "$tmp_open"; printf '</div>\n' > "$tmp_close"
  # implicit_figures off: each figure already has a numbered caption paragraph, so the
  # alt-text figcaption pandoc would add is a duplicate.
  pandoc "$src" -s -f markdown-implicit_figures -t html5 \
    --metadata lang="$lang" \
    --metadata document-css=false \
    --include-in-header=style_paper.html \
    --include-before-body="$tmp_open" --include-after-body="$tmp_close" \
    --resource-path=. \
    -o "$out"
  echo "[*] $out ($(wc -c <"$out") bytes)"
}
[ "$which" = en ] || [ "$which" = all ] && build preprint.md preprint.html en
[ "$which" = ko ] || [ "$which" = all ] && build preprint_ko.md preprint_ko.html ko
true
