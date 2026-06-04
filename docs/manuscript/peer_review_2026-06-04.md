# Peer Review — "Citation-grounded retrieval for faithful LLM somatic variant interpretation"

**Reviewer:** (referee, precision-oncology / clinical-informatics)
**Date:** 2026-06-04
**Manuscript:** `docs/manuscript/preprint.md` (bioRxiv preprint draft)
**Target tier assumed:** JAMIA / npj Digital Medicine / Bioinformatics-class methods-and-benchmarking venue

---

## 1. Summary of the manuscript

The authors present a dual-mode somatic-variant interpreter that classifies variants on two community standards (ClinGen/CGC/VICC oncogenicity and AMP/ASCO/CAP clinical tier) using a hybrid, citation-grounded retrieval layer (structured KB lookup, dense CIViC retrieval, and a knowledge graph) under an explicit "faithfulness contract": every assertion must cite a retrieved identifier, and the system must abstain (assign VUS) when no variant-specific evidence exists. Three arms are evaluated — a Generative LLM arm (gpt-4o-mini with self-consistency voting + an agentic verifier), a Deterministic direction-aware rule arm, and a separate citable VICC point-based rule arm — against a 56-variant five-cancer TCGA cohort (faithfulness, leakage-free) and the external 70-variant Horak et al. 2022 expert gold standard (accuracy).

The central contribution is **evaluative and applied, not methodological**: the paper argues that retrieval grounding makes the interpreter faithful and auditable *by construction* (0% citation fabrication vs 46.4% without retrieval), suppresses confident parametric over-calling (12/56 over-calls reclassified to VUS), and that any accuracy effect is not a leakage artifact (temporal-holdout, leave-own-evidence-out, second-model, and embedding controls). The accuracy claims are deliberately disciplined: the generative arm is framed as *non-inferior* (not superior), while a separate citable VICC rule arm reaches three-class accuracy 0.843 on Horak-70 and matches the open engine OncoVI at substantially higher specificity. The headline is faithfulness/auditability as a prerequisite for clinical decision support, with a powered accuracy study explicitly deferred and its design specified.

---

## 2. Overall recommendation: **MAJOR REVISION**

This is an unusually honest, well-instrumented manuscript whose framing discipline is its greatest strength: the authors repeatedly resist the over-claiming that the precision-oncology-LLM literature is prone to, and almost every headline number I checked reconciles exactly with the committed result JSONs (details in §6). The faithfulness gap is real and statistically robust, the leakage controls are more thorough than any comparable LLM-for-variants paper I am aware of, and the figures are clean and do not visually imply effects the statistics do not support.

It is not yet acceptable, for three reasons that are addressable but non-cosmetic:

1. **The headline is partly definitional, and the manuscript does not fully own this.** "Faithful by construction" means the strongest faithfulness numbers (0% fabrication, 1.0 grounding/directional/abstention) are partly *enforced by the gate*, not *discovered*. The genuinely empirical, falsifiable result is the *pre-gate* RAG behaviour (0/106 out-of-bundle citations; 46.4% vs the no-retrieval arm). The paper states this but then lets the post-gate "1.0 / 0%" numbers carry the abstract and Figure 1c. The circularity needs to be surfaced, not buried (see Major 1).

2. **The single most decision-critical issue: the two distinct accuracy regimes (generative ≈0.60 non-inferior vs VICC rule 0.843 "SOTA-matching") are interleaved in a way that risks a halo effect.** A reader skims the abstract and comes away believing "the LLM system reaches 0.843 and matches OncoVI." It does not — the rule arm does, and that arm is explicitly *not* the LLM and *not claimed as novel*. The separation is stated but not enforced strongly enough in the abstract, Discussion, and Figure 5 (which lists "Ours (VeriVar) 0.843" as a single row, eliding which arm produced it). This must be made airtight (see Major 2).

