# 🧬 VeriVar — LLM-Assisted Somatic Variant Interpretation Pipeline

**Citation-grounded retrieval for faithful, auditable LLM somatic variant interpretation — dual-mode (LLM + rule), two-axis (oncogenicity + clinical tier).**

> ⚠️ **Research, education, and demonstration only. NOT for clinical diagnostics or treatment decisions.**
> Built and evaluated entirely on **public** data and knowledge bases.
>
> *VeriVar* evolved from the project formerly named **LLM_Variant_Pipeline**, where the work began; it was renamed as the system matured.

---

## Motivation

Somatic variant interpretation — judging whether a tumour mutation is oncogenic and clinically actionable — is a rate-limiting, audit-critical step in precision oncology. Rule-based engines are reproducible and auditable but rigid: their coverage of rare or under-curated variants is bounded by their databases, and they neither read free-text evidence on demand nor produce natural-language justifications.

Large language models read evidence fluently and emit structured prose, but two failure modes bar naïve clinical use:

- **Hallucinated citations** — an LLM readily emits plausible but non-existent PMIDs / database IDs to "support" a call.
- **Parametric leakage** — famous drivers (e.g. BRAF V600E) may be answered from pretraining memory rather than the supplied evidence, inflating apparent accuracy and producing confident over-calls on benign look-alikes.

This project asks a focused question: **can retrieval grounding make LLM variant interpretation faithful and auditable — and is any accuracy effect genuine or a leakage artifact?** The headline result concerns faithfulness: with retrieval, the model cited no identifier outside the evidence it was given, while the same model without retrieval fabricated or misattributed identifiers on a third of variants. Citation *existence* can be guaranteed by construction; citation *support* (does a real citation say what the rationale claims?) is measured only approximately. Accuracy is reported with deliberate statistical discipline: at n = 70 no arm shows a significant accuracy difference, and no accuracy gain is claimed.

---

## What the pipeline does

For each variant, the system — **VeriVar** — assembles a **citable evidence bundle** via hybrid retrieval, then classifies the variant on **two international standards** under a **faithfulness contract**, running multiple interpretation arms on every variant for comparison. It is positioned as **clinical decision-support**: faithfulness is the *mechanism* and a trustworthy, auditable, expert-verifiable draft is the *purpose*; clinical utility is **motivated, not measured** (no patient outcomes — research-only).

### Two-axis classification

| Axis | Standard | Labels |
|---|---|---|
| **Oncogenicity** | ClinGen/CGC/VICC 2022 (Horak et al.) | Oncogenic · Likely Oncogenic · VUS · Likely Benign · Benign |
| **Clinical tier** | AMP/ASCO/CAP 2017 (Li et al.) | Tier I–IV (evidence levels A–D for Tiers I/II) |

> ACMG/AMP 2015 is the *germline* standard and is intentionally **not** used; its somatic analogue is the VICC oncogenicity scale. Tumour-type context matters — the same variant can map to different tiers across cancers.

### Interpretation arms

- **Generative mode (Mode A)** — the LLM assigns the labels itself, grounded on the evidence bundle, with self-consistency voting (n = 3) and an agentic adversarial verifier. For exploratory interpretation and rare/under-curated variants.
- **Deterministic mode (Mode B)** — a transparent, direction-aware rule fixes the label; the LLM writes only the human-readable rationale. For reproducibility and review safety (identical output every run).
- **VeriVar (rule arm) — a citable, SOP-strict VICC point-based implementation** — a deterministic engine that applies the Horak et al. 2022 criteria, point ranges and exclusion rules as written wherever open data allow, and leaves unevaluable criteria unassigned. Every fired criterion is a citable record. Reported for its auditability and error profile, not as a novel or accuracy-competitive classifier. Details: [`docs/reference/vicc_rule_arm.md`](docs/reference/vicc_rule_arm.md).
- **No-retrieval baseline** — the generative prompt with the evidence bundle removed, isolating parametric behaviour.

**Discordance between arms is treated as a primary analytical signal**, not a failure — it localises genuine interpretive uncertainty.

### Faithfulness contract

Every assertion may cite **only** retrieved identifiers, and the system must **abstain** (assign VUS) when no variant-specific evidence exists. Gene-level druggability does **not** count as variant-specific evidence.

---

## Hybrid, citation-grounded retrieval

Each evidence bundle is assembled from three arms, every item carrying a citable identifier:

