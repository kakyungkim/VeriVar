# 🧬 LLM-Assisted Somatic Variant Interpretation Pipeline

**Citation-grounded retrieval for faithful, auditable LLM somatic variant interpretation — dual-mode (LLM + rule), two-axis (oncogenicity + clinical tier).**

> ⚠️ **Research, education, and demonstration only. NOT for clinical diagnostics or treatment decisions.**
> Built and evaluated entirely on **public** data and knowledge bases.

---

## Motivation

Somatic variant interpretation — judging whether a tumour mutation is oncogenic and clinically actionable — is a rate-limiting, audit-critical step in precision oncology. Rule-based engines are reproducible and auditable but rigid: their coverage of rare or under-curated variants is bounded by their databases, and they neither read free-text evidence on demand nor produce natural-language justifications.

Large language models read evidence fluently and emit structured prose, but two failure modes bar naïve clinical use:

- **Hallucinated citations** — an LLM readily emits plausible but non-existent PMIDs / database IDs to "support" a call.
- **Parametric leakage** — famous drivers (e.g. BRAF V600E) may be answered from pretraining memory rather than the supplied evidence, inflating apparent accuracy and producing confident over-calls on benign look-alikes.

This project asks a focused question: **can retrieval grounding make LLM variant interpretation faithful and auditable — and is any accuracy effect genuine or a leakage artifact?** The headline result is that faithfulness and auditability can be guaranteed *by construction*; accuracy is reported with deliberate statistical discipline (non-inferior, not superior, for the generative arm).

---

## What the pipeline does

For each variant, the system assembles a **citable evidence bundle** via hybrid retrieval, then classifies the variant on **two international standards** under a **faithfulness contract**, running multiple interpretation arms on every variant for comparison.

### Two-axis classification

| Axis | Standard | Labels |
|---|---|---|
| **Oncogenicity** | ClinGen/CGC/VICC 2022 (Horak et al.) | Oncogenic · Likely Oncogenic · VUS · Likely Benign · Benign |
| **Clinical tier** | AMP/ASCO/CAP 2017 (Li et al.) | Tier I–IV (evidence levels A–D for Tiers I/II) |

> ACMG/AMP 2015 is the *germline* standard and is intentionally **not** used; its somatic analogue is the VICC oncogenicity scale. Tumour-type context matters — the same variant can map to different tiers across cancers.

### Interpretation arms

- **Generative mode (Mode A)** — the LLM assigns the labels itself, grounded on the evidence bundle, with self-consistency voting (n = 3) and an agentic adversarial verifier. For exploratory interpretation and rare/under-curated variants.
- **Deterministic mode (Mode B)** — a transparent, direction-aware rule fixes the label; the LLM writes only the human-readable rationale. For reproducibility and review safety (identical output every run).
- **Citable VICC point-based rule arm** — a deliberately simplified, direction-aware re-implementation in the tradition of curated rule engines, used as a strong honest baseline.
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

Evaluated with leakage-free faithfulness metrics, an external gold standard, bootstrap 95% CIs, and exact McNemar tests. Primary model **gpt-4o-mini** (a conservative capability floor); replicated on **gpt-4o**.

- **Faithfulness (the headline, statistically robust):** with retrieval, citation fabrication **0%** vs **46.4%** (95% CI 33.9–58.9) without; citation grounding **1.0**, directional faithfulness **1.0**, abstention recall **1.0**.
- **Suppressed parametric over-calling:** retrieval reclassified **12 of 56** confidently over-called variants (21.4%) to evidence-grounded VUS (behavioural change; per-variant correctness awaits expert adjudication).
- **Accuracy — honest and disciplined:** the **generative arm** is *non-inferior* to both baselines on Horak-70 (3-class 0.600 with retrieval vs 0.586 without vs 0.557 rule; McNemar p = 1.0 / 0.61) — so **faithfulness, not accuracy, is its contribution.** The **citable VICC rule arm** reaches 3-class accuracy **0.843** (specificity 0.973, AUROC 0.906) and matches the strongest open engine (OncoVI) head-to-head at markedly higher specificity, trading confident over-calls for honest abstentions.
- **Leakage controls all pass:** temporal holdout, leave-own-evidence-out (LOVO), second model (gpt-4o), and embedding ablation leave generative-arm accuracy statistically unchanged — the behaviour is not a retrieval-corpus or single-model artifact.

> Accuracy differences at n = 70 are **not** significant — no accuracy-superiority claim is made for the generative arm. See `data/outputs/stats_report.json`.

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
| `docs/` | Study summary, bioRxiv manuscript + figures, blog/talk material |

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

- Small scale (56-variant cohort, 70-variant external benchmark) — accuracy differences are not statistically powered.
- The Deterministic and VICC rule arms are deliberately **simplified** re-implementations, not guideline-compliant clinical engines.
- LLM parametric leakage is quantified (by the no-RAG floor) but not fully eliminated.
- The provisional discordance adjudication still requires sign-off by a board-certified molecular pathologist before any biological correctness claim.
- The dashboard and report are research/educational demonstrators, not validated clinical tools.

---

## Related work

- **RAG for variant annotation** — Lu & Cosgun (2025, *Bioinform Adv*) integrated ~190M variant annotations into GPT-4o via RAG/fine-tuning, reporting high field-level annotation accuracy.
- **LLM over-classification** — Lin et al. (2025, *npj Precis Oncol*) benchmarked GPT-4o/Llama 3.1/Qwen 2.5 and reported systematic over-classification toward higher evidence levels (the same parametric over-calling observed here).
- **Citation faithfulness & medical RAG** — ALCE (Gao et al.) formalised citation precision/recall evaluation; MedRAG/MIRAGE (Xiong et al.) established retrieval as a partial hallucination mitigation in medical QA.
- **Established interpretation platforms** — OncoKB, CIViC, COSMIC, CancerVar, Cancer Genome Interpreter, PCGR, OncoVI — treated here as prior art the system must remain compatible with, not baselines it claims to beat.

Full references are in the manuscript (`docs/manuscript/preprint.md`).

---

## License & attribution

MIT License. © 2026 **Ka-Kyung Kim** (GitHub: [kakyungkim](https://github.com/kakyungkim)).

Independent research project. Public data sources retain their own licenses (CIViC CC0; cBioPortal/TCGA, DGIdb, AlphaMissense, ClinicalTrials.gov per their respective terms).
