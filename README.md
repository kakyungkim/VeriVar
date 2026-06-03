# 🧬 LLM-Assisted Somatic Variant Interpretation Pipeline

**Dual-mode (LLM + rule-based) variant interpretation pipeline for somatic mutations**

---

## 🔬 Background & Motivation

This project originates from **rule-based variant interpretation work conducted at a previous employer**, where somatic variant tiering was performed using deterministic clinical guidelines (AMP/ASCO/CAP). While rule-based systems offer reproducibility and auditability, they are inherently limited in handling:

- Variants in poorly characterized or emerging genes
- Conflicting evidence across databases
- Context-dependent biological reasoning

This pipeline is an exploratory extension of that real-world experience — asking the question:
**"Where can LLMs add reasoning value beyond what rules can do?"**

Due to the absence of proprietary clinical data, this demo uses **public TCGA single-sample VCF data** as a minimal proof-of-concept dataset. The architecture is designed to scale to real clinical cohorts.

---

## Overview

A research-grade demo pipeline for single-sample somatic variant interpretation using **dual-mode LLM and rule-based tiering** on public TCGA data.

The pipeline integrates:
- Lightweight VCF parsing
- Minimal gene-level annotation
- **Dual-mode variant tiering**
  - **Mode A**: LLM-driven candidate tier assignment
  - **Mode B**: Rule-based tier fixing + LLM explanation
- Structured JSON outputs and comparison tables

> ⚠️ For research, education, and demonstration purposes only.
> Not suitable for clinical decision making.

---

## Pipeline Architecture

```
VCF (SNV / INDEL)
        │
        ▼
Lightweight Parsing
        │
        ▼
Candidate Variant Selection
        │
        ├──────────────┐
        ▼              ▼
 Mode A (LLM)      Mode B (Rule)
 Tier + Evidence   Tier fixed
        │              │
        └───────┬──────┘
                ▼
        Dual-mode Comparison
                │
                ▼
        Structured JSON / CSV
```

---

## Dual-Mode Design Rationale

### Why dual-mode?

In clinical practice, rule-based and LLM-based approaches serve different purposes:

| | Rule-based (Mode B) | LLM-driven (Mode A) |
|---|---|---|
| **Strength** | Reproducibility, auditability | Contextual reasoning, biological plausibility |
| **Weakness** | Rigid, misses novel variants | Hallucination risk, non-deterministic |
| **Best for** | Regulatory/clinical reporting | Exploratory analysis, hypothesis generation |

Discordant cases between the two modes are treated as **primary analytical signals**, not failures.

### Mode A — LLM-driven candidate tiering
- LLM assigns candidate tiers directly
- Optimized for exploratory analysis and signal discovery

### Mode B — Rule-based pre-tiering + LLM explanation
- Candidate tier is pre-assigned by deterministic rules
- LLM provides explanation only; tier is fixed
- Optimized for reproducibility and review safety

---

## Classification Standards (two axes)

The pipeline classifies each variant on two complementary international standards
for **somatic** variants (the ad-hoc `candidate_Tier_*` vocabulary has been
retired):

**Axis 1 — Oncogenicity** (ClinGen/CGC/VICC 2022, Horak et al.)

| Class | Meaning |
|---|---|
| `Oncogenic` / `Likely Oncogenic` | Evidence supports an oncogenic role |
| `VUS` | Variant of Uncertain Significance |
| `Likely Benign` / `Benign` | Evidence supports no oncogenic role |

**Axis 2 — Clinical actionability tier** (AMP/ASCO/CAP 2017, Li et al.)

| Tier | Meaning | Level (Tier I/II) |
|---|---|---|
| `Tier I` | Strong clinical significance | A–D evidence level |
| `Tier II` | Potential clinical significance | A–D evidence level |
| `Tier III` | Unknown clinical significance (VUS) | — |
| `Tier IV` | Benign / likely benign | — |

> ACMG/AMP 2015 is the *germline* standard and is intentionally not used; its
> somatic analogue is the VICC oncogenicity scale above. Tumor-type context
> matters: the same variant can map to different tiers across cancers.

---

## Key Finding: Discordant Variant Interpretation

### Case: *DDX11L1* variants

- **Rule-based (Mode B)**: `Likely Oncogenic` / `Tier III` (gene presence as a weak proxy)
- **LLM-driven (Mode A)**: `VUS` / `Tier III` — no supporting evidence is retrieved for this
  pseudogene, so the model **abstains** from an oncogenic call rather than fabricating one

**Takeaway:** with citation-grounded retrieval, the absence of evidence drives the
LLM to a VUS call, surfacing a discordance that naive gene-presence rules miss.
Such discordances are flagged for review.

---

## Execution Environment

| Package | Version |
|---|---|
| Python | 3.x |
| langchain | 0.2.x |
| langchain-openai | 0.1.x |
| pydantic | 2.x |
| pandas | 2.x |

---

## 🔭 Future Extensions

### Short-term
- **COSMIC / ClinVar / OncoKB integration**: Replace minimal gene-level annotation with structured DB queries via RAG
- **VAF-based filtering**: Incorporate variant allele frequency thresholds
- **Multi-sample / cohort-level analysis**: Extend from single-sample to recurrence-aware tiering

### Mid-term
- **Korean population-specific variant database integration**: e.g., KoVariome, KRGDB — addressing the ethnic bias noted in current clinical LLM literature
- **Formal AMP/ASCO/CAP guideline mapping**: Move from conceptual to guideline-compliant tiering
- **Automated HTML/PDF report generation**: Clinical-grade output formatting

### Long-term
- **Omics-context integration**: Incorporate RNA-seq expression data and scRNA-seq tumor microenvironment context for variant prioritization
- **Closed-loop experimental design**: Connect variant interpretation outputs to next-step experimental recommendations (target validation, drug sensitivity)
- **Fine-tuning vs RAG evaluation**: Benchmark approaches for domain knowledge injection (cf. Lin et al. 2025, NPJ Precis Oncol)

---

## 📚 Related Work

This project is situated within a rapidly growing field:

- **RAG for variant annotation**: GPT-4o + RAG integration of 190 million variant annotations demonstrated that RAG outperforms fine-tuning for factual knowledge injection in genomics, achieving higher accuracy at lower cost (Lin et al., *Bioinformatics Advances*, 2025)
- **LLM + Rule hybrid**: Just-DNA-Seq demonstrated how LLMs can be paired with rule-based genomic annotation engines to support variant interpretation workflows
- **Clinical LLM benchmarking**: Hamilton et al. (2024) compared GPT-4 vs GPT-3.5 on NGS reports in oncogene-driven NSCLC, showing GPT-4 produced more guideline-compliant treatment suggestions
- **Ethnic bias in genomic LLMs**: Leveraging patient genetic ethnicity to focus LLMs on population-specific variant knowledge is an important direction to address historic bias derived primarily from European populations

---

## Limitations

- Single-sample analysis only
- No cohort frequency or recurrence analysis
- No drug-actionability or clinical outcome linkage
- Rule-based tiering is intentionally simplified
- Demo dataset (TCGA public VCF) does not reflect clinical sequencing quality

---

## Intended Use

- Research prototyping
- Methodological exploration
- LLM behavior analysis in genomics
- Portfolio / demonstration projects

**Not for clinical diagnostics or treatment decisions.**

---

## License & Attribution

MIT License. Copyright (c) 2026.
Please attribute to Ka-Kyung Kim (GitHub: [kakyungkim](https://github.com/kakyungkim)).
