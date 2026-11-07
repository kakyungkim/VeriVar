# VICC point-based rule arm — a citable, SOP-strict oncogenicity engine

`src/classify/vicc_rules.py` implements the ClinGen/CGC/VICC oncogenicity standard (Horak et al.,
Genet Med 2022;24(5):986–998) as a deterministic point-based engine over **independent, open data**.
Every fired criterion is emitted as a **citable record** (VICC code, points, statement, source), so
each call can be audited line by line. The primary configuration is **SOP-strict**
(`CONFIGS["sop_strict"]`, `PRIMARY_CONFIG`): the SOP criteria, point ranges and exclusion rules are
applied as written wherever open data allow, and criteria that open data cannot evaluate are left
unassigned rather than approximated.

It is a deterministic engine, **not** the LLM, and it is **not** claimed as a novel or
accuracy-competitive classifier: OncoVI already maps each VICC criterion to an evidence source, and
on the shared expert set both OncoVI and HemaGuide's molecular mode are higher in point estimate.
What the rule arm contributes is auditability and an abstention-first error profile.

> Research and education only; not for clinical use.

## Summary (Horak-70, SOP-strict)

| Metric | Value | Source |
|---|---|---|
| Three-class accuracy | **0.657** (95% bootstrap CI 0.543–0.771) | `data/benchmark/horak_vicc.json` |
| Five-class accuracy | 0.500 | same |
| Oncogenic sensitivity | 0.424 (14/33; Wilson 0.272–0.592) | same |
| Specificity (oncogenic vs rest) | **1.000** (37/37; Wilson 0.906–1.000) | same |
| AUROC over raw points | 0.885 | same |
| Predicted oncogenic / VUS / benign | 14 / 43 / 13 (gold 33 / 30 / 7) | same |
| Oncogenic over-calls | **0** | `data/benchmark/vicc_config_comparison.json` |
| Benign-direction errors | 6 | same |

Operating threshold: points ≥ 6 (Likely Oncogenic or Oncogenic) for the binary oncogenic call.

## Criteria, points and data sources (SOP-strict)

Point ranges (Horak 2022 Figure 1): Oncogenic ≥ 10, Likely Oncogenic 6 to 9, VUS 0 to 5,
Likely Benign −1 to −6, Benign ≤ −7.

| Code | Pts | SOP-strict implementation | Source |
|---|---|---|---|
| OVS1 | +8 | Null variant (nonsense, frameshift, canonical splice, initiation codon) in a tumour-suppressor gene; stop-loss is not null. 3′-end NMD and in-frame splice caveats are not evaluated (no transcript model) | fixed CGC-based TSG list |
| OS1 | +4 | **Unassigned in the primary result**: no non-circular open list of variants "established as oncogenic using this standard". Used only in dial rows 3–4 | (ClinVar FTP snapshot, dial only) |
| OS2 / OS2_Moderate | +4 / +2 | Functional evidence only: MaveDB DMS loss of function (TP53, PTEN) or CIViC *functional* evidence supporting an oncogenic effect (≥ 2 citations / 1 citation). Clinical, predictive and prognostic evidence grants nothing. Not used when OS1 applies | MaveDB, CIViC |
| OS3 | +4 | cancerhotspots.org hotspot with ≥ 50 samples at the residue **and** ≥ 10 with the same amino-acid change. Not used when OS1 applies | cancerhotspots v2 |
| OM1 | +2 | UniProt residue-level active or binding site. Not used when OS1 or OS3 applies. Domain annotations cover the 9 Horak genes only | UniProt |
| OM2 | +2 | In-frame length change in an oncogene or TSG, or stop-loss in a TSG; not with OVS1. No firing on the missense evaluation sets | fixed gene lists |
| OM3 | +2 | Hotspot with < 50 samples at the residue and ≥ 10 with the same change. Not used when OM1 or OM4 applies | cancerhotspots v2 |
| OM4 | +2 | Implemented to the SOP definition (Grantham condition, exclusions), but **unassigned**: no reference list of established oncogenic variants | — |
| OP1 | +1 | Computational evidence supports an oncogenic effect: AlphaMissense ≥ 0.564. Single predictor, so "all utilized lines" is met trivially | AlphaMissense via Ensembl VEP |
| OP2 | +1 | **Unassigned**: needs tumour type; the evaluations are tumour-agnostic | — |
| OP3 | +1 | Hotspot residue with < 10 samples carrying the same change | cancerhotspots v2 |
| OP4 | +1 | Absent from gnomAD or AF < 1e-4, **only when gnomAD data are observed**; not gated on other evidence | gnomAD via Ensembl VEP |
| SBVS1 / SBS1 | −8 / −4 | Population AF ≥ 5% / ≥ 1%, on the global max(gnomAD exomes, genomes) rather than the per-continent maximum | gnomAD via Ensembl VEP |
| SBS2 / SBS2_Moderate | −4 / −2 | DMS neutral, or CIViC functional evidence showing no oncogenic effect (1 citation: moderate) | MaveDB, CIViC |
| SBP1 | −1 | AlphaMissense ≤ 0.34 (single predictor) | AlphaMissense |
| SBP2 | −1 | **Unassigned**: no splice-prediction or conservation data; no synonymous variants in the sets | — |

