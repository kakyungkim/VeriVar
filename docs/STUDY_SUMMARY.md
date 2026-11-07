# Study Summary — Dual-Mode, Citation-Grounded Somatic Variant Interpretation

Consolidated **Dataset · Methods · Results** reference for manuscript drafting.
Research/education only — NOT for clinical use. All figures below are read from the
committed output artifacts (not from memory); regenerate via the commands in §6.

One-line contribution:
> A **dual-mode** (LLM vs rule) somatic variant interpreter on **two international
> standards** (VICC oncogenicity + AMP/ASCO/CAP tier), built on **hybrid,
> citation-grounded retrieval** (structured KB + dense RAG + knowledge graph +
> foundation-model evidence), evaluated for **faithfulness** and against an
> **external, temporally leakage-controlled** gold standard.

> **(2026-06-14) Naming + framing:** the system is named **VeriVar**; its deterministic
> rule arm is "VeriVar (rule arm) — a citable VICC point-based implementation" (VICC =
> the external ClinGen/CGC/VICC guideline, never the system name). The manuscript is
> framed around **clinical decision-support** (framing only — claims unchanged):
> faithfulness is the *mechanism*, a trustworthy, auditable, expert-verifiable draft is
> the *purpose*; clinical utility is explicitly **"motivated, not measured"** (no patient
> outcomes; research-only).
>
> **(2026-09-27) Current status.** Target venue **medRxiv (Genetic and Genomic Medicine)**;
> posting and public repository planned for **2026-10-10**; affiliation Independent Researcher,
> Seoul. Headline = **faithfulness/auditability**, measured as citation existence
> (`data/outputs/citation_taxonomy.json`), with citation support reported separately as a noisy
> lower bound. Accuracy: **no arm shows a significant difference at n = 70; no accuracy gain or
> parity is claimed.** The VICC rule arm is the **SOP-strict** implementation (§3.8).

---

## 1. Datasets

### 1.1 Patient cohort (input variants)
- Source: **cBioPortal REST API** (TCGA PanCancer Atlas), public, no token.
- **5 cancer types** (deliberate narrative contrast): Lung adenocarcinoma (NSCLC),
  Breast, Colorectal, Cutaneous Melanoma, Pancreatic. **7 samples each = 35 samples.**
- Restricted to a **27-gene driver panel**; deterministic selection guarantees
  showcase variants (notably **BRAF V600E in BOTH melanoma and colorectal** for the
  context-dependence analysis).
- After de-duplication by (gene, protein change, cancer) and tiered selection
  (all CIViC-bearing + capped AlphaMissense-only + abstention examples):
  **56 variant×context units classified** (of 398 unique; 416 raw candidate calls).

### 1.2 Knowledge sources (evidence layer; offline snapshots)
| Source | Content | Snapshot |
|---|---|---|
| **CIViC** (nightly TSV, CC0) | clinical evidence statements, drugs, trial links, evidence_type/direction/significance | 1,714 panel evidence rows |
| **DGIdb** (GraphQL) | gene–drug interactions | 2,608 interactions / 27 genes |
| **AlphaMissense** via **Ensembl VEP REST** (GRCh37) | computational pathogenicity (→ VICC OP1/SBP1) | 352 missense SNVs scored |
| **ClinicalTrials.gov** API v2 | trial status/phase/title for CIViC NCT ids | 37 trials |
| Dense corpus | CIViC evidence statements embedded (NeuML/pubmedbert), persistent Chroma index | 1,714 docs |

### 1.3 External benchmark (ground truth)
- **Horak et al. 2022**, ClinGen/CGC/VICC oncogenicity standard (Genet Med; PMC9081216),
  Supplemental Table 3. Manually downloaded (publisher anti-bot); parsed to TSV.
- **70 expert-classified somatic variants / 9 genes** (FLT3, BRAF, IDH1, KRAS, PIK3CA,
  PTEN, RB1, EZH2, TP53), with build38/37 coordinates, VICC points, and SOP codes.