| Arm | Source / method |
|---|---|
| **Structured** | Exact gene+protein-change lookup in CIViC; gene-level drug lookup in DGIdb; AlphaMissense by genomic coordinate (→ VICC computational code) |
| **Dense** | Domain embeddings (NeuML/PubMedBERT) over CIViC evidence statements; BM25 + Chroma fused by Reciprocal Rank Fusion; same-variant hits only (guards against same-gene topic drift) |
| **Graph** | networkx knowledge graph (gene · variant · disease · drug · trial); surfaces related variants via shared drugs |

---

## Data (public only, offline-reproducible)

| Layer | Source | Scale |
|---|---|---|
| **Cohort (inputs)** | TCGA PanCancer Atlas via cBioPortal REST | 5 cancers × ~7 samples (35), 27-gene driver panel → 56 variant×context units classified (of 398 candidates) |
| **Evidence** | CIViC (CC0) | 1,714 panel evidence rows |
| | DGIdb | 2,608 gene–drug interactions |
| | AlphaMissense via Ensembl VEP REST | computational pathogenicity (missense SNVs) |
| | ClinicalTrials.gov v2 | 37 trials |
| **External benchmark** | Horak et al. 2022 (ClinGen/CGC/VICC gold) | 70 expert-classified variants, 9 genes, balanced 5-class |

Cohort and knowledge snapshots are committed so the pipeline runs **offline**; network access is only used by the `scripts/fetch_*` helpers. No company proprietary data, code, internal SOPs, client data, or assay/reporting logic are used anywhere in this repository.

---

## Key results

Evaluated with leakage-free faithfulness metrics, an external gold standard, bootstrap 95% CIs, and exact McNemar tests. Primary model **gpt-4o-mini** (a conservative capability floor); robustness re-run on **gpt-4o**. The manuscript (`docs/manuscript/preprint.md`) is the authoritative statement; numbers below are read from the committed JSON files named in each bullet.

- **Faithfulness, citation existence (the headline).** With retrieval, gpt-4o-mini emitted 106 citation tokens across the 56-variant cohort; **0 of the 86 identifier citations fell outside the retrieved evidence bundle** (one-sided 95% upper bound 3.4%). The other 20 tokens were not identifiers (for example the bare source name "AlphaMissense") and are counted as imprecision, not fabrication. Without retrieval, **19 of 56 variants (0.339, Wilson 95% CI 0.229–0.470) carried a fabricated or misattributed identifier**; paired exact McNemar p = 3.8×10⁻⁶. Source: `data/outputs/citation_taxonomy.json`.
- **Faithfulness, citation support (the open part).** An entailment (NLI) audit found the cited record supporting the citing rationale for **0.444 (95% CI 0.344–0.544) of 90 citations** on the primary run. This is a noisy lower bound, not a Type II error rate; hand review found the NLI labels biased against support. Source: `data/outputs/nli_attribution_report.json`.
- **Contract guarantees.** The post-gate scorecard (hallucination 0, citation grounding 1.0, directional faithfulness 1.0, abstention recall 1.0) reports what the faithfulness gate enforces by construction, not a measured emergent property.
- **Parametric over-calling.** Retrieval reclassified **12 of 56** variants that the no-retrieval model called (likely) oncogenic to evidence-grounded VUS. This is a behavioural change; whether each reclassification is correct awaits expert adjudication. Source: `data/outputs/ablation_report.json`.
- **Generative-arm accuracy: not significantly different.** Three-class accuracy on Horak-70 was 0.600 with retrieval, 0.586 without, and 0.557 for the simplified Deterministic rule (McNemar p = 1.0 and 0.61; overlapping CIs). Faithfulness, not accuracy, is the generative arm's contribution. Source: `data/outputs/stats_report.json`.
- **Leakage controls.** Temporal corpus holdout, leave-own-evidence-out (LOVO), a second model (gpt-4o), and an embedding ablation left generative-arm accuracy statistically unchanged. They control the retrieval-corpus channel only; the model's own parametric memory remains uncontrolled and is quantified by the no-retrieval floor. Sources: `data/benchmark/horak_{temporal,lovo,gpt4o}.json`, `data/benchmark/embed_ablation.json`.
- **VeriVar's rule arm (SOP-strict VICC engine; deterministic, not the LLM).** On Horak-70: three-class accuracy **0.657 (95% CI 0.543–0.771)**, oncogenic sensitivity 0.424, **specificity 1.000 (37/37)**, AUROC 0.885, and **no oncogenic over-call**; it leaves most oncogenic variants at VUS. OncoVI (0.797 on 69 shared variants, ours 0.652) and HemaGuide's molecular mode (0.800 on 70) are higher in point estimate; neither difference is significant (exact McNemar p = 0.087 for both). At n = 70 the rule arm is not accuracy-competitive with published engines. Sources: `data/benchmark/horak_vicc.json`, `data/benchmark/vicc_config_comparison.json`.
- **Rule arm on an independent ClinVar oncogenicity holdout** (712 missense variants from the ClinVar FTP aggregate oncogenicity field, Horak-70 overlap removed): specificity **0.970 (0.949–0.986)** at sensitivity **0.466 (0.421–0.517)**, AUROC 0.852; on the nine Horak genes (n = 236), sensitivity 0.798, specificity 0.789, AUROC 0.875. This validates oncogenic detection only (benign labels are almost absent), and most labels come from a single laboratory. Source: `data/benchmark/clinvar_onc_holdout.json`.
- **Pre-registered input-expansion round (robustness).** A sealed, pre-registered round added more computational predictors, continental population frequencies, a newer CIViC release and extra MaveDB sets. Horak-70 accuracy did not change (0.657), and ClinVar sensitivity fell (nine genes 0.798 to 0.747; all genes 0.466 to 0.394), so the primary engine stays SOP-strict. Source: `data/benchmark/vicc_config_comparison.json` (`sop_strict_v2` family).
- **CancerVar (cross-axis, error profile only).** CancerVar emits AMP/ASCO/CAP actionability tiers, not VICC oncogenicity, so the comparison is read only as an error-profile contrast: on 70 shared variants it made 21 over-calls and no miss, against the rule arm's 0 over-calls and 19 misses. Source: `data/benchmark/cancervar_headtohead.json`.
- **Input-context ablation (an open weakness).** Writing a gene under an HGNC alias symbol, or the protein change in three-letter HGVS, removed every curated clinical evidence item, yet 22 of the 26 affected variants were still called (likely) oncogenic on the coordinate-keyed AlphaMissense prior alone. No citation fell outside the bundle (0 of 228), so the contract held as written while not guaranteeing that a driver call rests on curated clinical evidence. Sources: `data/outputs/context_ablation.json`, `data/outputs/context_ablation_grounding.json`.