No rule outside the SOP is applied in the primary configuration: the engine does not return a
variant with a single benign line to VUS, and OP4 is not approximated when population data are
missing. CIViC evidence is credited only for the exact substitution, never a different change at
the same residue.

## Error profile on Horak-70

Three-class confusion (gold → call): ONC→ONC 14, ONC→VUS 18, ONC→BEN 1, VUS→VUS 25, VUS→BEN 5,
BEN→BEN 7. Every oncogenic call was correct, so the engine made **no oncogenic over-call**; it left
18 of the 33 oncogenic variants at VUS and made six benign-direction errors (BRAF A31G, IDH1 F32V,
KRAS R164Q, PIK3CA K733R, TP53 G334R, and the oncogenic TP53 A347D). Five of those six rest on a
single AlphaMissense-based SBP1 line of −1 point, which the SOP ranges map to Likely Benign; this
follows from the single-predictor approximation rather than from a tuned threshold.

Per-gene three-class accuracy is lowest for FLT3 (0.33), BRAF (0.57) and EZH2 (0.58)
(`vicc_config_comparison.json`, `per_gene_accuracy_3class_S1`). The oncogenic variants left at VUS
concentrate where open data hold no variant-specific functional evidence: the MaveDB snapshot used
by the SOP-strict engine has DMS evidence for TP53 and PTEN only among the Horak genes, and several
residues are not cancerhotspots hotspots. On the
curated-evidence stratum (20 variants with CIViC evidence) accuracy is 0.50 and sensitivity 0.40;
on the other 50 variants, 0.72 and 0.444 (`known_novel`).

## Head-to-heads on identical Horak variants

All tests are exact two-sided McNemar tests paired on three-class correctness against the same gold.

| Comparator | Shared | Ours | Comparator | McNemar p (ours only / comparator only correct) | Source |
|---|---|---|---|---|---|
| OncoVI (Carta et al., J Mol Diagn 2026) | 69 | 0.652 [0.536–0.754] | 0.797 | 0.087 (9 / 19) | `data/benchmark/oncovi_headtohead.json` |
| HemaGuide molecular mode | 70 | 0.657 [0.543–0.771] | 0.800 | 0.087 (9 / 19) | `data/benchmark/hemaguide_headtohead.json` |