- **Balanced 5-class** label distribution (a *discriminating* benchmark, unlike CIViC
  assertions which are ~82% one class): VUS 30, Likely Oncogenic 19, Oncogenic 14,
  Benign 5, Likely Benign 2.

### 1.4 Provenance / licensing / reproducibility
- Cohort + CIViC/DGIdb snapshots committed for offline reproducibility (`data/cohorts/`,
  `data/knowledge/civic|dgidb/`). Large/binary (Chroma index, AlphaMissense full TSV) and
  the Horak supplementary (`data/benchmark/`) are gitignored; reproduced via scripts.
- Licensing respected: CIViC CC0, ClinicalTrials/ClinVar public, TCGA open-access tier
  (cited), AlphaMissense CC BY-NC-SA (not committed), Horak labels not redistributed.
- No proprietary/clinical data; secrets via env-var names only (`OPENAI_API_KEY`).

---

## 2. Methods

### 2.1 Classification standards (two axes)
- **Oncogenicity** — ClinGen/CGC/VICC 2022: Oncogenic / Likely Oncogenic / VUS /
  Likely Benign / Benign (point-based codes OVS1…SBP2).
- **Clinical tier** — AMP/ASCO/CAP 2017: Tier I–IV (+ evidence Level A–D for Tier I/II).
- ACMG/AMP-2015 (germline) intentionally not used. Enforced as enums.

### 2.2 Hybrid, citation-grounded retrieval
Per variant, an evidence bundle is assembled from three arms, each item carrying a
**citable id**:
1. **Structured** — exact gene+protein-change lookup (CIViC), gene-level drugs (DGIdb),
   AlphaMissense (coordinate) → VICC computational code.
2. **Dense RAG** — domain embeddings (NeuML/PubMedBERT; OpenAI as ablation) over CIViC
   statements, **BM25 + Chroma fused by Reciprocal Rank Fusion**; attaches only
   same-variant hits (guards against same-gene topic drift).
3. **GraphRAG** — networkx KG (gene·variant·disease·drug·trial), multi-hop related
   variants via shared drug.
