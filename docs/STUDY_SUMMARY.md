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
- **Ablation**: rule / LLM-no-RAG / LLM+RAG.
- **External benchmark** (Horak): 5-class + collapsed 3-class accuracy & κ vs gold.
- **Temporal split**: RAG corpus restricted to pre-cutoff publication year.
- **8 additional analyses** (cross-cancer consistency, sensitivity/resistance, dense
  recall-lift, AlphaMissense↔LLM, calibration, discordance concentration, hotspot-vs-rare,
  verifier net-effect).
- Config: gpt-4o-mini, temperature 0 (0.4 for voting); torch 2.2.2 / sentence-transformers
  3.0.1 (Intel-mac safetensors constraint). 90 unit tests.

---

## 3. Results

### 3.1 Dual-mode agreement (cohort, 56 variants; dense+vote+verify)
- Oncogenicity concordance **0.786**, tier concordance 0.571; **31 discordant**.
- Inter-mode Cohen's κ: oncogenicity **0.713**, tier 0.417.
- Discordance types: **17 tier-boundary**, 6 oncogenic-confidence, **3 beyond-rules**
  (rule over-calls a driver; LLM reads evidence → not a driver), 2 benign-label,
  2 verifier-downgrade, 1 llm-overcall. **26/31 adjacent (1 step), only 5 gross.**

### 3.2 Faithfulness (leakage-free) — headline
- **Hallucinated-citation rate 0.0** · citation grounding **1.0** · directional
  faithfulness **1.0** · abstention recall **1.0**.

### 3.3 Ablation — what RAG contributes
- **No-RAG LLM fabricates citations on 26/56 (46%)** vs **RAG 0%.**
- No-RAG vs RAG tier κ = 0.18 (materially different); no-RAG over-calls **12/56 (21.4%)**
  variants oncogenic/likely-oncogenic that **RAG resolves to VUS** by reading variant-specific
  evidence (e.g. EGFR E114K, PTEN R130*, TP53 P152L). This measures behavioural change, NOT
  correctness — whether each resolution is an appropriate correction or an over-conservative
  downgrade is pending expert adjudication.
- → RAG **(1) eliminates citation hallucination** and **(2) suppresses parametric over-calling (correctness pending expert adjudication).**

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
  McNemar RAG-vs-no-RAG p=1.0, RAG-vs-rule p=0.61. → Do NOT claim accuracy superiority; claim
  **non-inferiority + faithfulness**. (The faithfulness gap IS significant — see §3.3/§4.)
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

## 4. Claim stack (manuscript) — statistically disciplined
1. **Faithful by construction & empirically (significant)**: 0% citation hallucination,
   100% grounding/directional-faithfulness/abstention. The gap vs no-RAG is robust:
   no-RAG fabricates citations **0.464 [0.34–0.59]** vs RAG 0 (CI excludes 0).
2. **RAG suppresses parametric over-calling**: no-RAG over-calls (EGFR E114K, PTEN R130*,
   TP53 P152L) that RAG resolves to VUS by reading variant-specific evidence.
3. **Accuracy: non-inferior, NOT superior**: on the balanced expert gold standard, LLM+RAG
   is comparable to rule and no-RAG — accuracy differences are NOT significant at n=70
   (McNemar p=1.0 / 0.61; overlapping CIs). Frame as "faithful AND non-inferior", not "more accurate".
4. **Leakage-controlled robustness**: accuracy is stable (not significantly changed) under a
   pre-2012 temporal corpus holdout → the (modest) RAG behaviour is not recent-answer retrieval.
5. **Dual-mode discordance is an analytical signal**: mostly fine-grained tier boundaries
   + a few interpretable beyond-rules corrections, concentrated in TP53.

> Headline = **faithfulness/auditability** (significant), NOT accuracy gains (n too small).
> Stats: `data/outputs/stats_report.json` (bootstrap 95% CI + exact McNemar).

## 5. Limitations (state honestly)
- Absolute 5-class accuracy is modest (~0.36–0.46); VICC 5-class is intrinsically hard.
- **VUS calibration** (over-resolution) and **rare-variant coverage** (thin evidence →
  abstention) are real weaknesses → motivate broader sources / foundation-model weighting.
- **LLM parametric leakage** is not controlled by the temporal split (only the RAG channel);
  quantified by the no-RAG floor.
- Single-sample, gene/protein-change level, n=70 external set, single LLM (gpt-4o-mini).
- The rule baseline is simplified (though direction-aware, not a strawman).
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
```
Artifacts: `data/outputs/{cohort_interpretation,eval_report,ablation_report,analyses_report,verifier_effect,discordance_analysis}.json`, `data/benchmark/{horak_results,horak_temporal}.json`, `data/outputs/cohort_report.{html,pdf}`, dashboard `src/dashboard/app.py`.
