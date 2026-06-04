# Peer Review — "Citation-grounded retrieval for faithful LLM somatic variant interpretation"

**Reviewer:** (referee, precision-oncology / clinical-informatics)
**Date:** 2026-06-04
**Manuscript:** `docs/manuscript/preprint.md` (bioRxiv preprint draft)
**Target tier assumed:** JAMIA / npj Digital Medicine / Bioinformatics-class methods-and-benchmarking venue

> *Format: biomedical-journal referee report (prose major/minor points) + a per-criterion score table — the hybrid house style (benchmarked to eLife / Nature-npj transparent peer review / OpenReview).*
> *Scope: substantive scientific judgment only. Pre-submission QA (citation/source correctness, figure rendering, mechanical number-vs-source reconciliation, reference completeness) is assumed complete and owned by the authors' QA pipeline (citation-management / the verification gate / paper-critic); it is deliberately not itemised here.*

---

## Recommendation: **MAJOR REVISION**

This is an unusually honest, well-instrumented manuscript whose framing discipline is its greatest strength: the authors repeatedly resist the over-claiming the precision-oncology-LLM literature is prone to, the faithfulness gap is real and statistically robust, and the leakage controls are more thorough than in any comparable LLM-for-variants paper I am aware of. The core claim — faithfulness/auditability is guaranteed by construction and the result is leakage-robust — will, I expect, survive revision; my concerns are about precision of attribution, not validity, and require no new experiments. **The single most decision-critical issue is presentational:** the manuscript reports two very different accuracy regimes (a modest, explicitly non-superior generative LLM at ~0.60 and a strong deterministic VICC rule engine at 0.843 that matches the open OncoVI engine), and the current framing lets the rule arm's strong number create a halo over the LLM system. That, plus the partly-definitional nature of the "faithful by construction" headline, is what holds this at major rather than minor revision.

---

## Summary of the manuscript

The authors present a dual-mode somatic-variant interpreter that classifies variants on two community standards (ClinGen/CGC/VICC oncogenicity and AMP/ASCO/CAP clinical tier) using a hybrid, citation-grounded retrieval layer (structured KB lookup, dense CIViC retrieval, a knowledge graph) under an explicit "faithfulness contract": every assertion must cite a retrieved identifier, and the system must abstain (assign VUS) when no variant-specific evidence exists. Three arms are evaluated — a Generative LLM arm (gpt-4o-mini with self-consistency voting + an agentic verifier), a Deterministic direction-aware rule arm, and a separate citable VICC point-based rule arm — against a 56-variant five-cancer TCGA cohort (faithfulness, leakage-free) and the external 70-variant Horak et al. 2022 expert gold standard (accuracy). The stated contribution is evaluative and applied, not methodological: retrieval grounding makes the interpreter faithful and auditable, suppresses confident parametric over-calling, and (via temporal-holdout, leave-own-evidence-out, second-model and embedding controls) is shown not to be a leakage artifact, with a powered accuracy study explicitly deferred and its design specified.

---

## Major points

1. **Own the definitional boundary of "faithful by construction."** The strongest faithfulness numbers (hallucination 0, grounding/directional/abstention 1.0; Fig 1c) are partly *enforced by the gate*, not discovered — a system that refuses to emit any non-retrieved identifier scores zero fabrication by definition. The genuinely empirical, falsifiable findings are the *pre-gate* behaviour: the RAG arm emitted 0/106 out-of-bundle citations, and the no-retrieval arm fabricated on 26/56 (0.464, 95% CI 0.339–0.589, excluding zero). The manuscript says "by construction" but then lets the post-gate 1.0/0% carry the abstract and Fig 1c. *Fix:* in the abstract and §3.1, lead with the pre-gate empirical numbers and label the 1.0/0% explicitly as the guarantee the contract provides; feature the 18.9% (20/106) source-category imprecision as the honest measured residual — it is the most informative faithfulness number in the paper.

