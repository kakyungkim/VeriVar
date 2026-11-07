# Faithfulness & auditability — concepts, metrics, and how we raise them

This is the conceptual companion to the rule-arm work in [`vicc_rule_arm.md`](vicc_rule_arm.md).
Current numbers are read from `data/outputs/citation_taxonomy.json` and
`data/outputs/nli_attribution_report.json`; the manuscript (`docs/manuscript/preprint.md`) is the
authoritative statement.
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

### Two kinds of citation failure (Type I and Type II)

The citation-integrity literature separates two failures that a single "fabrication rate"
conflates, and we report them separately:

- **Type I — citation existence.** The cited identifier is not in the retrieved evidence (or does
  not exist at all). The faithfulness gate removes this by construction.
- **Type II — citation support.** The cited record is real and retrieved, but does not support the
  claim it is attached to. The gate does **not** guarantee this.

**Citation taxonomy (Type I, measured).** One pre-specified taxonomy
(`src/eval/citation_taxonomy.py`) is applied identically to every arm: (a) in bundle; (b1)
fabricated identifier (placeholder-pattern number, an identifier under a namespace with no numeric
scheme, or no NCBI record); (b2) real and related but outside the bundle; (c) real but unrelated
to the variant's gene (misattributed); (d) non-identifier token, counted as imprecision.

| Arm (gpt-4o-mini, 56 variants) | Citation tokens | In bundle | Fabricated (b1) | Misattributed (c) | Non-identifier (d) | Variants with a fabricated or misattributed identifier |
|---|---|---|---|---|---|---|
| Retrieval, pre-gate | 106 | 86 | 0 | 0 | 20 | **0 / 56** |
| Retrieval, post-gate (primary run) | 90 | 90 | 0 | 0 | 0 | 0 / 56 |
| No retrieval | 56 | 0 | 28 | 13 | 15 | **19 / 56** (0.339, Wilson 95% CI 0.229–0.470) |

With retrieval, 0 of 86 identifier citations fell outside the bundle (one-sided 95% Clopper–Pearson
upper bound 3.4%). The paired contrast on variants with a fabricated or misattributed identifier is
19 versus 0, exact McNemar p = 3.8×10⁻⁶. Identifiers were resolved against NCBI E-utilities (lookup
cache committed as `data/outputs/citation_lookup_cache.json`).

**Citation support (Type II, measured approximately).** `scripts/run_nli_attribution.py` asks
whether each in-bundle cited record entails the claim that cites it (DeBERTa-v3 NLI, decision rule
fixed a priori, zero LLM calls). On the 90-citation primary run: supported 40 (0.444, 95% CI
0.344–0.544; variant-clustered 0.348–0.543), neutral 43 (0.478), contradicted 7 (0.078). We read
0.444 as a **noisy lower bound**, not a Type II error rate: hand review found the NLI labels biased
against support (no row labelled contradicted was a genuine contradiction), and 3 genuine
mismatches among the inline citations labelled neutral. Type II faithfulness is the open part of
the contract.

## 3. How we *raise* faithfulness: enforce it, don't hope for it

Prompting an LLM to "only cite retrieved evidence" reduces but never eliminates these failures.
Our contribution is to make faithfulness a **property guaranteed by construction**, via a
deterministic, model-agnostic post-hoc gate ([`src/classify/faithfulness.py`](../../src/classify/faithfulness.py))
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
the **real** no-retrieval gpt-4o-mini arm recorded in `ablation_report.json`. With no evidence
bundle, that model still emitted confident citations, and under the taxonomy above 19 of 56
variants carried a fabricated or misattributed identifier. The gate drops every citation that is
not in the (empty) bundle and forces abstention, so all 56 are abstained. The honest reading is
modest but real: *without* retrieval a faithful system has nothing legitimate to cite, so the only
faithful action is to abstain, which is exactly what the gate enforces. In the retrieval arm the
same gate leaves grounded calls intact; there, pre-gate, no identifier citation fell outside the
bundle, and the gate's exact-identifier matching removes the 20 non-identifier tokens.

### Auditability on the rule arm

The Deterministic-mode VICC engine is auditable for the same reason from the other direction:
every fired criterion is a citable record (`VICC:OS3` "occurs in N samples at a cancerhotspots
residue", `VICC:OVS1`, …), and the engine asserts "oncogenic" only when its points reach the
threshold. On Horak-70 the SOP-strict engine made no oncogenic over-call (specificity 1.000, 37/37)
at sensitivity 0.424. See [`vicc_rule_arm.md`](vicc_rule_arm.md).

### Where the contract does not hold

The abstention trigger fires only when *no variant-specific evidence* is retrieved, and a
coordinate-keyed computational prior counts as such evidence. In the input-context ablation
(`data/outputs/context_ablation.json`), writing a gene under an HGNC alias symbol, or the protein
change in three-letter HGVS, removed every curated clinical evidence item for the 26 variants that
had any, yet 22 of them were still called Oncogenic or Likely Oncogenic on the AlphaMissense prior
alone. No citation fell outside the bundle (0 of 228), so the contract held as written while not
guaranteeing that a driver call rests on curated clinical evidence.

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
3. **A citable VICC point engine** in which *every* criterion is an auditable, resolvable evidence id.
   It is reported for its auditability and error profile, not for accuracy (OncoVI and HemaGuide are
   higher in point estimate on the shared set; p = 0.087 each).
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
python -m scripts.run_citation_taxonomy         # Type I taxonomy across arms (committed NCBI lookup cache)
python -m scripts.run_nli_attribution           # Type II NLI audit (no LLM calls)
pytest tests/test_faithfulness.py               # adversarial gate tests
```
