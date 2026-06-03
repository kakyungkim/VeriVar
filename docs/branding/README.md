# VeriVar — branding

**VeriVar** = *Verifiable Variant*: faithful, citation-grounded, auditable LLM interpretation
of somatic cancer variants.

## Concept

**One-sentence metaphor:** Two interlocking V-letterforms — verification and variant — meet at a
coded gem that marks every interpretation as precise, auditable, and machine-verified.

The mark is a **VA monogram** composed of two geometric letterforms:

- **Bold dark-navy V** (left, upper): a downward chevron encoding verification, precision, certainty.
  Along its upper-left arm, a dissolving grid of teal pixels alludes to sequencing data and genomic signal
  processing — the raw evidence that feeds the pipeline.
- **Teal caret / delta** (right, lower): an upward-pointing V (capital-A / delta shape) encoding
  variant, change, and the genomic delta — the very thing VeriVar classifies. Its gradient from bright
  teal to deep teal suggests forward motion and directionality.
- **Hexagonal gem** at the junction: a faceted crystal with a `</>` code symbol anchors the
  composition where the two forms converge. The gem encodes "verified through code" — the pipeline's
  rule-based + LLM dual-mode output crystallised into a single call.

At 16px (favicon), the mark reads as a strong dark V with a teal accent.
At 512px, the full VA monogram — pixel strip, gem facets, caret gradient — is legible.

This design avoids DNA helices, lab flasks, and generic check-mark clichés. The genomic browser /
data-engineering vocabulary is immediately readable to its audience (molecular pathologists,
computational oncologists) while communicating precision and structure to anyone.

## Files

| File | Use |
|---|---|
| `verivar_icon.svg` | Master colour icon (512×512 viewBox, transparent bg) — source of truth |
| `verivar_icon_mono.svg` | Monochrome mark (`currentColor`, transparent bg) — favicons, print, single-colour UI |
| `verivar_icon_512.png` | Colour render — app stores, marketing, OG image |
| `verivar_icon_256.png` | Colour render — web, documentation header |
| `verivar_icon_64.png` | Colour render — toolbar, small tile |
| `verivar_icon_32.png` | Colour render — browser tab icon (retina) |
| `verivar_icon_16.png` | Colour render — favicon 1x |
| `verivar_icon_mono_256.png` | Mono on white — visual review, print |
| `verivar_icon_mono_dark_256.png` | Mono on navy — dark-bg visual review |

## Palette (colourblind-safe; no red/green-only distinction)

| Role | Hex | Usage |
|---|---|---|
| Navy | `#1B2E5E` | Primary dark V form, strong anchor |
| Teal | `#2EB8A6` | Variant caret form (mid gradient), gem body |
| Teal bright | `#3DD6C0` | Caret top gradient, pixel strip accent |
| Teal deep | `#1E9485` | Caret bottom gradient |
| Pixel/grey | `#C8D6E0` | Pixel strip alternate squares |
| Arm highlight | `#5ED8CA` | Facet highlight strips on caret arms |
| White | `#FFFFFF` | Gem highlight, top facet, apex tip accent |
| Cool grey | `#8FAEBB` | Gem bottom gradient |

No red/green pair used anywhere. Navy and teal are distinguishable by both hue and luminance.
Readable under deuteranopia, protanopia, and tritanopia.

## Usage notes

- The colour icon has a **transparent background** — it works on both light and dark surfaces.
  On very light white backgrounds the navy V provides strong contrast; on dark backgrounds the
  teal caret reads against the dark field.
- The mono mark inherits `currentColor`; set `color: #1B2E5E` on a light background or
  `color: #ffffff` on a dark background via CSS or the SVG `color` attribute.
- The `</>` symbol in the gem is rendered via a system monospace font (`Courier New`) in the
  colour SVG and as geometric path strokes in the mono SVG — no external font dependency in mono.
- Do not crop to a circle (the diagonal composition needs rectangular/square uncropped space).
- Maintain at least 8% padding around the mark when placing on a non-square surface.
- Do not recolour the teal form to red, green, or magenta without re-checking colourblind
  accessibility (use the Okabe-Ito set or WCAG-verified alternatives).

## Regenerate PNGs

```bash
source venv/bin/activate
pip install cairosvg   # one-time

python3 - <<'EOF'
import cairosvg
bd = "docs/branding"
# Colour renders
for w in [512, 256, 64, 32, 16]:
    cairosvg.svg2png(
        url=f"file://$(pwd)/{bd}/verivar_icon.svg",
        write_to=f"{bd}/verivar_icon_{w}.png",
        output_width=w, output_height=w
    )

# Mono renders (inject explicit color for preview)
import re
with open(f"{bd}/verivar_icon_mono.svg") as f:
    mono_src = f.read()

for bg, color, suffix in [
    ("white",   "#1B2E5E", "256"),
    ("#1B2E5E", "white",   "dark_256"),
]:
    svg = mono_src.replace(
        '<svg xmlns="http://www.w3.org/2000/svg"',
        f'<svg xmlns="http://www.w3.org/2000/svg" color="{color}"'
    )
    cairosvg.svg2png(
        bytestring=svg.encode(),
        write_to=f"{bd}/verivar_icon_mono_{suffix}.png",
        output_width=256, output_height=256,
        background_color=bg
    )
print("done")
EOF
```