Neither difference is significant, and both comparators are higher in point estimate. The engines
fail in opposite directions. Among the 28 disagreements with OncoVI, our 19 errors are 16 oncogenic
variants left at VUS and 3 benign-direction calls; OncoVI's 9 errors include 7 oncogenic over-calls
on gold-VUS variants. HemaGuide made 6 oncogenic over-calls, 4 oncogenic misses and 4 benign
variants called VUS; our engine made no over-call and 19 oncogenic misses. Whether an
abstention-first profile is preferable depends on over-treatment being costlier than
under-detection in a draft-and-review workflow; each abstained oncogenic variant is a patient who
may miss an available targeted therapy. Horak-70 is OncoVI's home set, so these are head-to-heads
on identical variants, not an independent benchmark.

**CancerVar (cross-axis; error-profile contrast only).** CancerVar emits AMP/ASCO/CAP
*actionability* tiers, not VICC oncogenicity. Mapping Tier I/II → Oncogenic, III → VUS,
IV → Benign only to score it, CancerVar made 21 over-calls and no miss on 70 shared variants
(sensitivity 1.0, specificity 0.432), against our 0 over-calls and 19 misses. The mapped three-class
accuracies (0.657 vs 0.614, p = 0.771) are reported for completeness only
(`data/benchmark/cancervar_headtohead.json`).

## Sensitivity dial

Two levers outside the SOP raise sensitivity: residue-total hotspot tiering (credits recurrence
without the SOP's ≥ 10 same-change requirement) and OS1 from ClinVar oncogenicity labels (partly
circular on Horak-70). `scripts/run_horak_sensitivity_modes.py`, `dial_table2` in
`vicc_config_comparison.json`:

| Operating point | Accuracy (3-class) | Sensitivity | Specificity |
|---|---|---|---|
| 1. SOP-strict (default) | **0.657** | 0.424 | **1.000** |
| 2. + residue-total hotspot tiering (non-SOP) | 0.657 | 0.455 | 0.973 |
| 3. + OS1 from ClinVar (partly circular) | 0.700 | 0.545 | 0.973 |
| 4. + both | 0.686 | 0.545 | 0.946 |
| *OncoVI (reference, 69 shared)* | *0.797* | *0.909* | *0.806* |
| *HemaGuide molecular mode (reference, 70)* | *0.800* | *0.879* | *0.838* |

Every setting stays below both published engines in accuracy and sensitivity. The full dial is
reported rather than the most favourable point, and the SOP-strict default stays the headline. OS1
is built from the ClinVar FTP snapshot with an exact gene and protein-change match
(`scripts/fetch_horak_clinvar.py`).

## Independent check: ClinVar somatic-oncogenicity holdout

`scripts/run_clinvar_onc_holdout.py` → `data/benchmark/clinvar_onc_holdout.json`. Gold labels come
from the aggregate Oncogenicity field of the ClinVar FTP release; variants overlapping Horak-70 are
removed, leaving 714 unique gene–amino-acid keys, of which 712 enter the oncogenic-versus-uncertain
task (the 2 benign keys are excluded). ClinVar labels are used as gold only, never as engine input.

| Scope | n (ONC / VUS) | Sensitivity | Specificity on gold VUS | AUROC | PPV |
|---|---|---|---|---|---|
| All genes | 712 (416 / 296) | 0.466 [0.421–0.517] | 0.970 [0.949–0.986] | 0.852 [0.826–0.880] | 0.956 |
| CIViC or panel genes | 354 (266 / 88) | 0.658 [0.598–0.714] | 0.898 [0.830–0.955] | 0.863 [0.817–0.903] | 0.951 |
| Nine Horak genes | 236 (198 / 38) | 0.798 [0.742–0.854] | 0.789 [0.658–0.921] | 0.875 [0.820–0.925] | 0.952 |

Read this as validation of **oncogenic detection only**. Benign labels are almost absent from
ClinVar oncogenicity (2 of 714), so benign recall cannot be measured, and a gold "uncertain" label
means insufficient evidence, not benignity. The nine-gene subset is dominated by TP53 (130
variants), where DMS evidence drives both true and false positives. 678 of the 712 variants were
classified by a single laboratory (Center for Genomic Medicine, Rigshospitalet; sensitivity 0.474,
specificity 0.968 on those alone), so this is a single-laboratory external set; if that laboratory
used the same public functional data, labels and engine are not fully independent.