> No accuracy-superiority claim is made for any arm. See `data/outputs/stats_report.json` and `data/benchmark/vicc_config_comparison.json`.

---

## Architecture

```
                cBioPortal cohort (TCGA, public)
                            │
                            ▼
        ┌───────── Hybrid citation-grounded retrieval ─────────┐
        │   structured (CIViC/DGIdb/AlphaMissense/trials)      │
        │   dense (BM25 + Chroma + RRF over CIViC, PubMedBERT) │
        │   graph (networkx GraphRAG)                          │
        └──────────────────────┬───────────────────────────────┘
                               ▼  citable evidence bundle
                ┌──────────────┼──────────────┬─────────────────┐
                ▼              ▼               ▼                 ▼
        Generative (A)   Deterministic (B)  VICC rule arm   No-RAG baseline
        LLM + vote +     rule label +       point-based     (ablation)
        verifier         LLM rationale
                └──────────────┴──────────────┘
                               ▼
              Dual-mode comparison · discordance analysis
                               ▼
        Eval harness (faithfulness · ablation · Horak benchmark ·
        temporal/LOVO/2nd-model/embedding leakage controls · stats)
                               ▼
              Interactive HTML/PDF report · Streamlit dashboard
```

### Repo layout

| Path | Contents |
|---|---|
| `src/models/` | Canonical pydantic schema — VICC + AMP enums, citable Evidence/EvidenceBundle, Variant, ClassificationResult, CohortInterpretation |
| `src/cohort/` | cBioPortal snapshot loader + candidate filter |
| `src/knowledge/` | Structured sources: CIViC, DGIdb, AlphaMissense (VEP), ClinicalTrials, aggregator/factory |
| `src/retrieval/` | Dense/hybrid RAG: corpus, embedders, BM25+Chroma+RRF, GraphRAG, orchestrator |
| `src/classify/` | `rules.py` (Mode B), `llm.py` (Mode A + grounded QA), voting, verifier, selection |
| `src/compare/` | Concordance/discordance between modes |
| `src/eval/` | Faithfulness/κ metrics, benchmark, typed discordance, 8 analyses, bootstrap+McNemar stats |
| `src/report/`, `templates/` | Interactive HTML + static PDF cohort report |
| `src/dashboard/` | Streamlit app (overview · variant explorer · detail + grounded chat) |
| `scripts/` | `fetch_*` (cohort/knowledge/evidence), `build_index`, eval/benchmark runners, `verify_manuscript.py` (deterministic anti-hallucination gate) |
| `data/` | Committed cohort/knowledge snapshots + generated outputs/benchmarks |
| `docs/` | `STUDY_SUMMARY.md`; `manuscript/` (medRxiv preprint + `figures/`, including `figS1_dashboard.png`); `reference/` (faithfulness, VICC rule arm, traceability check, resource manifest); `harness/` (agent-harness map); `blog/`, `talks/` |

