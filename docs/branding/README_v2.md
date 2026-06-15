# VeriVar icon — v2

Recreated from the updated reference
(`gemini/verivar_icon_Gemini_Generated_Updated_Image.png`). These `*_v2*` files
do **not** replace the original v1 set.

## Concept / metaphor

A bold **V monogram** (Veri + Var) whose **upper-right stroke flicks up into a
checkmark** = verification / faithful, evidence-grounded interpretation (cites
only real evidence, never fabricates). A **small node with short connector
ticks** sits in the valley of the V = a single genomic **variant** / "verified
data point". No DNA helix — meaning is carried by *trust (check) + variant (node)*.

- **V monogram** → the brand letterform, single bold even weight.
- **Teal checkmark** on the right arm → "verified".
- **Central node + ticks** → the somatic variant / data point under review.

## Palette (colourblind-safe)

| Role            | Hex       |
|-----------------|-----------|
| Deep navy (V)   | `#1B3A5B` |
| Teal (accent)   | `#2A9D8F` |
| Light teal (dark-theme accent) | `#7FD4C8` |
| Node core on dark | `#E8F6F3` |

## Files

Master (editable, source of truth):
- `verivar_icon_v2.svg` — light master (navy V, transparent background)
- `verivar_icon_v2_dark.svg` — dark theme (teal V for dark backgrounds)
- `verivar_icon_v2_mono.svg` — single-colour (`currentColor`, open-ring node)

App-icon sources (rounded-square / squircle container):
- `verivar_icon_v2_app_light.svg` — navy V on white tile
- `verivar_icon_v2_app_dark.svg` — teal V on navy tile

PNG renders of the light master:
- `verivar_icon_v2_16.png`, `_32.png`, `_64.png`, `_256.png`, `_512.png`

App-icon renders (512):
- `verivar_icon_v2_app_light_512.png`
- `verivar_icon_v2_app_dark_512.png`

## Usage notes

- The plain master has a **transparent background** — drops onto any surface.
- Use `verivar_icon_v2_dark.svg` on dark UI; `…_mono.svg` for one-ink contexts
  (set `color:` to recolour; defaults to navy).
- App-icon SVGs include the squircle tile; mark fills ~75% safe area, optically
  centred. Re-render at any size with cairosvg.
- Self-contained: no external fonts or images; all geometry is paths/primitives.

## Rendering

Renderer used: **cairosvg** (`/opt/anaconda3/bin/cairosvg`). Example:

```bash
cairosvg verivar_icon_v2.svg -o out.png --output-width 512 --output-height 512
```

## Legibility

Verified by viewing the rendered 16 / 32 / 64 / 256 px output. The V + teal
checkmark silhouette stays clear down to 16px (favicon); the node/ticks read as
a point at >=32px and dissolve gracefully into a small cluster at 16px without
muddying the silhouette.
