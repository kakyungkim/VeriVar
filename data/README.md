# data/

Everything the manuscript's numbers are computed from is committed here, so the evaluation re-runs
offline without network access or an API key. Run `python -m scripts.verify_manuscript` to recompute
the headline values from these files and check them against the manuscript text.

## Layout

| Folder | What it holds |
|---|---|
| `cohorts/` | the TCGA cohort snapshot (cBioPortal, open-access tier) and the selected variant set |
| `knowledge/` | evidence snapshots: CIViC release, DGIdb, per-variant AlphaMissense scores, MaveDB functional sets, UniProt domains, cancerhotspots, ClinicalTrials.gov records, gene aliases |
| `outputs/` | per-variant model outputs from every reported run (cached, because hosted-model calls are not deterministic) and the evaluation reports derived from them |
| `benchmark/` | the external gold standard (Horak et al. 2022, 70 variants), the ClinVar oncogenicity holdout, the comparator outputs (OncoVI, HemaGuide, CancerVar) and every rule-arm configuration |
| `golden/` | the pinned golden-set regression snapshot used by the change-control check |
| `examples/` | small VCFs for trying the dashboard |

## Licences and attribution

Third-party data are redistributed under their own terms.

| Source | Licence | Where |
|---|---|---|
| CIViC | CC0 1.0 | `knowledge/civic/`, `benchmark/horak_civic.tsv`, `benchmark/civic_assertions.tsv` |
| MaveDB score sets | CC0 1.0 | `knowledge/functional/` |
| AlphaMissense predictions (per-variant scores only) | CC BY 4.0 (Zenodo 10813168) | `knowledge/alphamissense/` |
| UniProt | CC BY 4.0 | `knowledge/domains/` |
| cancerhotspots.org | ODbL 1.0 | `knowledge/hotspots/` |
| HemaGuide Supplementary Table 6 (Zoller et al., *Nat Med* 2026) | CC BY 4.0 | `benchmark/hemaguide/` (see its README) |
| OncoVI predictions (Carta et al., *J Mol Diagn* 2026) | MIT | `benchmark/oncovi/` (notice in its LICENSE) |
| CancerVar web-server tiers (Li et al., *Sci Adv* 2022) | free for non-commercial use | `benchmark/cancervar/` (see its README) |
| ClinVar, ClinicalTrials.gov, gnomAD, TCGA open-access tier | public | various |

**Horak et al. 2022 gold standard.** The reference classifications for the 70 variants (decision,
points and criterion codes) appear in derived tables such as `benchmark/horak_benchmark.tsv`, with
attribution to Horak P et al., *Genet Med* 2022;24(5):986-998 (doi:10.1016/j.gim.2022.01.001), and to
their CC BY 4.0 republication in HemaGuide Supplementary Table 6. The original supplementary
workbooks are distributed under the publisher's terms and are **not** included; download them from
PMC9081216 into `benchmark/horak/` before running `scripts/build_horak_benchmark.py`.

## Not included, rebuilt by script

| Artefact | Rebuild with |
|---|---|
| Chroma dense index | `python -m scripts.build_index` |
| full AlphaMissense prediction table | `python -m scripts.fetch_alphamissense` |
| Horak et al. supplementary workbooks | manual download from PMC9081216 |
| COSMIC Cancer Gene Census extracts | not redistributable; not read by any code here |

No patient data, proprietary data or credentials are stored in this folder. The research-use-only
notice in the top-level README applies to everything here.
