<!-- DRAFT — HOLD. Publish only after company/IP review + the paper goes public; then move to the blog repo _posts/en/. Do NOT push now. date/permalink finalized at publish time. -->
---
layout: single
title: "Honest Beats Correct — What Actually Matters When an LLM Reads a Cancer Variant"
date: 2026-06-14 09:00:00 +0900
lang: en
ref: faithful-over-correct
featured: true
categories: [AI & Tooling]
tags: [LLM, Faithfulness, RAG, Variant Interpretation, Building in Public]
permalink: /en/2026/06/14/faithful-over-correct/
excerpt: "In the clinic, the scariest LLM failure isn't being wrong — it's being wrong while inventing a citation convincing enough to fool you. So we treated 'honesty' as a first-class metric alongside accuracy."
---

{% include lang-switch.html %}

Hi — I'm Ka-Kyung, a bioinformatics researcher working across clinical data, genomics, and machine learning.

This is the story of building a somatic-variant interpretation pipeline and obsessing not over making the LLM *smarter*, but over making it *honest*. If you want the numbers and methods in depth, the companion post — [Faithfulness by the Numbers](https://kakyungkim.github.io/en/2026/06/14/faithfulness-by-the-numbers/) <!-- TODO(at publish): confirm faithfulness-by-the-numbers permalink --> — walks the same idea through the measurements.

> Research/education demo only — not for clinical use. All data is public TCGA and public knowledge bases (CIViC, DGIdb, AlphaMissense, ClinicalTrials.gov, and others).

## The brilliant med student you can't trust

You hand a cancer patient's single gene variant to a well-trained med student (the LLM) and ask: "Does this variant cause cancer?"

The student answers, confidently: **"Yes, it's oncogenic. It's in *Smith 2019, PMID 12345678*."**

Sounds solid. Then you look up that PMID — and it **doesn't exist.** It was invented.

That's the scariest way an LLM fails in the clinic. The problem isn't being wrong; it's being wrong *and* manufacturing a citation convincing enough that a human believes it. So our work treated "how accurate is it?" as only half the question. The other half — maybe the more important half — was **"how faithful is it?"**

## Accuracy and honesty are two different axes

| | The question | Exam analogy |
|---|---|---|
| **Accuracy** | Was the answer *right?* | Did you get the right answer? |
| **Faithfulness** | Did you answer *from the evidence*, without making it up? | Are the footnotes real, and do they point the same way as the conclusion? |
| **Auditability** | Can a human *trace the reasoning line by line?* | Can the grader open each cited source and check it? |

The key thing is that these two are **independent**.

- 🟥 **Right but unfaithful** = "correct answer, fabricated source" → in the clinic this is the *more dangerous* outcome (it was right by luck; next time it'll be wrong and just as insistent).
- 🟩 **Wrong but faithful** = "no evidence, so it honestly abstained as VUS (uncertain)" → a *safe* failure.

For a physician to put their *signature* on an LLM's call in a molecular tumor board, they have to be able to open each line of evidence and push back on it. So auditability isn't a nice-to-have — it's a **precondition for deployment.**

## Measuring honesty with four numbers

We don't measure "honesty" as a vibe. We measure it as **four metrics that need no external answer key** (which also means no risk of answer leakage).

1. **Hallucination rate** — the fraction of citations to evidence that was never retrieved. Should be **0** (nothing invented).
2. **Citation rate** — when evidence exists, the fraction of calls that actually cite ≥1 item. Should be **1**.
3. **Directional faithfulness** — do the cited items point the *same direction* as the conclusion? (Catches "this is cancer-causing" backed only by *benign* evidence.)
4. **Abstention accuracy** — when there's no evidence at all, the fraction that honestly abstains as VUS. (Catches empty confidence.)

Together these four cover all three angles the literature talks about — **groundedness, attribution, and faithfulness.**

## Not "we hope it's honest" — "we force it to be"

You can prompt the model: "only cite retrieved evidence." It helps. But it never reaches **0.** The LLM keeps inventing.

So we put a **deterministic gate** behind the LLM. Whatever it says, the output passes through four checkpoints before it ships, and gets corrected by force.

1. **Source verification** — any citation not in the retrieved bundle is dropped immediately → hallucination is **structurally 0.**
2. **Forced abstention** — no evidence at all → forced to VUS.
3. **Directional consistency** — a citation that contradicts the call → abstain.
4. **Forced grounding** — evidence exists but nothing was cited → abstain.

And we keep an **audit trail of which checkpoint fired** — so even the corrections are traceable.

### Does it actually work? (in numbers)

We injected errors on purpose, simulating a genuinely hallucinating LLM, then ran the output through the gate:

| Metric | Before the gate (broken model) | After the gate |
|---|---|---|
| Hallucination rate | 0.45 | **0.0** |
| Directional faithfulness | 0.48 | **1.0** |
| Abstention accuracy | 0.40 | **1.0** |

44 of 56 cases were auto-corrected. The takeaway: no matter how bad the model upstream is, the honesty metrics of the shipped output snap back to their ideal values. That's what "faithful by construction" actually means.

## The rule engine is just as honest

This isn't only about the LLM. Our deterministic rule engine attaches a citable source (cancerhotspots, UniProt, gnomAD, MaveDB, CIViC) to *every* decision criterion. On an independent ClinVar set, **93.9% of its cancer-causing calls came with strong, citable evidence**; the rest abstained. Specificity 0.967 — it **almost never bluffs.**

## Is any of this a new claim?

Honestly: **we did not invent the concept of "faithfulness."** It's already a hot area in NLP (RAGAS, ALCE, MedCite, and more). Claim you invented it and a reviewer will spot it instantly.

What we *can* legitimately claim is **not the concept, but the application and the guarantee:**

1. The **first time faithfulness is reported as a first-class metric, on par with accuracy**, for somatic-variant oncogenicity/tier interpretation (a field that has only looked at accuracy).
2. **A structural guarantee, not just a measurement** (the gate = 0% hallucination even in the worst case).
3. An evaluation **with leakage controls** (temporal split, self-evidence exclusion).

The sharpest contrast: a recent autonomous oncology AI agent (Ferber et al., Nature Cancer 2025) reaches 91% conclusion accuracy but only **75.5% guideline-citation accuracy** — meaning roughly one cited reference in four can't be trusted. That's fatal in a clinical report. That gap is exactly what we're trying to close.

## One-line summary

> **"It can say it's uncertain — it must never say something it can't stand behind."**
> In the clinic, a system that knows when to honestly abstain is safer than one that's occasionally right but nobody can verify.

If you want to follow the same story through the actual measurements (46.4% with no retrieval → 18.9% with RAG → 0% with the gate, plus the head-to-head against a SOTA rule engine), read the companion post, [Faithfulness by the Numbers](https://kakyungkim.github.io/en/2026/06/14/faithfulness-by-the-numbers/). <!-- TODO(at publish): replace with faithfulness-by-the-numbers permalink --> And the way I built this research *alongside a team of AI agents* is in [the research-harness post](https://kakyungkim.github.io/en/2026/06/14/research-agent-harness/) — where, fittingly, the AI itself refused to fabricate missing data and stopped, holding to the very faithfulness principle this project studies. <!-- TODO(at publish): confirm research-agent-harness permalink -->

---

*This post is a conceptual write-up from the research process. Research/education demo only, not for clinical use; all data is public.*