2. **Make the generative-arm vs VICC-rule-arm separation airtight (the decision-critical fix).** A reader skimming the abstract will come away believing "the LLM system reaches 0.843 and matches OncoVI." It does not — the *deterministic rule arm* does, and that arm is explicitly not the LLM and not claimed as novel. The separation is stated but not enforced in the abstract, §3.3, Fig 1, and Fig 5 (which lists "Ours … 0.843" as one row, eliding which arm produced it). *Fix:* at the first mention of 0.843 in the abstract and §3.3, add the clause "a deterministic rule engine, not the LLM, not claimed as a novel classifier"; reorder §3.3 so the generative (faithfulness-first) result precedes the rule arm; and attribute each Fig 1/Fig 5 accuracy cell to the arm that produced it. Note that "matches OncoVI" rests on a non-significant McNemar (p = 0.66) — state it as "statistically indistinguishable accuracy at substantially higher specificity," and bring forward the disclosure that OncoVI is scored on its home set (Horak-70).

3. **Transmit the *direction* of the provisional adjudication.** The "21.4% (12/56) over-call→VUS" reclassification carries a "behavioural change, not verified correctness" caveat — good — but the authors' own provisional adjudication record found the rule correct 2/3 on the three examined "beyond-rules" cases (PTEN R130* and PIK3CA R88Q were over-conservative LLM abstentions; ESR1 E247K favoured the LLM), which *reinforces* the documented VUS-over-resolution limitation. The paper should not rest on "pending adjudication" while its own provisional review leans against the suppression being correct. *Fix:* state in §3.2/Limitations that preliminary, **non-pathologist-signed** review of the examined cases suggests several reclassifications are over-conservative abstentions — this strengthens, not weakens, the paper's honesty — while making explicit that no board-certified molecular pathologist has signed off.

4. **Add a confidence interval to every appearance of the VICC-arm 0.843, and discipline the word "non-inferior."** At n = 70 the 0.843 CI is wide and should accompany the point estimate exactly as the generative-arm numbers do. Separately, "non-inferior" is currently a colloquial reading of overlapping CIs (McNemar p = 1.0 vs no-RAG, p = 0.61 vs rule), not a non-inferiority test against a pre-specified margin. *Fix:* either pre-specify a margin or restate as "comparable / not significantly different."

5. **Meet the relevant reporting guidelines.** This is a diagnostic-accuracy + prediction-model study, but neither **TRIPOD-AI** nor a **STARD** lens is cited or followed. *Fix:* add a short "Reporting" paragraph; a variant flow diagram (398 candidates → 56 classified; Horak 70; OncoVI 69 shared; ClinVar 458) with explicit "intermediate result" (VUS/abstention) handling; a structured model card (model/version, temperature, voting n, verifier, snapshots, replication model); and a per-gene accuracy/abstention table so the EZH2/PTEN thin-coverage weakness is auditable.

---

## Minor points

1. **gpt-4o-mini as primary model** is adequately justified for a preprint (cost at cohort scale; conservative capability floor; a gpt-4o replication that does not change conclusions, 0.70 vs 0.60, p = 0.21). A higher-tier venue will still want the multi-family sweep (Llama/Mixtral) you appropriately defer — flag it as a limitation up front.
2. **Cohort selection** (56 of 398, capping AlphaMissense-only and no-evidence variants) is disclosed as cost control; state the exact tiered selection rule reproducibly so the cohort is not read as showcase-biased (BRAF V600E is engineered in by design).
3. **Multi-model proof-of-concept** introduces new quantitative results (mean agreement 0.929; 44/56 unanimous; 25% abstention) in the Discussion. Promote to Results-with-caveats or compress to a single forward-looking sentence; new findings in the Discussion is a structural weakness.
4. **Figures:** clarify in Fig 3b what the ClinVar-OOD operating point (AUROC 0.902) means visually — it is a single off-curve marker from a different dataset and may be misread as on-curve; and split/annotate the Fig 5 row so the rule-arm accuracy/specificity cells are not conflated with the system's citation-accuracy cell. Keep the ClinVar caveat (benign recall 0; balanced 3-class 0.505) prominent wherever AUROC 0.902 appears.
5. **Leakage nuance:** note that LOVO controls own-evidence leakage but not residue-neighbour leakage (same-gene/same-residue evidence can still leak the answer).
6. **Endpoint:** consider a quadratic-weighted κ / macro-F1 as the primary ordinal endpoint, as you yourself recommend for the future powered study.
7. **Positioning:** the "to our knowledge no prior study reports a leakage-controlled accuracy evaluation alongside a leakage-free faithfulness audit" claim is plausible and is the real contribution; date-stamp it, given two concurrent works ([16],[17]) are already cited.
8. **Housekeeping (governance, not QA):** remove the reader-facing internal note about the corrected "Lin 2025 RAG" citation, and resolve the placeholder repository URL and "[to confirm]" affiliation before posting.