3. **Provisional, non-expert-signed adjudication leaks into the interpretation of the strongest behavioural claim.** The authors' own provisional adjudication (the worksheet underlying the manuscript's provisional-adjudication discussion) is admirably explicit that the AI-assisted adjudication found the rule correct 2/3 on the "beyond-rules" cases and that this *reinforces* the VUS-over-resolution limitation. The manuscript keeps the "behavioural change, not correctness" caveat but does not transmit the *direction* of that provisional finding — that the over-call suppression is, on the cases examined, partly over-conservative abstention. This is a fairness issue (see Major 3).

The core claim — faithfulness/auditability is guaranteed and the result is leakage-robust — **survives revision**; I expect it to. The revisions are about precision of attribution and ownership of the definitional boundary, not about new experiments. Hence major revision rather than reject.

---

## 3. Per-criterion scores (1–5; 5 = excellent)

| Criterion | Score | Rationale |
|---|---|---|
| Originality / significance | **3.5** | The faithfulness-by-construction + leakage-controlled-evaluation framing for variant interpretation is a genuine, timely niche; but the system components (hybrid RAG, citable VICC rules, abstention) are individually prior art (ALCE, OncoVI, MedRAG), and the authors correctly do not claim methodological novelty. Significance is in the evaluation discipline, which is real but incremental. |
| Methodological rigor | **4** | Direction-aware rule (not a strawman), enforced enums, offline reproducibility, four orthogonal leakage controls, deterministic verification gate. Strong. Capped by single-sample/single-primary-model design and the small n. |
| Statistical validity | **4** | Bootstrap CIs + exact McNemar applied wherever an accuracy comparison appears; non-inferiority framing is honest and CIs/p-values are reported in-line, in Table 1, and on the figures. Gaps: no formal non-inferiority margin pre-specified; temporal-sweep rows lack CIs (disclosed); VICC-arm 0.843 reported without a CI in several places. |
| Reproducibility | **4.5** | Every headline number reconciles with committed JSONs; scripts named per result; offline snapshots; a deterministic anti-fabrication gate. Repo URL is still a placeholder. |
| Clarity | **3.5** | Generally excellent scientific writing, but the generative-vs-rule-arm interleaving in Results §3.3 and the abstract is a genuine comprehension hazard, and the Discussion is long and partly redundant with Results. |
| Figures / tables | **4.5** | CIs and McNemar p are shown and the figures do not overstate effects (no misleading visual gains). The substantive issues are attribution and clarity: Fig 5 row labelling and the ClinVar-OOD point in Fig 3b need clarification. |

---

## 4. Section-by-section comments

### Abstract
- Generally a model of disciplined reporting. The faithfulness, non-inferiority, and McNemar p-values are all stated.
- **Problem:** the VICC rule arm result ("0.843 … matches OncoVI … at markedly higher specificity") is given roughly equal billing to the faithfulness headline, and a fast reader will attribute it to the LLM system. Add an explicit clause in the abstract that this arm is a *deterministic rule engine, not the LLM, and is not claimed as a novel classifier* — the same disclaimer you make in §Comparison-with-prior-work must appear where the number first lands.
- "a further 18.9% of citations named only the source category … which the faithfulness gate reduced to 0%" — good, but state here (not only in §3.1) that the 0% is *gate-enforced*, so the empirical claim is the pre-gate 0/106 out-of-bundle figure.

### Background and Significance
- Strong, well-referenced, and appropriately positions the work as application-of-known-mitigations rather than new method. The two-failure-mode framing (hallucinated citations + parametric leakage) is crisp and motivates the design.
- The Lin et al. [14] over-classification claim and the OncoVI [19] 80%/88% figures are **verified against source** and accurately represented.
- The gap statement ("no prior variant-interpretation study reports a leakage-controlled accuracy evaluation alongside a leakage-free faithfulness audit") is plausible and is the paper's real contribution; consider softening "To our knowledge" claims with a date, since this is a fast-moving area and two concurrent works ([16],[17]) are already cited.