- **Faithfulness contract**: classifications cite only retrieved ids; **abstain (VUS)**
  when no variant-specific evidence (`has_variant_evidence`; gene-level drugs don't count).

### 2.3 Dual-mode classification
- **Mode A (LLM)** — gpt-4o-mini, structured output to the enum vocabulary, grounded on
  the bundle. Enhanced with **self-consistency voting** (n=3, agreement→confidence) and an
  **agentic verifier** (adversarial second pass; downgrades over-claims; skipped on
  abstained calls).
- **Mode B (rule)** — deterministic, **direction-aware**: CIViC significance/direction
  (e.g. "Unaltered Function", "Does Not Support") count against oncogenicity; only
  Sensitivity/Response evidence confers actionability (gene-level druggability does not).
  The LLM writes the explanation only.
- Baseline (ablation): **LLM no-retrieval** (parametric only).

### 2.4 Evaluation harness
- **Leakage-free faithfulness metrics** (no external truth): hallucinated-citation rate,
  citation grounding, directional faithfulness, abstention recall, inter-mode Cohen's κ.
- **Citation taxonomy** (`src/eval/citation_taxonomy.py`, `scripts/run_citation_taxonomy.py`):
  one pre-specified taxonomy applied identically to the retrieval, post-gate and no-retrieval
  arms — (a) in bundle, (b1) fabricated identifier (placeholder pattern, no numeric scheme, or no
  NCBI record), (b2) real and related but outside the bundle, (c) real but unrelated
  (misattributed), (d) non-identifier token (imprecision). Identifiers resolved via NCBI E-utilities.
- **Type II attribution audit** (`scripts/run_nli_attribution.py`): DeBERTa-v3 NLI, threshold
  0.5 fixed a priori, no LLM calls; does the cited record entail the claim that cites it?
- **Ablation**: rule / LLM-no-RAG / LLM+RAG.
- **External benchmark** (Horak): 5-class + collapsed 3-class accuracy & κ vs gold.
- **Temporal split**: RAG corpus restricted to pre-cutoff publication year.
- **8 additional analyses** (cross-cancer consistency, sensitivity/resistance, dense
  recall-lift, AlphaMissense↔LLM, calibration, discordance concentration, hotspot-vs-rare,
  verifier net-effect).
- Config: gpt-4o-mini, temperature 0 (0.4 for voting); torch 2.2.2 / sentence-transformers
  3.0.1 (Intel-mac safetensors constraint). 105 unit tests.

---

## 3. Results

### 3.1 Dual-mode agreement (cohort, 56 variants; dense+vote+verify)
- Oncogenicity concordance **0.786**, tier concordance 0.571; **31 discordant**.
- Inter-mode Cohen's κ: oncogenicity **0.713**, tier 0.417.
- Discordance types: **17 tier-boundary**, 6 oncogenic-confidence, **3 beyond-rules**
  (rule over-calls a driver; LLM reads evidence → not a driver), 2 benign-label,
  2 verifier-downgrade, 1 llm-overcall. **26/31 adjacent (1 step), only 5 gross.**

### 3.2 Faithfulness (leakage-free) — headline
Source: `data/outputs/citation_taxonomy.json`, `data/outputs/nli_attribution_report.json`.
- **Citation existence, retrieval arm (pre-gate, gpt-4o-mini):** 106 citation tokens on 56
  variants; **0 of 86 identifier citations outside the bundle** (one-sided 95% Clopper–Pearson
  upper bound 3.4%); the other **20 are non-identifier tokens** (e.g. bare "AlphaMissense"),
  counted as imprecision, not fabrication.
- **Post-gate scorecard (enforced by construction, not measured):** hallucinated-citation rate
  0.0, citation grounding 1.0, directional faithfulness 1.0, abstention recall 1.0; the primary
  post-gate run has 90 citations, all in bundle.
- **Citation support (Type II), primary run:** NLI supported **40/90 = 0.444 [0.344–0.544]**
  (variant-clustered 0.348–0.543), neutral 0.478, contradicted 0.078. Read as a **noisy lower
  bound**: hand review found the NLI labels biased against support; 3 genuine mismatches among
  the inline neutral citations.

### 3.3 Ablation — what RAG contributes
- **No-retrieval arm: 19/56 variants (0.339, Wilson 95% CI 0.229–0.470) carry a fabricated or
  misattributed identifier** (14/56 fabricated alone, 0.250 [0.155–0.377]); retrieval arm 0/56.
  Paired exact McNemar p = 3.8×10⁻⁶ (19 vs 0 discordant). Of the no-retrieval arm's 56 tokens,
  28 are fabricated identifiers, 13 real but unrelated records, 15 non-identifiers
  (`citation_taxonomy.json`).
- No-RAG vs RAG tier κ = 0.18 (materially different); no-RAG over-calls **12/56 (21.4%)**
  variants oncogenic/likely-oncogenic that **RAG resolves to VUS** by reading variant-specific
  evidence (e.g. EGFR E114K, PTEN R130*, TP53 P152L). This measures behavioural change, NOT
  correctness — whether each resolution is an appropriate correction or an over-conservative
  downgrade is pending expert adjudication.
- → Retrieval **(1) removes out-of-bundle identifier citations** (Type I) and **(2) suppresses parametric over-calling (correctness pending expert adjudication).** It does not guarantee that a cited record supports its claim (§3.2).

### 3.4 Additional analyses
- **Cross-cancer consistency**: oncogenicity stable on all 4 multi-cancer variants;
  context-dependent tier in 1 (**KRAS G12V**: CRC Tier I vs Pancreatic Tier II).
- **AlphaMissense ↔ LLM agreement 0.944** (computational vs LLM oncogenicity).
- **Dense recall-lift**: 2 variants gained CIViC evidence exact-match missed (decisive
  for PIK3CA H1047R).
- **Discordance concentration**: TP53 (7/7); **hotspot 0.54 ≈ non-hotspot 0.56**
  (disagreement is tier-boundary, not rare-variant difficulty).
- **Verifier net-positive**: changed 10 tiers (6 toward rule / 4 away); tier concordance
  0.518 → 0.571. Voting confidence is calibrated (low agreement → 100% discordant once the
  verifier-cap confound is removed).

### 3.5 External benchmark — Horak 2022 (70 variants)
| method | 5-class acc | 3-class acc | κ (3-class) |
|---|---|---|---|
| rule | 0.357 | 0.557 | 0.274 |
| **LLM + RAG** | 0.357 | **0.600** | **0.332** |
| LLM no-RAG | 0.457 | 0.586 | 0.254 |
- LLM+RAG has the highest point estimate on the 3-class collapse (**oncogenic recall 0.79**), BUT
  **accuracy differences are NOT statistically significant** at n=70: 3-class acc 95% CIs
  overlap heavily (rule 0.557 [0.44–0.67], RAG 0.600 [0.49–0.71], no-RAG 0.586 [0.47–0.70]);
  McNemar RAG-vs-no-RAG p=1.0, RAG-vs-rule p=0.61. → Do NOT claim accuracy superiority or
  equivalence; state **"not significantly different"** (absence of evidence of a difference at
  n = 70; no non-inferiority margin was pre-specified). The faithfulness gap IS significant — §3.3.
- Hardest class is VUS (recall 0.37, over-resolved); 7 oncogenic→VUS misses are
  thin-coverage rare PTEN/EZH2 variants (mean 1.0 evidence items). 5-class hard for all.

### 3.6 Temporal split — leakage control (RAG corpus restricted by publication year)
| corpus cutoff | evidence | 3-class acc | oncogenic recall |
|---|---|---|---|
| full | 988 | 0.586 | 0.73 |
| < 2018 | 885 | 0.629 | 0.82 |
| < 2015 | 666 | 0.600 | 0.82 |
| **< 2012** | 459 | **0.643** | **0.85** |
| *no-RAG floor* | — | 0.586 | — |
- Accuracy is **stable** under temporal holdout — even with the corpus cut to **pre-2012
  literature** (< half; a decade before the 2022 gold), 3-class accuracy is unchanged within
  noise (point estimates 0.586→0.643, but at n=70 the ~±0.11 CIs overlap — the small upward
  drift is NOT significant; do not claim it improves).
- → Interpretation: performance does **not** depend on retrieving recent answer-stating
  evidence (the RAG-corpus leakage channel is not driving results). State as robustness, not gain.

---

### 3.7 Robustness checks (Horak, 3-class)
- **Second model**: gpt-4o reaches higher point estimates (acc3 **0.70**, κ3 0.51, vs gpt-4o-mini
  0.60/0.33) — but the gain is **NOT significant** (McNemar p=0.21, n=70). Read as "results are not
  a gpt-4o-mini artifact and do not worsen with a stronger model", not "gpt-4o is better".
- **LOVO (leave-own-evidence-out)**: removing each variant's OWN CIViC evidence leaves accuracy
  statistically unchanged (0.614 vs 0.600 full; McNemar p=1.0) — the **strongest leakage control**:
  performance does not depend on retrieving the variant's own curated answer-evidence.
- **Embedding ablation** (recall@5 of own evidence): PubMedBERT 0.243 ≈ MiniLM 0.229 ≈ OpenAI 0.229
  — embedder choice is not a sensitive factor (small domain-model edge).
- Files: `data/benchmark/horak_{gpt4o,lovo}.json`, `embed_ablation.json`.

### 3.8 VeriVar's rule arm — SOP-strict VICC engine (primary since 2026-09-24)
`src/classify/vicc_rules.py`, `CONFIGS["sop_strict"]`: Horak 2022 Tables 2–3, point ranges and
exclusion rules applied as written where open data allow; OP4 only from observed gnomAD data;
OM1 only at UniProt active/binding sites; CIViC functional evidence only; no non-SOP guards.
OS1, OM4, OP2, SBP2 not evaluable from open data (unassigned). Deterministic, **not** the LLM,
**not** claimed as a novel or accuracy-competitive classifier. Full description:
`docs/reference/vicc_rule_arm.md`.

| Horak-70 (n = 70) | value | source |
|---|---|---|
| 3-class accuracy | **0.657 [0.543–0.771]** | `data/benchmark/horak_vicc.json` |
| 5-class accuracy | 0.500 | same |
| oncogenic sensitivity | 0.424 (14/33; Wilson 0.272–0.592) | same |
| specificity | **1.000 (37/37; Wilson 0.906–1.000)** | same |
| AUROC (points) | 0.885 | same |
| predicted ONC / VUS / BEN | 14 / 43 / 13 | same |
| oncogenic over-calls | 0 (six benign-direction errors) | `vicc_config_comparison.json` |

Head-to-heads (exact McNemar, paired on 3-class correctness; `vicc_config_comparison.json`):
- **OncoVI**, 69 shared: ours 0.652 [0.536–0.754] vs 0.797; p = 0.087 (9 vs 19). Not significant;
  OncoVI higher in point estimate. Errors run in opposite directions (ours: oncogenic left at VUS;
  OncoVI: 7 oncogenic over-calls on gold-VUS). `oncovi_headtohead.json`.
- **HemaGuide molecular mode**, 70: ours 0.657 vs 0.800; p = 0.087 (9 vs 19). `hemaguide_headtohead.json`.
- **CancerVar** (AMP/ASCO/CAP **actionability** axis — **CROSS-AXIS**; tiers mapped I/II→Oncogenic,
  III→VUS, IV→Benign only to score it): read strictly as an **error-profile contrast**, not an
  accuracy benchmark. On 70 shared variants CancerVar made 21 over-calls and 0 misses
  (sensitivity 1.0, specificity 0.432) vs the rule arm's 0 over-calls and 19 misses (specificity
  1.000). Mapped 3-class 0.657 vs 0.614, p = 0.771 (completeness only). `cancervar_headtohead.json`.
  **The cross-axis caveat must travel with every CancerVar mention.**
