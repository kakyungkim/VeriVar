<!-- DRAFT — HOLD. Publish only after company/IP review + the paper goes public; then move to the blog repo _posts/en/. Do NOT push now. date/permalink finalized at publish time. -->
---
layout: single
title: "When an LLM Invents Its Sources — Measuring Faithfulness in Numbers, and Guaranteeing 0%"
date: 2026-06-14 09:00:00 +0900
lang: en
ref: faithfulness-by-the-numbers
featured: true
categories: [AI & Tooling]
tags: [LLM, Faithfulness, RAG, Variant Interpretation, Benchmark, Building in Public]
permalink: /en/2026/06/14/faithfulness-by-the-numbers/
excerpt: "The numbers from building a somatic-variant interpretation pipeline. Citation fabrication pinned from 46.4% with no retrieval → 18.9% with RAG → 0% with a gate, matching a SOTA rule engine on accuracy while failing more safely."
---

{% include lang-switch.html %}

Hi — I'm Ka-Kyung, a bioinformatics researcher working across clinical data, genomics, and machine learning.

This is a story told through the numbers I actually got from building a somatic-variant interpretation pipeline. It's not about "how much did accuracy go up" — it's about "did I make the output trustworthy line by line." If you'd rather see the concepts first, the companion post — [Honest Beats Correct](https://kakyungkim.github.io/en/2026/06/14/faithful-over-correct/) <!-- TODO(at publish): confirm faithful-over-correct permalink --> — is the gentler read.

> Research/education demo only — not for clinical use. All data is public TCGA and public knowledge bases.

In a molecular tumor board, the classification of a single variant directs or withholds a targeted therapy. So every sentence that goes into the report has to be traceable to a primary source. But hand variant interpretation to an LLM and two things are frightening. **(1) It invents the evidence (PMIDs, DB IDs) convincingly. (2) It returns "the textbook answer it memorized because the variant is famous" instead of the evidence you actually gave it.**

The question for this work wasn't "can I make the LLM smarter?" It was **"can I make the LLM honest — and can I prove it in numbers?"** Here's what I got.

## 1. Ask it without evidence — 46.4% fabricate

I gave the same gpt-4o-mini 56 variants to interpret **with the evidence bundle removed.** On **26 of them (46.4%, 95% CI 33.9–58.9%)** it produced citations that don't exist — placeholders like `PMID: 12345678`, unsupported DB tokens. The confidence interval doesn't include 0, so this isn't chance; it's **structural behavior.** A single fabricated reference in a clinical report is a patient-safety and legal harm — the sentence looks supported but can't be verified.

## 2. Add RAG — under half, but the real story is what the 18.9% is

I attached retrieved evidence and ran it again. Across 56 variants there were **106 citations total.**

- **Fully fabricated citations not in the bundle: 0.**
- But of the 106, **20 (18.9%)** named only the **source category** — like `"AlphaMissense"` — without the specific variant identifier (`AlphaMissense:7:140481402C>T`).

What mattered was not stopping there but interrogating what that 18.9% actually *was.* A naive match first reported "52.8% hallucination," which turned out to be a **format mismatch** — `CIViC:EID6003` vs `EID6003`. After normalization it dropped to 18.9%, and even that 18.9% was **not fabrication but imprecision: right source, didn't pin the item ID.**

> **Lesson 1 — honesty in measurement.** Stopping at "52.8% hallucination!" would have been the wrong conclusion. When a number falls out, you have to chase down what that number *is.* Fabrication and source-imprecision are clinically very different problems.

## 3. The gate — not measurement, guarantee

How do you get the remaining 18.9% to 0? Not by **measuring and reducing** — by **structurally blocking.** The faithfulness gate (`src/classify/faithfulness.py`) enforces four things.

1. Citations not in the bundle are **dropped.**
2. Empty evidence bundle → **abstain** (VUS).
3. A cited item whose direction contradicts the call → **abstain.**
4. A directional call with no precisely-pinned evidence → **abstain.**

Result: enforcing exact identifier matching takes 18.9% → **0%.** The point is that this isn't "good on average" — it's a **worst-case guarantee.** In an ablation that deliberately injected three violation types into 44 of 56 cases, post-gate hallucination recovered 0.452 → **0.0** and abstention recall 0.40 → **1.0.**

> So both paths reach 0% — RAG trims 46.4% → 18.9%, and **the gate guarantees the rest to 0.** The rule-based (deterministic) path never lets the LLM touch classification at all, so it's **structurally 0%.**

## 4. Small open models agree once they're given evidence

An answer to the doubt "don't you need a big model for this?" I ran three small open models (Llama 3.1 8B, Qwen 2.5 3B, Llama 3.2 3B) as **independent graders over the same fixed evidence bundle** (56 variants).

- Mean inter-model agreement **0.929**
- Unanimous on **44/56 (78.6%)**
- Complete disagreement on **0** cases
- Majority-vote abstention rate 25.0% (close to gpt-4o-mini alone at 32.1%)

The 12 cases of disagreement clustered on **borderline variants** like ALK and PTEN — the ones where abstaining is the right answer anyway. In other words, **disagreement between models can itself be used as a "don't know / hold" signal.** Small open models too weak to *drive* the tool are consistent enough to *grade* against fixed evidence. (This is a PoC stage — an NLI attribution gate, larger judges, and risk-coverage curves are future work.)

