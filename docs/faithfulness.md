# Faithfulness & auditability — concepts, metrics, and how we raise them

This is the conceptual companion to the accuracy work in [`vicc_rule_arm.md`](vicc_rule_arm.md).
Accuracy/specificity/AUROC ask *"is the label right?"*. **Faithfulness** asks a different,
orthogonal question: *"does the system only say what its evidence actually supports — and can
we audit every claim?"* For a clinical decision-support tool that is arguably the more
important axis, because a confidently-wrong, unattributable call is more dangerous than an
honest abstention.

## 1. The two axes (they are independent)

| Axis | Question | Metrics here | Failure it catches |
|---|---|---|---|
| **Correctness** | Is the call right vs an expert gold? | accuracy, specificity, sensitivity, AUROC | wrong label |
| **Faithfulness** | Does the call follow from, and cite, real retrieved evidence? | hallucination, citation-grounding, directional-faithfulness, abstention-recall | fabrication, over-claim, contradiction, false confidence |
| **Auditability** | Can a human trace *why*, citation by citation? | every criterion carries a resolvable source id (VICC code / CIViC EID / AlphaMissense / gnomAD) | unexplainable "black-box" call |

A model can be accurate *and* unfaithful (right answer, fabricated citation) or faithful *and*
wrong (honest abstention on a variant that is in fact oncogenic). We report both.

## 2. The four faithfulness metrics (leakage-free, no gold needed)

All four are computable from a `cohort_interpretation.json` with no further model calls — they
measure the system against *its own retrieved evidence*, so there is no test-set leakage.
Together they span the three (distinct, overlapping) facets the NLP literature separates:

| Facet | Question | Covered by |
|---|---|---|
| **Groundedness** | is every claim within the provided evidence? | abstention-recall + citation-grounding |
| **Attribution** | does each claim carry the correct source id? | hallucination rate |
| **Faithfulness** (umbrella) | does the conclusion follow, without contradiction? | directional-faithfulness |


1. **Hallucination rate** — fraction of calls that cite an id **not** in the retrieved bundle.
   Ideal = 0. A fabricated citation is the canonical attribution failure.
2. **Citation grounding rate** — of non-abstained calls that *have* evidence available, the
   fraction that cite ≥1 id. Ideal = 1. Catches "right answer, no evidence shown".
3. **Directional faithfulness** — fraction of calls whose *cited* evidence points the same way
   as the call (oncogenic call ⇒ ≥1 cited oncogenic-supporting line). Ideal = 1. Catches a call
   that contradicts the very evidence it cites.
4. **Abstention recall** — of variants with **no** variant-specific evidence, the fraction the
   model abstains on (→ VUS). Ideal = 1. Catches false confidence on an empty bundle.

## 3. How we *raise* faithfulness: enforce it, don't hope for it

Prompting an LLM to "only cite retrieved evidence" reduces but never eliminates these failures.
Our contribution is to make faithfulness a **property guaranteed by construction**, via a
deterministic, model-agnostic post-hoc gate ([`src/classify/faithfulness.py`](../src/classify/faithfulness.py))
that runs on any Generative-mode call plus its bundle and applies four gates in order:

1. **Citation validation (anti-hallucination)** — drop any cited id absent from the bundle ⇒
   hallucination rate is 0 *by construction*.
2. **Abstention** — empty bundle ⇒ force VUS / Tier III.
3. **Directional consistency** — surviving citations must point the call's way, else abstain.
4. **Grounding** — a directional call with evidence available but no citations must abstain.

Every run emits a `faithfulness_audit` block (which gates fired, which citations were dropped),
so the correction itself is auditable. The gate is **pure** (no I/O, no LLM) and unit-tested
against adversarial inputs, so it is fully reproducible.

### Demonstration (fault-injection stress test)

The deterministic mock cohort already scores a perfect 1.0/0.0 on every metric, so to *show* the
gate working we inject the three real LLM failure modes into a copy of the cohort and re-measure
(`scripts/run_faithfulness_ablation.py`):

| metric | corrupted model | after gate |
|---|---|---|
| hallucination rate | 0.452 | **0.0** |
| directional faithfulness | 0.483 | **1.0** |
| abstention recall | 0.40 | **1.0** |
| citation grounding | 1.0 | 1.0 |

