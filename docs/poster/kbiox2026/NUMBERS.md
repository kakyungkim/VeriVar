# Poster number-to-source table

Every number printed on `poster.html` and in the charts, with the file and field it is read from.
Nothing on the poster is typed from the manuscript prose. `tests/test_poster_numbers.py` checks this
table's claims against the same files and fails if a retired value reappears.

Poster: `out/VeriVar_KBioX2026_poster.pdf`, A0 portrait 841 x 1189 mm, for the Chuncheon x KNU x K-BioX
Global Bio Innovation Summit 2026 (2026-11-14). Built by `./build.sh`.

## Headline strip

| Printed | Value | Source file | Field |
|---|---|---|---|
| 0 / 86 identifier citations outside the retrieved evidence | 0 of 86 | `data/outputs/citation_taxonomy.json` | `headline.arms.retrieval_gpt4o_mini_106.identifier_tokens_out_of_bundle` (`k`, `n`) |
| 19 / 56 variants given a fabricated or misattributed identifier without retrieval | 19 of 56 | same | `headline.arms.no_retrieval_E_empty_bundle.variant_any_fabricated_or_misattributed` (`k`, `n`) |
| 0.600 vs 0.586, p = 1.0 | 0.6, 0.586, 1.0 | `data/outputs/stats_report.json` | `horak_3class_accuracy_ci.llm_rag.point`, `.llm_norag.point`, `horak_mcnemar.rag_vs_norag.p_value` |

## Section 3, cohort tiles

| Printed | Value | Source |
|---|---|---|
| 56 variant x context units, 5 cancers, 27-gene panel | 56 | `citation_taxonomy.json` arm `n` = 56; cohort description in `docs/STUDY_SUMMARY.md` §1.1 |
| 70 expert-classified variants | 70 | `data/benchmark/horak_vicc.json` → `n` |
| 712 ClinVar variants | 712 | `data/benchmark/clinvar_onc_holdout.json` → `scopes.all.detection.n` |

## Figure 2, citation existence (`p2_faithfulness.svg`)

| Element | Value | Source |
|---|---|---|
| no-retrieval bar, 19/56 | 0.339, Wilson 0.229–0.470 | `citation_taxonomy.json` `no_retrieval_E_empty_bundle.variant_any_fabricated_or_misattributed` |
| hatched subset, 14/56 | 0.250, Wilson 0.155–0.377 | same arm, `variant_any_fabricated_identifier` |
| retrieval bar, 0/56 | 0.0, Wilson 0.0–0.064 | `retrieval_gpt4o_mini_106.variant_any_fabricated_or_misattributed` |
| McNemar p = 3.8e-06 | 3.814697265625e-06 | `paired_contrasts_variant_level.no_retrieval_E_empty_bundle_vs_retrieval_gpt4o_mini_106.any_fabricated_or_misattributed.mcnemar.p_value_exact` |
| caption: 41 identifiers, 13 real but unrelated | 41, 13 | `no_retrieval_E_empty_bundle.citation_counts` (`b1_fabricated_identifier` 28 + `c_real_unrelated_out_of_bundle` 13 = 41 identifier tokens; `c` = 13) |

## Figure 3, accuracy (`p3_accuracy.svg`)

| Element | Value | Source |
|---|---|---|
| Simplified rule 0.557 [0.443–0.671] | | `stats_report.json` `horak_3class_accuracy_ci.rule` |
| LLM, no retrieval 0.586 [0.471–0.700] | | same, `.llm_norag` |
| LLM + retrieval 0.600 [0.486–0.714] | | same, `.llm_rag` |
| VeriVar rule arm 0.657 [0.543–0.771] | | `horak_vicc.json` `accuracy_3class_ci` |
| OncoVI reference line 0.797 | | `data/benchmark/oncovi_headtohead.json` `oncovi.accuracy_3class` |

## Figure 4, rule arm and discordance (`p4_rule_discordance.svg`)

| Element | Value | Source |
|---|---|---|
| specificity 1.000, 37/37, Wilson 0.906–1.000 | | `horak_vicc.json` `specificity_onc_exact_ci.wilson` |
| sensitivity 0.424, 14/33, Wilson 0.272–0.592 | | `horak_vicc.json` `sensitivity_onc_exact_ci.wilson` |
| 31 of 56 discordant, 26 one step apart | | `data/outputs/discordance_analysis.json` `n_discordant`, `n_total`, `adjacent` |
| type bars 17 / 6 / 3 / 2 / 2 / 1 | | same, `category_counts` |
| text: OncoVI 0.797, p = 0.087 | | `oncovi_headtohead.json` `oncovi.accuracy_3class`, `paired_mcnemar_3class.p_two_sided` |

## Figure 5, input-notation perturbation (`p5_robustness.svg`)

| Element | Value | Source |
|---|---|---|
| CIViC 416 → 0, AlphaMissense 45 → 45 | | `data/outputs/context_ablation.json`, summed over `variants[].baseline` and `variants[].arms.alias` |
| 22 still called drivers, 4 abstained or non-driver | 22, 4 | same, `summary.arms.alias.driver_calls_after_clinical_loss`, `.safe_downgrades_after_clinical_loss` |
| text: 0 of 228 citations out of bundle | | `data/outputs/context_ablation_grounding.json` |
| text: 17.3% repeatability floor | | `data/outputs/baseline_repeatability.json`; manuscript Methods, change-control section |

## Right-hand rail

| Printed | Value | Source |
|---|---|---|
| 392 tests | 392 | `python -m pytest -q` on 2026-11-07 |
| entailment audit 0.444 | 0.444 | `data/outputs/nli_attribution_report.json`; manuscript Results |

## Deliberately not on the poster

- **CancerVar comparison.** Cross-axis (actionability tiers, not VICC oncogenicity); its specificity 0.432 is
  not comparable without the caveat, and the caveat does not fit a poster.
- **The post-gate scorecard** (hallucination 0, grounding 1.0, directional 1.0, abstention recall 1.0).
  These are guarantees the gate enforces by construction, not measured outcomes, and a poster reader cannot
  be expected to carry that distinction. The measured pre-gate figure is shown instead.
- **HemaGuide 0.800.** One head-to-head reference line is enough at poster distance; OncoVI is the closer
  comparator because it implements the same guideline.
- **Retired values.** 0.464 / 46.4% / 26 of 56 (the pre-2026-09-27 fabrication endpoint) and 0.843
  (the pre-SOP-strict rule-arm accuracy) must never appear. The test checks this.