- **CGI** — deferred (registration-token-gated API; `data/benchmark/cgi/FEASIBILITY_BLOCKED.json`).

**Sensitivity dial** (non-SOP levers; `vicc_config_comparison.json` `dial_table2`): sensitivity
0.424 → at most 0.545 (specificity 0.973–0.946, accuracy 0.657–0.700); every setting stays below
OncoVI and HemaGuide. SOP-strict default remains the headline.

**ClinVar somatic-oncogenicity holdout** (`data/benchmark/clinvar_onc_holdout.json`; rebuilt from
the ClinVar FTP aggregate Oncogenicity field; Horak-70 overlap removed; 714 keys, 2 benign keys
excluded from the binary task):

| scope | n (ONC / VUS) | sensitivity | specificity (gold VUS) | AUROC | PPV |
|---|---|---|---|---|---|
| all genes | 712 (416 / 296) | 0.466 [0.421–0.517] | 0.970 [0.949–0.986] | 0.852 [0.826–0.880] | 0.956 |
| CIViC or panel genes | 354 (266 / 88) | 0.658 [0.598–0.714] | 0.898 [0.830–0.955] | 0.863 [0.817–0.903] | 0.951 |
| nine Horak genes | 236 (198 / 38) | 0.798 [0.742–0.854] | 0.789 [0.658–0.921] | 0.875 [0.820–0.925] | 0.952 |