### Methods
- Datasets, knowledge sources, retrieval arms, and the faithfulness contract are clearly specified and match the supporting summary.
- **gpt-4o-mini as primary model** is *adequately justified* (cost for cohort-scale dual-mode + ablations; conservative capability floor; gpt-4o replication provided). This is a defensible and honestly-argued choice for a preprint; reviewers at a higher-tier venue will still want the multi-family sweep you defer.
- The 56-of-398 cohort selection (capping AlphaMissense-only and no-evidence variants) is disclosed as cost control — good, but state the exact selection rule reproducibly (tiered selection criteria) so the cohort is not seen as cherry-picked toward showcase variants (BRAF V600E is explicitly engineered in).
- **Reporting-guideline gap (see §5):** the Methods do not frame the external benchmark as a diagnostic-accuracy evaluation; add a STARD-style flow (n screened → n with coordinates → n evidence-retrieved → n classified) and a TRIPOD-AI-style model card.

### Results
- §3.1 Faithfulness: the denominators (44 vs 46 vs 56) are carefully explained. Good. But this section should *lead* with the empirical pre-gate number and clearly mark the 1.0/0% as gate-enforced.
- §3.2 Ablation: the 12/56 (21.4%) over-call→VUS reclassification is **exactly reproducible** from `ablation_report.json` (I enumerated all 12). The "behavioural change, not correctness" caveat is present and repeated. The *direction* of the provisional adjudication (rule right 2/3) is missing — see Major 3.
- §3.3 Accuracy: this is where the generative-arm and VICC-rule-arm results are interleaved. The sub-headers help, but the section opens with "the accuracy result is carried by the citable VICC rule arm" and then spends four paragraphs on the rule arm before the generative arm — inverting the paper's own stated emphasis (faithfulness first, rule arm as a "need not trade accuracy" demonstration). Reorder or fence more explicitly.
- §3.3 Independent generalisation (ClinVar n=458): the honesty here is exemplary — benign recall 0, balanced 3-class 0.505, AUROC-as-onc-vs-rest-only. Keep this caveat prominent; do not let "AUROC 0.902" travel without it.
- §3.4 Leakage controls: thorough and correctly interpreted as robustness, not gain. The explicit statement that LLM parametric leakage remains uncontrolled (quantified only by the no-retrieval floor) is exactly right and should be retained verbatim.
- §3.5 Discordance: all category counts reconcile with `discordance_analysis.json`. The KRAS G12V context-dependence case is well chosen and matches `analyses_report.json`.

### Discussion / Limitations
- The Limitations section is honest and comprehensive (modest absolute accuracy, VUS over-resolution, thin rare-variant coverage, uncontrolled parametric leakage, single-sample/single-model, simplified deterministic baseline, cohort capping). This is better than most submissions.
- The "Toward a powered accuracy evaluation" subsection is genuinely useful and shows the authors understand exactly what their study cannot claim. The power analysis (several hundred variants for a 0.05 gain) is a credibility asset.
- The multi-model proof-of-concept (§Discussion) is appropriately fenced as preliminary, but it introduces *new results* (mean agreement 0.929, 44/56 unanimous, 25% abstention) in the Discussion. Either promote these to Results-with-caveats or compress to a single forward-looking sentence; new quantitative findings in Discussion is a structural weakness reviewers will flag.

### References
- 21 references; I verified the two highest-risk ones (Lin [14], OncoVI [19]) against source records and both are accurate. The transparent note about the corrected "Lin 2025 RAG" citation is good scholarly practice but **should be removed from the published version** (it is an internal provenance note, not reader-facing). The placeholder repo URL and "[to confirm]" affiliation must be resolved before posting.
- Reference [18] (Ferber) lacks volume/page (cited as "Nat Cancer 2025" + DOI only) — confirm it resolves to a versioned record.

### Figures
- **Fig 1** (system + faithfulness scorecard): clean; the "VICC arm benchmarked vs OncoVI" annotation and the 0.843 in panel (a) again risk attributing the rule-arm accuracy to the whole system.
- **Fig 2** (fabrication 0.46→0; 12/56 waffle; contract behaviours 1.0): correct, CI shown, no overstatement. The waffle plot shows exactly 12 filled cells.
- **Fig 3** (OncoVI head-to-head, ROC+OOD, error asymmetry, sensitivity dial): all values match the JSONs. **Clarify in 3b** what "ClinVar OOD operating point AUROC 0.902" means visually — a single marker is plotted but it represents a different dataset's operating point; a reader may misread it as on-curve.
- **Fig 4** (generative confusion, discordance bars, cross-cancer): recall values (0.79/0.37/0.71) reconcile with `horak_results.json`. Good.
- **Fig 5** (capability landscape): useful, but the "Ours (VeriVar) … 0.843 / 0.973 / 1.00" row conflates the VICC rule arm's accuracy/specificity with the LLM system's citation accuracy in a single row. Split or annotate which arm each cell comes from. Also confirm the product name "VeriVar" is intended for the public version.
- **S1–S3**: report CIs/p-values and make no overstated visual claims; no substantive concerns.

