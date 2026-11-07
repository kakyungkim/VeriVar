# VeriVar poster — Chuncheon x KNU x K-BioX Global Bio Innovation Summit 2026

A0 portrait (841 x 1189 mm), presented 2026-11-14 at the KNU Science & Industry Innovation Hub,
Chuncheon. The secretariat prints the poster, so the deliverable is a file, not a print.

## Build

```bash
./build.sh            # charts -> PDF (headless Chrome) -> 300-dpi JPG + 100-dpi proof PNG
```

Outputs land in `out/`. The build fails loudly if the PDF is not exactly one A0 portrait page,
which is how content overflow is caught.

## Files

| Path | What it is |
|---|---|
| `poster.html`, `poster.css` | the poster itself; `--page-w` / `--page-h` in the CSS retarget the sheet |
| `make_poster_figures.py` | the five charts, generated from the committed result JSONs |
| `figures/` | generated SVGs and the repository QR code |
| `assets/` | event logos (downloaded from the event site, not committed) and the VeriVar mark |
| `NUMBERS.md` | every printed number with the file and field it comes from |
| `application_form.md` | what to paste into the event's poster-application form |
| `out/` | the built PDF, JPG and proof PNG (not committed) |

## Checks

```bash
python -m pytest tests/test_poster_numbers.py     # printed numbers match the JSONs; no retired values
```

The event logos in `assets/` were downloaded from the event site for this one printed poster and are
not redistributed with the repository; `.gitignore` keeps `assets/` and `out/` untracked.