Validates **oncogenic detection only** (benign labels 2 of 714). 678 of the 712 scored variants
were classified by a single laboratory (Rigshospitalet; sensitivity 0.474, specificity 0.968 on
those alone, `robustness.rigshospitalet_only`), so this is a single-laboratory external set.

### 3.9 Pre-registered input-expansion round (robustness; 2026-09-24)
Sealed pre-registration (`notes/audits/2026-09-24/개선라운드_사전명시_20260924.md`, local) before
inputs were fetched: (a) OP1/SBP1 only when AlphaMissense, REVEL and CADD all agree at ClinGen
thresholds, (b) SBVS1/SBS1 on the maximum of five continental gnomAD populations, (c1) CIViC
monthly release, (c2) pre-registered MaveDB sets. All configurations and per-change ablations
reported (`vicc_config_comparison.json`, `sop_strict_v2` family).
- **Horak-70:** accuracy unchanged, 0.657 [0.543–0.771]; sensitivity 0.424 → 0.364; specificity
  1.000; AUROC 0.885 → 0.900; McNemar vs SOP-strict 2 vs 2, p = 1.0.
- **ClinVar holdout:** sensitivity fell — nine genes 0.798 → 0.747 (McNemar 0/10, p = 0.002),
  all genes 0.466 → 0.394 (0/30, p < 0.001); specificity and AUROC essentially unchanged.