## 5. The rule engine: tied with SOTA on accuracy, but fails more safely

I built a citable, ClinGen/CGC/VICC point-based rule engine (`src/classify/vicc_rules.py`) from public data only (cancerhotspots, CIViC, UniProt, gnomAD, MaveDB, AlphaMissense). Every firing criterion leaves a citable record (code, score, evidence sentence, source) — the axis that raises **auditability.**

On the Horak-70 expert gold set: **3-class accuracy 0.843, specificity 0.973, AUROC 0.906.** It far outruns our own simple rules (0.557) and the generative mode (0.600). Then I ran a head-to-head against the strongest open engine, **OncoVI**, using its own published predictions on the same 69 variants.

| | Ours | OncoVI |
|---|---|---|
| Accuracy | 0.841 | 0.797 |
| Specificity | **0.972** | 0.806 |
| Sensitivity | 0.697 | 0.909 |

The accuracy difference is not statistically significant (McNemar p=0.66). So I **do not claim accuracy superiority.** The real difference is in the **character of the errors.** Of the 21 disagreements, our engine made **9 errors — every one an honest abstention** on a truly oncogenic variant, with not a single over-call. OncoVI made **12** — of which **9 were confident over-calls** on gold-VUS variants (6 called Oncogenic, e.g. KRAS S65I and PIK3CA H1065Y/E418K; 3 called Benign) plus 3 misses. The counts aren't symmetric, and neither is the risk: a false "oncogenic" can trigger an inappropriate targeted therapy, while an honest VUS abstention is **declared uncertainty.** At equal accuracy, an engine that says "I don't know" when it doesn't is a safer tool than one that's confidently wrong.

> **Lesson 2 — "how it's wrong" beats "how often it's right."** In the clinic, at the same error rate, over-calling and honest abstention carry different risk. That difference is invisible in a single accuracy number.

## 6. The shadow of honesty — and why it isn't a bug

All this honesty has a cost. On an independent ClinVar holdout (n=458), oncogenic-detection **specificity 0.967, sensitivity 0.537**, AUROC 0.902 (the same as Horak's 0.906). Sensitivity is low. Why?

Diagnosing it: of 57 missed oncogenics, **53 fired no strong evidence code at all**, and **34 stalled within 2 points of the threshold.** Conversely, 93.9% of the ones it got right carried a strong, citable code. The engine **says "oncogenic" only when there's strong, auditable evidence, and otherwise abstains.** The low sensitivity isn't a reasoning failure — it's **the faithfulness design made visible.**

There's a limit worth stating honestly too. On this ClinVar set the engine **calls no benign at all** (benign recall 0, balanced 3-class accuracy 0.505). VICC requires population-frequency evidence for Benign, and rare benigns don't have it, so it correctly abstains to VUS. That's why the 0.902 AUROC should be read only as **"oncogenic vs. the rest" discrimination**, not as a 3-class panacea. Writing down a limit like this rather than hiding it is the project's consistent stance.

## 7. The last lesson — honest reporting isn't self-deprecation

Writing the manuscript, I caught myself repeating the defensive phrase "non-inferior, not superior" more than six times. Avoiding a superiority claim the statistics don't support is right. But it's a problem when that hedge starts dragging down even the things that genuinely did win.

So I split it into two tracks.

- **The generative (LLM) path** — accuracy is a true draw (p=1.0). Keep "non-inferior," honestly. **The contribution is faithfulness.**
- **The rule engine** — +0.24–0.29 over its own baseline, specificity 0.973 vs 0.806, AUROC 0.906. This I write down **as an achievement, plainly.** Only the *accuracy superiority* over OncoVI (p=0.66) stays as "equivalent."

> **Lesson 3.** Honesty isn't saying "none of it is a big deal." It's putting each thing exactly where it belongs — **a win as a win, a draw as a draw, a loss as a loss.**

## One-paragraph summary

In LLM variant interpretation, citation fabrication went from 46.4% with no retrieval → 18.9% with RAG (mostly source-imprecision, not fabrication) → **0% (a structural guarantee)** with the gate. Three small open models agreed 92.9% over fixed evidence, letting disagreement serve as a hold signal. A citable rule engine built from public data alone matched the SOTA (OncoVI) on accuracy (0.841 vs 0.797) while showing **far higher specificity (0.973 vs 0.806) and safer error character** (honest abstention instead of over-calling). The core claim is not "more accurate" but **"auditable line by line, and it says 'I don't know' when it doesn't"** — a precondition that comes before accuracy in clinical decision support.

The gentler, concept-first companion is [Honest Beats Correct](https://kakyungkim.github.io/en/2026/06/14/faithful-over-correct/). <!-- TODO(at publish): replace with faithful-over-correct permalink --> The way I built this research alongside a team of AI agents is in [the research-harness post](https://kakyungkim.github.io/en/2026/06/14/research-agent-harness/). <!-- TODO(at publish): confirm research-agent-harness permalink -->

---

*Reproduce: `scripts/run_faithfulness_real.py` (46.4%→0%), `scripts/run_multimodel_faithfulness.py` (ensemble), `scripts/run_oncovi_headtohead.py` (head-to-head), `scripts/run_clinvar_vicc.py` (independent generalization), `scripts/run_horak_vicc.py` (0.843). Result JSON in `data/outputs/` and `data/benchmark/`.*