---

## 5. Reporting-guideline check

This is a methods/benchmarking + diagnostic-accuracy study. The two most relevant instruments are **TRIPOD-AI** (prediction-model reporting) and a **STARD** diagnostic-accuracy lens (since the Horak/ClinVar evaluations are essentially classification-accuracy studies against an expert reference standard). Neither is currently cited or followed.

**STARD-style items missing or partial:**
- No participant/variant **flow diagram** (398 candidates → 56 classified; 70 Horak; 69 OncoVI-shared; 458 ClinVar). Add one.
- Reference standard is well-specified (Horak expert labels) — good.
- **Indeterminate results** (VUS/abstentions) are handled as a class — good, and clinically appropriate, but should be explicitly stated as a STARD "intermediate result" handling decision.
- No reporting of **time/version** of knowledge snapshots in a single table (scattered across Methods).

**TRIPOD-AI items missing or partial:**
- **Model card**: primary model, version/date, temperature, voting n, verifier, prompt availability — present in prose but should be a structured table.
- **Sample size justification**: explicitly absent for the primary study (acknowledged in the "powered evaluation" section, which is good) — but TRIPOD-AI expects it stated up front as a limitation.
- **Calibration**: voting-confidence calibration is reported (§3.5) but only narratively; report a calibration figure or numbers in a standard form.
- **Fairness / subgroup**: per-gene and per-cancer breakdowns exist in the JSONs (`analyses_report.json`); surface the per-gene accuracy/abstention so the EZH2/PTEN thin-coverage weakness is auditable.

Adding a short "Reporting" paragraph citing TRIPOD-AI + STARD and a flow diagram would materially strengthen the submission for the assumed venue tier.

---

## 6. Specific scrutiny on high-risk points (as requested)

**(a) Is the faithfulness headline genuinely supported or partly definitional?**
**Partly definitional, and this must be owned.** The empirical, falsifiable findings are: (i) RAG arm emitted 0/106 out-of-bundle citations pre-gate; (ii) the no-retrieval arm fabricated on 26/56 (0.464, 95% CI 0.339–0.589), CI excluding zero. Both reconcile with `stats_report.json` and `eval_report.json`. These are strong and genuine. By contrast, the post-gate "hallucination 0 / grounding 1.0 / directional 1.0 / abstention 1.0" (Fig 1c) are *contract-enforced*: a system that refuses to emit any non-retrieved identifier will score 0 fabrication by definition. The manuscript says as much ("by construction") but then features the enforced numbers. **Fix:** in the abstract and §3.1, lead with the pre-gate empirical numbers and label the 1.0/0% explicitly as the guarantee the contract provides, not as a measured outcome. The 18.9% (20/106) source-category imprecision is the honest measured residual and is the most informative faithfulness number you have — feature it.

**(b) Small-n and non-inferiority honesty (56-cohort, 70-Horak).**
**Honest.** CIs and exact McNemar are reported everywhere an accuracy comparison appears (abstract, §3.3, §3.4, Table 1, Fig 4). The generative arm is explicitly *non-inferior, not superior* (McNemar p=1.0 vs no-RAG, p=0.61 vs rule), reconciling with `stats_report.json` (a_better 15/14, 9/6). **Caveats to address:** (i) no formal non-inferiority *margin* is pre-specified — "non-inferior" is currently a colloquial reading of overlapping CIs, not a non-inferiority test; either soften to "comparable / not significantly different" or specify a margin. (ii) The VICC-arm 0.843 is frequently reported without a CI; at n=70 its CI is wide and should accompany every appearance of 0.843, exactly as you do for the generative arm.