---

## Per-criterion scores

| Criterion | Score (1–5) | Rationale |
|---|---|---|
| Significance / novelty | **3.5** | Faithfulness-by-construction + leakage-controlled evaluation for variant interpretation is a genuine, timely niche; components (hybrid RAG, citable VICC rules, abstention) are individually prior art and correctly not claimed as novel. Significance is in the evaluation discipline — real but incremental. |
| Soundness of method | **4** | Direction-aware rule (not a strawman), enforced enums, offline reproducibility, four orthogonal leakage controls. Capped by single-sample / single-primary-model design and small n. |
| Statistical validity | **4** | Bootstrap CIs + exact McNemar wherever an accuracy comparison appears; non-superiority framing honest. Gaps: no pre-specified non-inferiority margin; VICC-arm 0.843 sometimes reported without a CI. |
| Reproducibility | **4.5** | Released JSON artifacts support the headline numbers on spot-check; scripts named per result; offline snapshots; a deterministic anti-fabrication gate. (Repo URL still a placeholder.) |
| Clarity | **3.5** | Excellent scientific writing, but the generative-vs-rule-arm interleaving (abstract, §3.3) is a real comprehension hazard and the Discussion is partly redundant with Results. |
| Figures / tables | **4** | CIs and McNemar p shown; no misleading visual gains. Substantive issues are attribution/clarity (Fig 5 row, Fig 3b OOD point). |

**Overall recommendation: Major revision.   Reviewer confidence: 4/5 (high).**

---

## Reporting-guideline note

Most relevant instruments: **TRIPOD-AI** (prediction-model reporting) and a **STARD** diagnostic-accuracy lens (the Horak/ClinVar evaluations are classification-accuracy studies against an expert reference standard). Currently neither is cited. Missing/partial items the authors should add: a participant/variant **flow diagram**; explicit **intermediate-result (VUS/abstention) handling**; a single **knowledge-snapshot time/version** table; a structured **model card**; an up-front **sample-size limitation**; standard-form **calibration** reporting; and **per-gene/per-cancer subgroup** accuracy/abstention. See Major point 5.

---

## Confidential comments to the editor

A solid, honest preprint-grade manuscript reporting an applied system plus an unusually rigorous faithfulness/leakage evaluation. The science is sound and the released artifacts support the headline numbers on spot-check; the faithfulness/auditability core claim is robust and will survive revision. The decision-critical issue is presentational risk, not scientific error — two very different accuracy regimes (a modest, explicitly non-superior generative LLM and a strong deterministic rule engine that matches OncoVI) are framed so the rule arm's strong number can halo the LLM system, compounded by the partly-definitional "faithful by construction" headline. This is fixable by reorganisation and explicit fencing.

Severity: moderate. No fabrication, no statistical malpractice; the limitations section is more candid than typical. Novelty is incremental (components are prior art; the contribution is the evaluation framing), appropriate for a preprint and a methods/benchmarking venue, though a top-tier journal may find the n = 70 scale and single-primary-model design thin without the powered, multi-family follow-up the authors themselves specify. I would support acceptance after a major revision that enforces the attribution fixes; no new experiments are required for the preprint. Governance note: an unresolved affiliation/IP placeholder, a product name, and the repository URL must be finalised before posting, and the authors should confirm no proprietary (employer) data or logic is included.

---

*Prior work the reviewer drew on for novelty / positioning assessment:*
- OncoVI (Carta et al., medRxiv 2024) — 80% accuracy / 88% sensitivity on the 93-variant guideline set: https://www.medrxiv.org/content/10.1101/2024.10.10.24315072v1
- Lin et al. 2025, npj Precision Oncology 9(1):141 — over-classification finding: https://www.nature.com/articles/s41698-025-00935-4
