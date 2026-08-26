---
title: 'VeriVar: citation-grounded, dual-mode LLM interpretation of somatic cancer variants'
tags:
  - Python
  - bioinformatics
  - precision oncology
  - somatic variant interpretation
  - large language models
  - retrieval-augmented generation
authors:
  - name: Ka-Kyung Kim
    orcid: 0000-0000-0000-0000
    affiliation: 1
affiliations:
  - name: Independent Researcher, Seoul, Republic of Korea
    index: 1
date: 27 August 2026
bibliography: paper.bib
---

# Summary

Somatic variant interpretation — deciding whether a tumour mutation is oncogenic and clinically actionable — is a rate-limiting, audit-critical step in precision oncology. `VeriVar` is a Python pipeline that interprets somatic variants on two international standards, the ClinGen/CGC/VICC oncogenicity classification [@Horak2022] and the AMP/ASCO/CAP clinical tier system [@Li2017], using a large language model (LLM) that is constrained to be *faithful by construction*. For each variant, the pipeline assembles a citable evidence bundle through hybrid retrieval (structured knowledgebase lookup, dense retrieval, and a knowledge graph) over public resources including CIViC [@Griffith2017], OncoKB [@Chakravarty2017], and COSMIC [@Tate2019]. A faithfulness contract then governs generation: every assertion may cite only retrieved identifiers, and when no variant-specific evidence exists the system must abstain and assign VUS (variant of uncertain significance). Interpretation runs as parallel arms — a generative LLM mode with self-consistency voting and an adversarial verifier, a deterministic rule mode in which the LLM writes only the human-readable rationale, a transparent VICC point-based rule engine as an honest baseline, and a no-retrieval baseline that isolates what the LLM answers from pretraining memory alone. Disagreement between arms is surfaced as a primary signal that localises genuine interpretive uncertainty. The pipeline is built and evaluated entirely on public data, runs offline-reproducibly, and ships with an automated test suite (207 tests) covering retrieval, classification logic, faithfulness enforcement, and report generation. `VeriVar` is research software for methods development and education; it is explicitly not a clinical diagnostic device.

# Statement of need

Rule-based interpretation engines such as CancerVar [@Li2022CancerVar], the Personal Cancer Genome Reporter [@Nakken2018], and the Cancer Genome Interpreter [@Tamborero2018] are reproducible and auditable, but their coverage of rare or under-curated variants is bounded by their databases, and they neither read free-text evidence on demand nor produce natural-language justifications. LLMs read evidence fluently and draft structured prose, and recent benchmarks show competitive classification behaviour on cancer variants [@Lin2025; @Lu2025]. Two failure modes, however, bar naive use in this domain: hallucinated citations, where a model emits plausible but non-existent PMIDs or database identifiers [@Gao2023], and parametric leakage, where famous driver variants are answered from pretraining memory rather than the supplied evidence, inflating apparent accuracy and producing confident over-calls on benign look-alikes.

Existing LLM-based variant tools report accuracy but rarely control for these failure modes. `VeriVar` fills this gap with a design in which faithfulness and auditability are guaranteed structurally rather than promised statistically: the citation-restricted generation contract makes every claim traceable to a retrieved identifier; the abstention rule prevents evidence-free calls; and the built-in no-retrieval arm gives every user a leakage control, so that any accuracy effect can be attributed to evidence rather than memorisation. Because the deterministic mode fixes labels by transparent rules while the LLM contributes only rationale text, sites that require review safety can obtain identical outputs on every run. The intended audience is computational oncology researchers, developers of LLM systems for medicine, and educators who need an auditable, offline-reproducible reference implementation for retrieval-grounded variant interpretation.

# Design and quality control

The pipeline separates retrieval, evidence bundling, classification, verification, and reporting into testable modules. Every interpretation arm consumes the same evidence bundle, which makes arm-to-arm discordance meaningful. Outputs include per-variant structured labels on both standards, the cited evidence identifiers, and an auditable rationale. The automated test suite (207 tests, running offline in under a minute) exercises the faithfulness contract directly — including tests that a variant without retrieved evidence must abstain — alongside classification logic, cohort loading, and head-to-head comparison against the rule engine. Continuous integration runs the suite on every push.

# Acknowledgements

This work was conducted independently, using only public data and personal computing resources. The author thanks the maintainers of the public knowledgebases on which the pipeline builds.

# References