**(c) Leakage controls — convincing? residual parametric leakage acknowledged?**
**Among the strongest parts of the paper.** Four orthogonal controls (temporal holdout to pre-2012, LOVO, gpt-4o, embedding) all leave accuracy statistically unchanged; values reconcile with `horak_temporal.json`, `horak_lovo.json` (0.614 vs 0.600, p=1.0), `horak_gpt4o.json` (0.70, p=0.21), `embed_ablation.json`. Critically, the manuscript explicitly states that **LLM parametric leakage remains uncontrolled** and is quantified only by the no-retrieval floor — this is the correct and honest position; keep it. One nuance: the LOVO control removes the variant's *own* CIViC evidence but same-gene/same-residue evidence can still leak the answer (you note neighbour-inheritance for the rule arm); state that LOVO controls own-evidence leakage but not residue-neighbour leakage.

**(d) VICC rule arm "0.843, matches OncoVI at higher specificity" vs modest generative accuracy — framed without overclaiming?**
**Mostly, but this is the weakest framing point (Major 2).** The numbers are accurate: `horak_vicc.json` gives 0.843 (5-class 0.643, AUROC 0.906, spec 0.973, sens 0.697); `oncovi_headtohead.json` gives ours 0.841 vs OncoVI 0.797 on 69 shared (McNemar p=0.664, 12 vs 9 only-correct), spec 0.972 vs 0.806. The error-asymmetry argument (9 honest abstentions vs 9 confident over-calls, symmetric counts but asymmetric clinical risk) is legitimate and well-made. The risk is purely *attributional*: this arm is a deterministic rule engine, explicitly *not* the LLM and *not claimed novel* (you concede OncoVI already maps criteria to evidence). Ensure no reader can attribute 0.843 to "the LLM system." Also: "matches OncoVI" rests on a non-significant McNemar (p=0.66) — i.e. *not distinguishable*, which you should state as "statistically indistinguishable accuracy at higher specificity," and note that OncoVI is being scored on its *home set* (Horak-70), which favours neither but should be disclosed (you do, in the future-work section — bring it forward).

**(e) The 12/56 over-call→VUS reclassification — is the "behavioural change, not verified correctness" caveat consistently applied?**
**The caveat is consistently present, but its provisional *direction* is omitted (Major 3).** The 12 variants reconcile exactly with `ablation_report.json`. The caveat "21.4% measures behavioural change, not correctness" appears in abstract, §3.2, and Discussion. However, the authors' own provisional adjudication record (the worksheet behind the manuscript's provisional-adjudication discussion) reports that on the 3 examined "beyond-rules" cases the **rule was right 2/3** (PTEN R130* and PIK3CA R88Q: the LLM over-abstained; ESR1 E247K favoured the LLM), explicitly *reinforcing the VUS-over-resolution limitation*. The manuscript should not hide behind "pending adjudication" while the project's own provisional review leans against the over-call-suppression being correct. State that preliminary (non-expert-signed) review of the examined cases suggests several reclassifications are over-conservative abstentions, consistent with the documented VUS-over-resolution weakness. This strengthens, not weakens, the paper's honesty.

**(f) gpt-4o-mini as primary model — adequately justified?**
**Yes**, for a preprint: cost (cohort-scale dual-mode + ablations), conservative capability floor, and a gpt-4o replication that does not change the conclusions (0.70 vs 0.60, p=0.21). A higher-tier journal will still request a multi-family sweep (Llama/Mixtral), which you appropriately defer.

**(g) Provisional (non-expert-signed) adjudication — properly fenced off from claims?**
**Yes in the manuscript proper** — no correctness claim is built on the adjudication, and the worksheet is not cited as evidence. The only gap is the omission of its *direction* (point e). Ensure the published version contains **no** statement that could be read as expert-validated correctness, and explicitly state that no board-certified pathologist has signed the adjudication.