---

## Quickstart

```bash
./setup.sh                                         # one-time: Python 3.11 venv + install
source venv/bin/activate

# full enhanced run (needs OPENAI_API_KEY in .env; falls back to offline mock if unset)
python -m src.pipeline --vote --verify --dense

# evaluation (no LLM cost — reads data/outputs/cohort_interpretation.json)
python -m scripts.run_eval                         # faithfulness suite + benchmark
python -m scripts.run_analyses                     # 8 cohort analyses
python -m scripts.analyze_discordance              # typed discordance breakdown

# reporting & UI
python -m src.report.cohort_report                 # regenerate HTML/PDF report
./run_dashboard.sh                                 # Streamlit dashboard

pytest                                             # test suite
```

`OPENAI_API_KEY` is read from `.env` (via `python-dotenv`). **If unset, the LLM layer silently falls back to a deterministic offline mock** — useful for tests, but such a run contains no real LLM output (check for the mock warning).

---

## Limitations

- Small scale (56-variant cohort, 70-variant external benchmark) — accuracy differences are not statistically powered; single primary model (gpt-4o-mini).
- Citation support (Type II faithfulness) is measured only approximately (NLI lower bound 0.444); the gate guarantees that citations exist in the bundle, not that they support the claim.
- The Deterministic mode is a deliberately **simplified** rule. The VICC rule arm follows the SOP text where open data allow, but several criteria (OS1, OM4, OP2, SBP2) cannot be evaluated from open data and are left unassigned, OP1/SBP1 rest on a single predictor, and population frequencies are global rather than per continent. It is not a validated clinical engine.
- The abstention contract accepts a computational prior as variant-specific evidence, so a driver call can survive the loss of all curated clinical evidence (input-context ablation).
- LLM parametric leakage is quantified (by the no-retrieval floor) but not controlled.
- The provisional discordance adjudication still requires sign-off by a board-certified molecular pathologist before any biological correctness claim.
- The dashboard and report are research/educational demonstrators, not validated clinical tools.

---

## Related work

- **RAG for variant annotation** — Lu & Cosgun (2025, *Bioinform Adv*) integrated ~190M variant annotations into GPT-4o via RAG/fine-tuning, reporting high field-level annotation accuracy.
- **LLM over-classification** — Lin et al. (2025, *npj Precis Oncol*) benchmarked GPT-4o/Llama 3.1/Qwen 2.5 and reported systematic over-classification toward higher evidence levels (the same parametric over-calling observed here).
- **Citation faithfulness & medical RAG** — ALCE (Gao et al.) formalised citation precision/recall evaluation; MedRAG/MIRAGE (Xiong et al.) established retrieval as a partial hallucination mitigation in medical QA.
- **Established interpretation platforms** — OncoKB, CIViC, COSMIC, PCGR — treated here as prior art the system must remain compatible with, not baselines it claims to beat.
- **Reported head-to-head comparators (rule arm only):** **OncoVI** and **HemaGuide**'s molecular mode (native VICC-oncogenicity axis; both higher than our rule arm in point estimate, McNemar p = 0.087 each) and **CancerVar** (AMP/ASCO/CAP actionability axis — a **cross-axis** comparison read strictly as an error-profile contrast, not an accuracy benchmark). **Cancer Genome Interpreter (CGI)** was considered as a near-axis comparator but **deferred** — its per-variant predictions require a registration-gated token unavailable in scope; extending the head-to-head to CGI is future work.

Full references are in the manuscript (`docs/manuscript/preprint.md`).

---

## License & attribution

MIT License. © 2026 **Ka-Kyung Kim** (GitHub: [kakyungkim](https://github.com/kakyungkim)).

Independent research project. Public data sources retain their own licenses (CIViC CC0; cBioPortal/TCGA, DGIdb, AlphaMissense, ClinicalTrials.gov per their respective terms).