44 of 56 calls were repaired. The reading is a **worst-case guarantee**: however unfaithful the
upstream model, the shipped call's faithfulness metrics return to ideal — this is the operational
meaning of "faithful by construction". (It is a guarantee, *not* a measurement of any real model's
hallucination rate; that is what Method A below is for.)

### Real-data anchor (the gate on the actual no-retrieval model)

The fault injection above is synthetic; `scripts/run_faithfulness_real.py` applies the same gate to
the **real** no-retrieval gpt-4o-mini arm recorded in `ablation_report.json`. With no evidence bundle,
that model still emitted confident citations (e.g. "ClinGen: BRAF") on **26/56 = 46.4%** of variants —
all ungrounded. The gate drops every ungrounded citation and forces abstention, taking the ungrounded
rate to **0.0** and abstaining all 56. The honest reading is modest but real: *without* retrieval a
faithful system has nothing legitimate to cite, so the only faithful action is to abstain — which is
exactly what the gate enforces, converting a real 46% confident-fabrication rate into honest
abstention. It complements the retrieval arm, where the same gate leaves grounded calls intact and
only removes the occasional fabrication.

### Auditability on the rule arm

The Deterministic-mode VICC engine is faithful for the same reason from the other direction: every
fired criterion is a citable record (`VICC:OS3` "occurs in 53 samples at a cancerhotspots residue",
`VICC:OVS1`, …). On the ClinVar generalisation set this shows up as **93.9% of oncogenic calls
carrying a strong, citable evidence code** and the rest abstaining — the engine asserts only what it
can cite. See [`vicc_rule_arm.md`](vicc_rule_arm.md).

## 4. Is "faithfulness" a known idea, or our own? (honest positioning)

**The concept is established — we are not inventing it, and should not claim to.** Faithfulness /
groundedness / attribution is a major, active area in NLP and clinical NLP:

- **RAG / summarization faithfulness** (a.k.a. factual consistency): FactCC, SummaC, QAGS, and the
  **RAGAS** framework's "faithfulness" metric.
- **Attribution / citation evaluation**: the "Attributable to Identified Sources (AIS)" framework
  (Rashkin et al.), **ALCE** "enabling LLMs to generate text with citations" (Gao et al.), RARR,
  and medical variants such as MedCite.
- **Faithfulness of explanations/reasoning** (Jacovi & Goldberg): does the stated rationale reflect
  the actual decision?

A reviewer in NLP or clinical-AI will recognise the term immediately — which is good for
credibility but means the *metric* is not the novelty.

**What we can defensibly claim as novel is the application and the mechanism, not the concept:**

1. **Faithfulness/auditability as the *primary* success criterion for somatic oncogenicity & tier
   interpretation.** This subfield (OncoVI, CGI, guideline-concordance studies) optimises and reports
   *accuracy/concordance vs guidelines*; framing variant interpretation as an *attribution* problem —
   and reporting hallucination/abstention as first-class outcomes alongside accuracy — is uncommon here.
2. **Faithful-by-construction enforcement + audit trail**, rather than faithfulness as a property one
   merely measures and hopes for. The deterministic gate gives a worst-case guarantee.
3. **A citable VICC point engine** in which *every* criterion is an auditable, resolvable evidence id —
   pairing the rule arm's accuracy with full attributability.
4. **Dual-mode (Generative vs Deterministic) with discordance as signal**, and **Method A** (multi-model
   agreement + an NLI attribution gate driving abstention) as the harder-setting faithfulness mechanism
   for real, fallible open models.

**One-line framing for the paper:** *"Faithfulness and attribution are established axes in NLP; our
contribution is to make them the primary, enforced, and auditable success criteria for clinical
somatic-variant interpretation — a field that today optimises accuracy alone."*

> Caveat: the citations above are named from domain knowledge for positioning, not yet verified
> bibliographically. Before submission, run the `novelty-strategist` / `literature-scout` agents to
> confirm exact references, check for any direct prior art that already frames variant interpretation
> as attribution, and lock the differentiation. See [[manuscript-preprint-state]].

## 5. Reproduce

```bash
python -m scripts.run_eval                      # 4 faithfulness metrics over the cohort
python -m scripts.run_faithfulness_ablation     # fault-injection: corrupted -> enforced
pytest tests/test_faithfulness.py               # adversarial gate tests
```