- The whole effect came from change (a); (b), (c1), (c2) changed no Horak call.
- **Decision: the primary engine stays SOP-strict.** No v2-family configuration differed
  significantly from SOP-strict on Horak-70.

## 4. Claim stack (manuscript) — statistically disciplined
1. **Citation existence: faithful empirically and by construction (significant)**: 0 of 86
   identifier citations outside the bundle with retrieval (pre-gate) vs **19/56 variants with a
   fabricated or misattributed identifier without retrieval, 0.339 [0.229–0.470]**, exact McNemar
   p = 3.8×10⁻⁶. The post-gate 0 / 1.0 / 1.0 / 1.0 scorecard is enforced, not measured.
   **Citation support** is the open part: NLI 0.444 [0.344–0.544], a noisy lower bound.
2. **RAG suppresses parametric over-calling**: no-RAG over-calls (EGFR E114K, PTEN R130*,
   TP53 P152L) that RAG resolves to VUS by reading variant-specific evidence.
3. **Accuracy: not significantly different, no gain claimed**: on the balanced expert gold
   standard, LLM+RAG vs rule and no-RAG differences are NOT significant at n=70 (McNemar
   p=1.0 / 0.61; overlapping CIs). The SOP-strict rule arm (0.657) is lower than OncoVI and
   HemaGuide in point estimate (p = 0.087 each) and is reported for its error profile (no
   oncogenic over-call), not its accuracy.
4. **Leakage-controlled robustness**: accuracy is stable (not significantly changed) under a
   pre-2012 temporal corpus holdout → the (modest) RAG behaviour is not recent-answer retrieval.
5. **Dual-mode discordance is an analytical signal**: mostly fine-grained tier boundaries
   + a few interpretable beyond-rules corrections, concentrated in TP53.

> Headline = **faithfulness/auditability** (significant), NOT accuracy gains (n too small).
> Stats: `data/outputs/stats_report.json` (generative-arm bootstrap 95% CI + exact McNemar),
> `data/outputs/citation_taxonomy.json` (faithfulness), `data/benchmark/vicc_config_comparison.json`
> (rule arm). Note: `stats_report.json` still carries an older `norag_citation_fabrication_ci`
> field; the faithfulness headline is read from `citation_taxonomy.json`.

## 5. Limitations (state honestly)
- Absolute 5-class accuracy is modest (~0.36–0.46); VICC 5-class is intrinsically hard.
- **VUS calibration** (over-resolution) and **rare-variant coverage** (thin evidence →
  abstention) are real weaknesses → motivate broader sources / foundation-model weighting.
- **LLM parametric leakage** is not controlled by the temporal split (only the RAG channel);
  quantified by the no-RAG floor.