**(h) Numbers in prose vs JSONs — discrepancies found:**
I recomputed/cross-checked every headline number against the committed JSONs. Findings:
- **All major numbers reconcile** — faithfulness (0/46, 44/44, 10/10, 2 abstained-despite-evidence), 46.4% [0.339–0.589], 12/56, κ values, Horak 3-class (0.557/0.586/0.600), McNemar (p=1.0; p=0.61), LOVO (0.614, p=1.0), gpt-4o (0.70, p=0.21), temporal (0.586/0.629/0.600/0.643), embedding (0.243/0.229/0.229), VICC (0.843, AUROC 0.906, spec 0.973, sens 0.697), OncoVI head-to-head (0.841 vs 0.797, p=0.664), ClinVar (n=458, AUROC 0.902, spec 0.967, sens 0.537), discordance categories, cross-cancer, AlphaMissense agreement 0.944 (17/18), verifier (10 changed, 6 toward/4 away, 0.518→0.571). This is excellent reproducibility.
- **Minor inconsistency #1 (multimodel POC):** the manuscript (Suppl. §) says "12 cases of partial disagreement" but `multimodel_faithfulness_poc.json` reports `abstained: 14` (abstention_rate 0.25 = 14/56) at threshold 0.66. 56−44 unanimous = 12, but abstained = 14; "12 partial disagreement" and "14 abstained" are both used loosely. Reconcile (unanimous=44, partial=12, but abstention rule abstained on 14 → clarify the abstention rule vs unanimity).
- **Minor inconsistency #2 (OncoVI number):** the abstract/Table use OncoVI 0.797 (69-shared, head-to-head JSON) while `horak_vicc.json` `baselines.oncovi_3class` and the text elsewhere use 0.80 (published full-93). Both are correct *for their respective sets*; ensure each instance states which set (you mostly do — verify §3.6 and Table 2 are internally consistent: Table 2 reference row says OncoVI 0.797 on 69 shared, good).
- **Minor inconsistency #3 (temporal full-corpus point):** prose (§3.4) correctly flags that the temporal-sweep full-corpus point (0.586) differs from the primary pipeline (0.600) because it is a separate re-embed/re-index run. This is disclosed; keep it.
- **No fabricated variants detected** in the manuscript prose (the project's own gate previously caught a "TP53 Y220C" slip; it is correctly absent).

---

## 7. Comments to the Authors

This is a genuinely careful piece of work, and the discipline with which you refuse to over-claim accuracy is a credit to the manuscript — it is rarer than it should be in this subfield. The faithfulness gap is robust, the leakage controls are the most thorough I have seen for LLM variant interpretation, and your numbers reconcile with your released artifacts to a degree most submissions do not approach.

To move this from "honest preprint" to "publishable methods/benchmarking paper," focus on **attribution precision** rather than new experiments:

1. **Own the definitional boundary of "faithful by construction."** Lead with the empirical pre-gate numbers (0/106 out-of-bundle; 46.4% no-retrieval, CI excludes 0) and the 18.9% source-category imprecision; explicitly label the 1.0/0% contract behaviours as *guarantees the gate enforces*, not measured emergent properties.
2. **Make the generative-arm vs VICC-rule-arm separation airtight** in the abstract, §3.3, Fig 1, and Fig 5. No reader should be able to attribute 0.843 / "matches OncoVI" to the LLM. State at first mention that the VICC arm is a deterministic rule engine, not the LLM, and is not claimed as novel.
3. **Transmit the direction of your provisional adjudication.** Your own worksheet finds the rule correct 2/3 on the beyond-rules cases, reinforcing VUS over-resolution. Say so; it makes the over-call-suppression claim more credible, not less.
4. **Add CIs to every appearance of the VICC-arm 0.843**, as you already do for the generative arm.
5. **Add a STARD/TRIPOD-AI reporting paragraph, a variant flow diagram, a model card, and per-gene breakdowns.**
6. Resolve placeholders (affiliation, repo URL), remove the reader-facing reference-provenance note, and reconcile the two minor multimodel/OncoVI numbering inconsistencies in §6(h).

None of these requires re-running the pipeline; all are within reach for a revision.

---

## 8. Confidential Comments to the Editor

This is a solid, honest preprint-grade manuscript reporting an applied system plus an unusually rigorous faithfulness/leakage evaluation. The science is sound and reproducible — I independently reconciled essentially every headline number against the authors' committed JSON artifacts, and they match (including the 12/56 reclassification, the four leakage controls, and the OncoVI head-to-head). The faithfulness/auditability core claim is robust and **will survive revision**; my concerns are about precision of attribution, not validity.

The decision-critical issue is presentational risk, not scientific error: the manuscript reports two very different accuracy regimes (a modest, explicitly non-inferior generative LLM at ~0.60, and a strong deterministic VICC rule engine at 0.843 that matches OncoVI), and the current framing lets the rule arm's strong number create a halo over the LLM system. Combined with the partly-definitional nature of the "faithful by construction" headline, an inattentive reader could over-interpret the contribution. This is fixable with reorganisation and explicit fencing.

Severity: moderate. There is no fabrication, no statistical malpractice, and the limitations section is more candid than typical. The novelty is incremental (the components are prior art; the contribution is the evaluation framing), which is appropriate for a preprint and for a methods/benchmarking venue, but a top-tier journal may find the n=70 scale and single-primary-model design thin without the powered, multi-family follow-up the authors themselves specify. I would be comfortable seeing this accepted after a major revision that enforces the attribution fixes; I do not believe a new round of experiments is required for the preprint, though the journal version would benefit from the larger benchmark.

One governance note for the editor: the manuscript carries an unresolved affiliation/IP placeholder and a product name ("VeriVar"); these and the repository URL must be finalised before any posting, and the authors should confirm no proprietary (employer) data or logic is included — their own documentation indicates active attention to this boundary.

---

## 9. Prioritized revision list

### Required (must address before acceptance)
1. **R1 — Fence the faithfulness claim** as partly gate-enforced; lead with pre-gate empirical numbers; feature the 18.9% imprecision residual. (§Abstract, §3.1)
2. **R2 — Enforce generative-arm vs VICC-rule-arm separation** in Abstract, §3.3, Fig 1, Fig 5; state the rule arm is deterministic, not the LLM, not novel; never let 0.843 attach to "the LLM system."
3. **R3 — Add the direction of the provisional adjudication** (rule right 2/3 on beyond-rules; over-conservative abstention) while keeping it explicitly non-expert-signed. (§3.2, Limitations)
4. **R4 — Add CIs to all VICC-arm 0.843 appearances**; either specify a non-inferiority margin or restate "non-inferior" as "not significantly different." (§3.3, Table 1/2)
5. **R5 — Reporting compliance:** add STARD/TRIPOD-AI paragraph, a variant flow diagram, a model card, and per-gene accuracy/abstention. (§Methods/Results)
6. **R6 — Resolve placeholders** (affiliation, repo URL), remove the reader-facing reference-provenance note, confirm Ferber [18] bibliographic completeness.
7. **R7 — Reconcile minor numeric inconsistencies:** multimodel "12 partial disagreement" vs 14 abstained; ensure every OncoVI 0.797 vs 0.80 instance names its variant set. (§Discussion/§3.6/Table 2)

### Optional (would strengthen; not blocking for a preprint)
8. **O1 — Promote or compress the multi-model POC**: do not introduce new quantitative results in the Discussion.
9. **O2 — Clarify Fig 3b** ClinVar-OOD operating point (off-curve, different dataset) and Fig 5 per-cell arm attribution.
10. **O3 — State the exact tiered cohort-selection rule** so the 56/398 selection is auditable and not read as showcase-biased.
11. **O4 — Note LOVO controls own-evidence but not residue-neighbour leakage.**
12. **O5 — Consider a quadratic-weighted κ / macro-F1** as the primary ordinal endpoint, as you yourself recommend for the future study.

---

*Sources consulted for prior-art verification:*
- OncoVI (Carta et al., medRxiv 2024) — 80% accuracy / 88% sensitivity on the 93-variant guideline set: https://www.medrxiv.org/content/10.1101/2024.10.10.24315072v1
- Lin et al. 2025, npj Precision Oncology 9(1):141 — over-classification finding: https://www.nature.com/articles/s41698-025-00935-4
