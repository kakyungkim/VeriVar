"""Offline tests for scripts/run_nli_attribution.py (no model download).

The NLI model is replaced by a stub scorer keyed on string content, so these
tests exercise alignment, citation resolution, chunking, the a-priori decision
rule, aggregation and the imprecision cross-tab only.
"""
from scripts import run_nli_attribution as m


def _stub(pairs):
    """Entail if the premise contains 'supports-claim'; contradict on 'refutes'."""
    out = []
    for premise, _hyp in pairs:
        if "supports-claim" in premise:
            out.append({"entailment": 0.9, "neutral": 0.05, "contradiction": 0.05})
        elif "refutes" in premise:
            out.append({"entailment": 0.05, "neutral": 0.15, "contradiction": 0.8})
        else:
            out.append({"entailment": 0.1, "neutral": 0.8, "contradiction": 0.1})
    return out


def test_split_sentences_unwraps_verifier_and_keeps_hgvs():
    s = m.split_sentences("BRAF p.G469E is oncogenic. It is pathogenic. "
                          "[Verifier: Evidence is unaltered function.]")
    assert s == ["BRAF p.G469E is oncogenic.", "It is pathogenic.",
                 "Evidence is unaltered function."]


def test_strip_citations_removes_inline_ids():
    assert m.strip_citations("Afatinib works (CIViC:EID879).") == "Afatinib works."
    assert m.strip_citations("Predicted pathogenic [AlphaMissense:17:37881332G>A], so LO.") \
        == "Predicted pathogenic, so LO."


def test_align_inline_vs_fallback():
    rat = "A trial showed benefit (CIViC:EID879). Computation says pathogenic."
    hyps, how = m.align_citation(rat, "CIViC:EID879")
    assert how == "inline" and hyps == ["A trial showed benefit."]
    hyps, how = m.align_citation(rat, "AlphaMissense:1:2A>T")
    assert how == "max_over_rationale" and len(hyps) == 2


def test_resolve_reproduces_imprecision_categories():
    ids = ["CIViC:EID6003", "AlphaMissense:7:140481402C>T"]
    src = {"CIViC:EID6003": "CIViC", "AlphaMissense:7:140481402C>T": "AlphaMissense"}
    assert m.resolve_citation("CIViC:EID6003", ids, src) == ("CIViC:EID6003", "exact")
    assert m.resolve_citation("EID6003", ids, src) == ("CIViC:EID6003", "normalized")
    assert m.resolve_citation("AlphaMissense", ids, src)[1] == "bare_source"
    assert m.resolve_citation("OP1", ids, src) == (None, "unresolvable")


def test_chunking_respects_budget():
    text = " ".join(f"Sentence number {i} has words." for i in range(100))
    chunks = m.chunk_premise(text, max_words=50)
    assert all(len(c.split()) <= 50 for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_decision_rule_order():
    assert m.label_scores(0.5, 0.9) == "supported"
    assert m.label_scores(0.49, 0.5) == "contradicted"
    assert m.label_scores(0.2, 0.2) == "neutral"


def test_label_template_is_fixed_and_vus_untestable():
    assert m.label_template("Likely Oncogenic", "BRAF", "p.G469E") == \
        "BRAF G469E is an oncogenic mutation."
    assert m.label_template("VUS", "BRAF", "p.G469E") is None


def _variant(vk, cites, evs, rationale="Claim one. Claim two.", call="Oncogenic"):
    return {"variant_key": vk, "cancer_type": "X", "gene": vk.split()[0],
            "hgvsp": vk.split()[1],
            "mode_a": {"oncogenicity": call, "rationale": rationale, "citations": cites},
            "bundle": {"evidences": evs}}


def test_pipeline_scoring_and_aggregate():
    ev = lambda i, s: {"id": i, "source": "CIViC", "gene": "G", "variant": "p.V1",
                       "statement": s}
    vs = [_variant("G p.V1", ["CIViC:EID1", "CIViC:EID2"],
                   [ev("CIViC:EID1", "supports-claim text."), ev("CIViC:EID2", "other.")]),
          _variant("G p.V2", ["CIViC:EID3"], [ev("CIViC:EID3", "This refutes it.")])]
    recs = m.pipeline_records(vs, "statement")
    m.score_records(recs, _stub)
    assert [r["label"] for r in recs] == ["supported", "neutral", "contradicted"]
    agg = m.aggregate(recs)
    assert agg["n_citations"] == 3 and agg["n_variants"] == 2
    assert agg["citation_level"]["supported"]["iid"]["point"] == round(1 / 3, 3)
    assert agg["variant_level"]["counts"] == {"partially": 1, "unsupported": 1}
    assert agg["variant_level"]["any_contradicted"]["point"] == 0.5
    sample = m.hand_sample(recs, n=3)
    assert {s["label"] for s in sample} == {"supported", "neutral", "contradicted"}


def test_label_only_crosstab_and_kappa():
    evs = [{"id": "CIViC:EID1", "source": "CIViC", "statement": "supports-claim."},
           {"id": "AlphaMissense:1:2A>T", "source": "AlphaMissense", "statement": "score."}]
    cohort = {"G p.V1 | X": _variant("G p.V1", [], evs)}
    results = [{"variant_key": "G p.V1", "cancer_type": "X", "gene": "G", "hgvsp": "p.V1",
                "per_model": {m.LABEL_ONLY_MODEL: {
                    "oncogenicity": "Oncogenic",
                    "cited_ids": ["EID1", "AlphaMissense", "OP1"]}}}]
    recs = m.label_only_records(results, cohort, "statement")
    assert [r["match"] for r in recs] == ["normalized", "bare_source", "unresolvable"]
    assert sum(r["imprecise"] for r in recs) == 2
    m.score_records(recs, _stub)
    x = m.imprecision_crosstab(recs)
    assert x["table"]["precise"] == {"supported": 1}
    assert x["table"]["imprecise"] == {"neutral": 1, "not_testable": 1}
    assert x["n"] == 2 and x["percent_agreement"] == 1.0 and x["cohens_kappa"] == 1.0


def test_cluster_bootstrap_point_matches_pooled_mean():
    ci = m.cluster_bootstrap_ci([1, 0, 1, 1], ["a", "a", "b", "c"], n_boot=200)
    assert ci["point"] == 0.75 and ci["n_clusters"] == 3 and ci["lo"] <= ci["hi"]