- Single-sample, gene/protein-change level, n=70 external set, single LLM (gpt-4o-mini).
- The Deterministic-mode rule is simplified (though direction-aware, not a strawman). The VICC
  rule arm follows the SOP text where open data allow, but OS1, OM4, OP2 and SBP2 are unassigned,
  OP1/SBP1 use a single predictor, and population frequencies are global, not per continent.
- **Citation support** is measured only approximately (NLI lower bound 0.444).
- **Input-context ablation:** an HGNC alias symbol or three-letter HGVS removed all curated
  clinical evidence for the 26 variants that had any, yet 22 kept a driver call on the
  AlphaMissense prior alone (0 of 228 citations out of bundle). The abstention contract accepts
  a computational prior as variant-specific evidence (`data/outputs/context_ablation.json`).
- **Comparator caveats:** the CancerVar head-to-head (§3.8) is **cross-axis**
  (actionability tiers re-graded onto the VICC oncogenicity gold) → read as an error-profile
  contrast (specificity / over-call asymmetry), not an oncogenicity-accuracy benchmark; the
  resulting accuracy gap is largely a mapping artifact. **CGI** (Cancer Genome Interpreter) was
  considered as a near-axis comparator but **deferred** — its per-variant predictions require a
  registration-gated authentication token unavailable in scope (`data/benchmark/cgi/FEASIBILITY_BLOCKED.json`);
  extending the head-to-head to CGI is future work.
- **Provisional expert-adjudication (AI-assisted, NOT yet expert-signed — see
  `notes/expert_adjudication_worksheet.md`):** on the 3 beyond-rules discordances, evidence review
  suggests **rule right 2/3, LLM/RAG right 1/3** — PTEN R130* (melanoma; rule correct: truncating LoF
  in a tumour-suppressor → VICC OVS1; LLM over-abstained) and PIK3CA R88Q (colorectal; rule correct:
  validated gain-of-function [Gymnopoulos 2007], OncoKB Oncogenic; the CIViC hits were predictive/
  cetuximab-resistance, not oncogenicity) favour the rule, while ESR1 E247K (colorectal; LLM/RAG
  correct: outside LBD hotspots, no functional evidence, only AlphaMissense 0.840; rule over-called on
  that prior alone) favours the LLM. ⇒ the "beyond-rules" label over-credits the LLM; these are mostly
  over-conservative abstentions, reinforcing the VUS-over-resolution limitation. Concrete fix:
  encode **OVS1** (null variant in TS gene) so truncating variants aren't abstained. Requires a
  board-certified molecular pathologist to confirm before any of this enters the manuscript.

## 6. Reproducibility (commands)
```bash
./setup.sh
python -m scripts.fetch_cohort && python -m scripts.fetch_knowledge && python -m scripts.fetch_variant_evidence
python -m scripts.build_index
python -m src.pipeline --vote --verify --dense          # main run
python -m scripts.run_eval && python -m scripts.run_ablation
python -m scripts.run_analyses && python -m scripts.analyze_discordance
python -m src.pipeline --vote --dense --out cohort_noverify && python -m scripts.verifier_effect
# external benchmark (needs Horak supplement-3.xlsx in data/benchmark/horak/):
python -m scripts.build_horak_benchmark && python -m scripts.fetch_horak_evidence
python -m scripts.run_horak_benchmark && python -m scripts.run_horak_temporal
# faithfulness endpoints (NCBI lookup cache committed; no LLM calls):
python -m scripts.run_citation_taxonomy && python -m scripts.run_nli_attribution
# VICC rule arm (SOP-strict primary + all configurations, offline):
python -m scripts.run_vicc_config_suite && python -m scripts.build_vicc_config_comparison
```
Artifacts: `data/outputs/{cohort_interpretation,eval_report,ablation_report,analyses_report,verifier_effect,discordance_analysis,citation_taxonomy,nli_attribution_report,context_ablation}.json`, `data/benchmark/{horak_results,horak_temporal,horak_vicc,vicc_config_comparison,clinvar_onc_holdout}.json`, `data/outputs/cohort_report.{html,pdf}`, dashboard `src/dashboard/app.py`.