## Pre-registered input-expansion round (robustness)

On 2026-09-24 a sealed, pre-registered round tested whether richer open inputs would improve the
SOP-strict engine (`sop_strict_v2` family in `CONFIGS`; all configurations and per-change ablations
reported in `vicc_config_comparison.json`):

- (a) OP1/SBP1 only when AlphaMissense, REVEL and CADD all agree at ClinGen-calibrated thresholds;
- (b) SBVS1/SBS1 on the maximum of the five SOP continental gnomAD populations;
- (c1) the CIViC monthly release; (c2) pre-registered MaveDB DMS sets.

| | SOP-strict (primary) | SOP-strict v2 | McNemar vs primary |
|---|---|---|---|
| Horak-70 accuracy (3-class) | 0.657 [0.543–0.771] | 0.657 [0.543–0.771] | 2 / 2, p = 1.0 |
| Horak-70 sensitivity / specificity / AUROC | 0.424 / 1.000 / 0.885 | 0.364 / 1.000 / 0.900 | |
| ClinVar, nine genes: sensitivity | 0.798 | 0.747 | 0 / 10, p = 0.002 |
| ClinVar, all genes: sensitivity | 0.466 | 0.394 | 0 / 30, p < 0.001 |

The whole effect came from change (a): at ClinGen thresholds, CADD and REVEL often place somatic
hotspots in the indeterminate range (a germline-calibrated scale), so the all-agree condition
blocks OP1. Changes (b), (c1) and (c2) changed no Horak call. No v2-family configuration differed
significantly from SOP-strict on Horak-70, and the input expansion lowered ClinVar sensitivity, so
**the primary engine stays SOP-strict**.

## Integrity

- The Horak gold `points` and `sop_codes` columns are **never read** by the engine.
- DMS cutoffs are anchored to each assay's internal controls (nonsense = loss of function) or a
  classifier's natural cut, not tuned to Horak labels.
- Components of the SOP-strict configuration were fixed from the SOP text before results were
  examined. A variant with OM1 returned to domain-level scope gives accuracy 0.671 and sensitivity
  0.455, so the conclusion does not rest on the OM1 scope decision.
- **CIViC temporal integrity**: evidence IDs in the snapshot top out at EID 12,947 (none ≥ 15,000,
  the range of post-2022 submissions), and 88% of the source PMIDs predate 2022, so no CIViC item
  used by the rule arm was created after the Horak gold labels were set.
- History: earlier drafts of this work reported a different engine configuration. It is retained
  as the `original` sensitivity configuration, alongside `os2_fixed`, in
  `vicc_config_comparison.json`; the change is documented in the correction note of
  `docs/manuscript/preprint.md`.

## Reproduce

```bash
python -m scripts.fetch_hotspots                   # cancerhotspots -> data/knowledge/hotspots/
python -m scripts.fetch_dms                        # MaveDB DMS -> data/knowledge/functional/
python -m scripts.run_horak_vicc                   # SOP-strict on Horak-70 -> data/benchmark/horak_vicc.json
python -m scripts.run_clinvar_onc_holdout          # ClinVar FTP oncogenicity holdout
python -m scripts.run_oncovi_headtohead            # vs OncoVI on 69 shared variants
python -m scripts.run_hemaguide_headtohead         # vs HemaGuide molecular mode on 70
python -m scripts.run_cancervar_headtohead         # cross-axis error-profile contrast
python -m scripts.fetch_horak_clinvar              # OS1 lookup for the dial (ClinVar FTP snapshot)
python -m scripts.run_horak_sensitivity_modes      # sensitivity dial
python -m scripts.run_vicc_config_suite && python -m scripts.build_vicc_config_comparison   # all configurations
pytest tests/test_vicc_rules.py tests/test_vicc_configs.py tests/test_vicc_v2.py
```
