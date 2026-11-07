# HemaGuide Supplementary Table 6 (extracted)

`hemaguide_st6.csv` has the 70 rows of **Supplementary Table 6**: the molecular-mode benchmark
variant set, with the Horak 2022 reference call and HemaGuide's own call for each variant.

- **Source article:** Zoller et al. HemaGuide. *Nat Med* 2026;32(9):3224-3234.
  doi:[10.1038/s41591-026-04494-4](https://doi.org/10.1038/s41591-026-04494-4), PMC13577921.
- **Source file:** `41591_2026_4494_MOESM4_ESM.xlsx`, sheet `Supplementary Table 6`
  (https://static-content.springer.com/esm/art%3A10.1038%2Fs41591-026-04494-4/MediaObjects/41591_2026_4494_MOESM4_ESM.xlsx).
  sha256 `9bf1a0bf59fabc1181907ee290cefc9533c6cd13d905149a7300490a6b056afa`; md5
  `0083985b2fcffc217cb202623f87e75b`, which matches the checksum PMC lists for this file.
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0,
  https://creativecommons.org/licenses/by/4.0/), per the article's PMC license statement.
  Credit goes to the original authors.
- **Accessed:** 2026-09-24.
- **Changes made:** we kept only Supplementary Table 6 (the workbook has 12 tables) and dropped
  empty trailing columns. Integral numbers are written without a trailing `.0`, so `10.0`
  becomes `10`. Cell values are otherwise copied verbatim; no labels were recoded.

Columns: `ID, Gene, CDS_position, AA_change, Horak_2022_decision, Horak_2022_points,
Horak_2022_codes, Hemaguide_decision, HemaGuide_points, HemaGuide_codes`. Decisions use three
bins: `LO/O`, `VUS`, `LB/B`.

To regenerate: `python -m scripts.fetch_hemaguide` downloads the workbook into `raw/`, which
is gitignored, and rewrites the CSV. Use `--xlsx PATH` to extract from a local copy instead.
Scoring runs offline via `python -m scripts.run_hemaguide_headtohead`, which writes
`data/benchmark/hemaguide_headtohead.json`.
