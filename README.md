# LLM_Variant_Pipeline
Dual-mode (LLM + rule-based) variant interpretation pipeline for somatic mutations
=======
# 🧬 LLM-Assisted Somatic Variant Interpretation Pipeline (TCGA, Single Sample)

**GitHub repo description (1-liner)**

> A research-grade demo pipeline for single-sample somatic variant interpretation using dual-mode LLM and rule-based tiering on public TCGA data.

---

## Overview

This repository demonstrates a **research-focused somatic variant interpretation pipeline**
using **public TCGA single-sample VCF data**.

The pipeline integrates:

* Lightweight VCF parsing
* Minimal gene-level annotation
* **Dual-mode variant tiering**

  * **Mode A**: LLM-driven candidate tier assignment
  * **Mode B**: Rule-based tier fixing + LLM explanation
* Structured JSON outputs and comparison tables

⚠️ **Important**
This pipeline is intended for **research, education, and demonstration purposes only**.
All tier assignments are **candidate-level interpretations** and **not suitable for clinical decision making**.

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

## Dual-Mode Tiering Strategy

### Mode A — LLM-driven candidate tiering

* The LLM **assigns candidate tiers directly**
* Uses conditional, non-clinical language
* Optimized for:

  * Exploratory analysis
  * Hypothesis generation
  * Signal discovery

### Mode B — Rule-based pre-tiering + LLM explanation

* Candidate tier is **pre-assigned by deterministic rules**
* LLM **must not change the tier**
* Optimized for:

  * Reproducibility
  * Review safety
  * Baseline comparison

> **Design principle**
> Rule-based tiering is **intentionally minimal and conservative**.
> It is not intended to reproduce full clinical guideline logic.

---

## Candidate Tier Definitions

| Candidate Tier      | Description                      |
| ------------------- | -------------------------------- |
| `candidate_Tier_I`  | Strong known oncogenic relevance |
| `candidate_Tier_II` | Moderate or emerging evidence    |
| `uncertain`         | Insufficient or unclear evidence |

---

## Conceptual Mapping to AMP/ASCO/CAP Guidelines

> This mapping is **conceptual only** and not guideline-compliant.

| Candidate Tier (this pipeline) | Approximate AMP Tier |
| ------------------------------ | -------------------- |
| `candidate_Tier_I`             | AMP Tier I / II      |
| `candidate_Tier_II`            | AMP Tier III         |
| `uncertain`                    | AMP Tier IV          |

**Rationale**

* AMP guidelines require population-level evidence, drug associations, and clinical validation
* This pipeline operates on **single-sample public data only**
* Therefore, tiers are framed as **candidate signals**, not definitive classifications

---

## Dual-Mode Comparison Output

The pipeline generates a **variant-level comparison table**:

| Column                    | Description                             |
| ------------------------- | --------------------------------------- |
| `variant`                 | Genomic coordinate and allele           |
| `variant_type`            | SNV/MNV or INDEL                        |
| `LLM_candidate_tier`      | Tier assigned by LLM                    |
| `Rule_candidate_tier`     | Tier fixed by rules                     |
| `tier_match`              | Whether both modes agree                |
| `LLM_tier_basis`          | Evidence cited by LLM                   |
| `Rule_tier_basis`         | Explanation under fixed tier            |
| `LLM_requires_validation` | Whether additional validation is needed |

This enables **explicit inspection of concordant vs discordant interpretations**.

---

## Mini Case Study: Discordant Variant Interpretation

### Case: *DDX11L1* variants

**Observation**

* Rule-based mode assigns `candidate_Tier_II`
* LLM-driven mode assigns `uncertain`

**Why this happens**

* Rule-based logic uses **gene presence as a weak proxy** for relevance
* *DDX11L1* is a **pseudogene / uncharacterized locus**
* LLM recognizes the **lack of oncogenic evidence** and downgrades confidence

**Interpretation**

* The discordance highlights:

  * Limitations of naive rule-based tiering
  * The LLM’s ability to reason about biological plausibility
* Such cases are **flagged for review**, not automatically accepted

> **Takeaway**
> Discordant cases are not failures — they are the *primary analytical signal* produced by this pipeline.

---

## Outputs

* Structured JSON interpretation per sample
* Variant-level dual-mode comparison table (`CSV`)
* Explicit annotation of:

  * Evidence strength
  * Reasoning basis
  * Validation requirements

---

## Execution Environment

Versions are **logged at runtime** for reproducibility.

| Package          | Version |
| ---------------- | ------- |
| Python           | 3.x     |
| langchain        | 0.2.x   |
| langchain-core   | 0.2.x   |
| langchain-openai | 0.1.x   |
| pydantic         | 2.x     |
| pandas           | 2.x     |

---

## Limitations

* Single-sample analysis only
* No cohort frequency or recurrence analysis
* No drug-actionability or clinical outcome linkage
* Rule-based tiering is intentionally simplified

---

## Future Extensions

* Multi-sample / cohort-level analysis
* COSMIC / ClinVar / OncoKB integration
* VAF-based filtering
* Formal AMP/ASCO/CAP guideline mapping
* Automated report (HTML / PDF) generation

---

## Intended Use

This repository is designed for:

* Research prototyping
* Methodological exploration
* LLM behavior analysis in genomics
* Portfolio / demonstration projects

**Not for clinical diagnostics or treatment decisions.**

## License & Attribution

This project is licensed under the MIT License.  
Copyright (c) 2026 [Your Name / GitHub ID].

Please attribute the original work to Ka-Kyung Kim (GitHub: [kakyungkim](https://github.com/kakyungkim)) when using, referencing, or adapting this project.  
GitHub commit history also serves as a timestamped record of original authorship.
