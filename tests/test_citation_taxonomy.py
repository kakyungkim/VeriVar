"""Offline tests for the arm-independent citation taxonomy (stubbed lookup cache)."""
import pytest

from src.eval.citation_taxonomy import (CitationCategory as C, VariantInput,
                                        classify_token, classify_variants,
                                        existence_only_category, is_placeholder_number,
                                        parse_token, variant_flags)
from src.eval.stats import clopper_pearson_ci, wilson_ci, zero_event_upper_bound

CACHE = {
    "pmid": {
        "12345678": {"exists": True, "title": "Denpasar Declaration on Population", "abstract": None},
        "87654321": {"exists": False, "title": None},
        "29514012": {"exists": False, "title": None},
        "19474124": {"exists": True, "title": "Carotid angioplasty with stenting",
                     "abstract": "Cerebral perfusion after stenting."},
        "31415": {"exists": True, "title": "BRAF V600E drives melanoma", "abstract": ""},
        "27182": {"exists": True, "title": "Mutant p53 gain of function", "abstract": ""},
    },
    "clinvar": {"123456": {"exists": False, "title": None, "genes": []}},
}
BUNDLE = ["CIViC:EID6003", "AlphaMissense:7:140481402C>T"]
SOURCES = {"CIViC:EID6003": "CIViC", "AlphaMissense:7:140481402C>T": "AlphaMissense"}


def _cls(tok, gene="BRAF", hgvsp="p.V600E", bundle=BUNDLE, sources=SOURCES):
    return classify_token(tok, variant_index=0, variant_id="v", gene=gene, hgvsp=hgvsp,
                          bundle_ids=bundle, bundle_sources=sources, cache=CACHE)


@pytest.mark.parametrize("num,exp", [("123456", True), ("12345678", True), ("87654321", True),
                                     ("789012", True), ("345678", True), ("000123456", True),
                                     ("111111", True), ("123", False), ("19474124", False),
                                     ("29514012", False)])
def test_placeholder_pattern(num, exp):
    assert is_placeholder_number(num) is exp


@pytest.mark.parametrize("tok,kind", [
    ("PMID: 123", "pmid"), ("PMID123", "pmid"), ("ClinVar: VCV000123456", "clinvar"),
    ("EID6003", "civic_eid"), ("CIViC:EID6003", "civic_eid"), ("NCT01234567", "nct"),
    ("7:140481402C>T", "coordinate"), ("AlphaMissense:7:140481402C>T", "coordinate"),
    ("ClinGen: 123456", "unschemed_numeric"), ("CGC: 789012", "unschemed_numeric"),
    ("ClinGen: BRAF", "non_identifier"), ("ClinGen", "non_identifier"),
    ("AlphaMissense", "non_identifier"), ("123", "non_identifier"), ("1", "non_identifier"),
    ("OP1", "non_identifier"),
])
def test_parse_token(tok, kind):
    assert parse_token(tok).kind == kind


def test_in_bundle_exact_and_normalized():
    assert _cls("CIViC:EID6003").category == C.IN_BUNDLE
    r = _cls("7:140481402C>T")
    assert r.category == C.IN_BUNDLE and r.resolved_bundle_id == "AlphaMissense:7:140481402C>T"


def test_non_identifiers_same_rule_with_or_without_bundle():
    # bare source name: d in both arms; flagged resolvable only when a bundle names it
    with_bundle = _cls("AlphaMissense")
    no_bundle = _cls("AlphaMissense", bundle=[], sources={})
    assert with_bundle.category == no_bundle.category == C.NON_IDENTIFIER
    assert with_bundle.uniquely_resolvable_in_bundle and not no_bundle.uniquely_resolvable_in_bundle
    for tok in ("1", "123", "OP1", "ClinGen: BRAF", "CGC"):
        assert _cls(tok).category == C.NON_IDENTIFIER
        assert _cls(tok, bundle=[], sources={}).category == C.NON_IDENTIFIER


def test_placeholder_is_fabricated_even_if_record_exists():
    r = _cls("PMID: 12345678", bundle=[])
    assert r.category == C.FABRICATED and "placeholder_pattern" in r.reasons
    assert r.record_exists is True
    # existence-only sensitivity re-bins it by relevance
    assert existence_only_category(r) == C.REAL_UNRELATED


def test_unschemed_numeric_and_no_record():
    assert _cls("ClinGen: 123456", bundle=[]).category == C.FABRICATED
    r = _cls("PMID: 29514012", bundle=[])
    assert r.category == C.FABRICATED and r.reasons == ["no_record"]
    assert _cls("ClinVar: VCV000123456", bundle=[]).category == C.FABRICATED


def test_real_pmid_relevance_by_gene_and_alias():
    assert _cls("PMID: 19474124", bundle=[]).category == C.REAL_UNRELATED
    rel = _cls("PMID: 31415", bundle=[])
    assert rel.category == C.REAL_RELATED and rel.mentions_protein_change
    assert _cls("PMID: 27182", gene="TP53", hgvsp="p.R175H", bundle=[]).category == C.REAL_RELATED


def test_unchecked_when_not_cached():
    assert _cls("PMID: 16180", bundle=[]).category == C.UNCHECKED
    # an out-of-bundle EID has no lookup table -> unchecked, never silently in-bundle
    assert _cls("EID4817").category == C.UNCHECKED


def test_variant_flags():
    vs = [VariantInput(variant_index=0, variant_id="a", gene="BRAF", hgvsp="p.V600E",
                       citations=["PMID: 19474124"]),
          VariantInput(variant_index=1, variant_id="b", gene="KRAS", hgvsp="p.G12D",
                       citations=["PMID: 12345678", "123"]),
          VariantInput(variant_index=2, variant_id="c", gene="KRAS", hgvsp="p.G12D",
                       citations=["ClinGen: KRAS"]),
          VariantInput(variant_index=3, variant_id="d", gene="KRAS", hgvsp="p.G12D",
                       citations=[])]
    rows = variant_flags(vs, classify_variants(vs, CACHE))
    assert [r["any_fabricated"] for r in rows] == [False, True, False, False]
    assert [r["any_fabricated_or_misattributed"] for r in rows] == [True, True, False, False]
    assert [r["any_non_identifier"] for r in rows] == [False, True, True, False]
    assert [r["any_citation"] for r in rows] == [True, True, True, False]


def test_boundary_intervals():
    w = wilson_ci(37, 37)
    cp = clopper_pearson_ci(37, 37)
    assert w["hi"] == 1.0 and 0.90 < w["lo"] < 0.92
    assert cp["hi"] == 1.0 and cp["lo"] == pytest.approx(0.905, abs=0.001)
    assert clopper_pearson_ci(0, 10)["lo"] == 0.0
    z = zero_event_upper_bound(101)
    assert z["clopper_pearson_upper"] == pytest.approx(0.0292, abs=1e-4)
    assert z["rule_of_three_upper"] == pytest.approx(0.0297, abs=1e-4)


# --- 2026-09-27: PMID-backed bundle membership and the two no-retrieval definitions ---

BACKING = {"CIViC:EID6003": ["18794803"], "AlphaMissense:7:140481402C>T": []}


def test_pmid_backing_a_bundle_item_is_in_bundle():
    r = classify_token("PMID: 18794803", variant_index=0, variant_id="v", gene="BRAF",
                       hgvsp="p.G469E", bundle_ids=BUNDLE, bundle_sources=SOURCES,
                       cache=CACHE, bundle_pmids=BACKING)
    assert r.category == C.IN_BUNDLE
    assert r.resolved_bundle_id == "CIViC:EID6003#PMID18794803"
    # without the backing map the same token is out of bundle (and unchecked here)
    assert _cls("PMID: 18794803").category == C.UNCHECKED


def test_reference_bundle_only_moves_tokens_into_a():
    """Definition E (empty) vs R (reference bundle): fabricated tokens never move."""
    toks = ["PMID: 18794803", "PMID: 12345678", "ClinGen: 123456", "123", "EID6003"]
    e = VariantInput(variant_index=0, variant_id="v", gene="BRAF", hgvsp="p.G469E",
                     citations=toks)
    r = e.model_copy(update={"bundle_ids": BUNDLE, "bundle_sources": SOURCES,
                             "bundle_pmids": BACKING})
    ce = [x.category for x in classify_variants([e], CACHE)]
    cr = [x.category for x in classify_variants([r], CACHE)]
    assert ce == [C.UNCHECKED, C.FABRICATED, C.FABRICATED, C.NON_IDENTIFIER, C.UNCHECKED]
    assert cr == [C.IN_BUNDLE, C.FABRICATED, C.FABRICATED, C.NON_IDENTIFIER, C.IN_BUNDLE]


def _stub_inputs():
    """Two-variant stub of the three committed outputs."""
    evs = [{"id": "CIViC:EID6003", "source": "CIViC", "pmids": ["18794803"]},
           {"id": "AlphaMissense:7:140481402C>T", "source": "AlphaMissense", "pmids": []}]
    cohort = {"variants": [
        {"variant_key": "BRAF p.G469E", "cancer_type": "Melanoma", "gene": "BRAF",
         "hgvsp": "p.G469E", "bundle": {"evidences": evs},
         "mode_a": {"citations": ["CIViC:EID6003"]}},
        {"variant_key": "TP53 p.R175H", "cancer_type": "Breast", "gene": "TP53",
         "hgvsp": "p.R175H", "bundle": {"evidences": []}, "mode_a": {"citations": []}}]}
    label_only = {"results": [
        {"variant_key": "BRAF p.G469E", "cancer_type": "Melanoma",
         "per_model": {"gpt-4o-mini": {"cited_ids": ["EID6003", "AlphaMissense", "1"]}}},
        {"variant_key": "TP53 p.R175H", "cancer_type": "Breast",
         "per_model": {"gpt-4o-mini": {"cited_ids": []}}}]}
    ablation = {"n": 2, "faithfulness": {"norag_ungrounded_citations": 2}, "rows": [
        {"variant_key": "BRAF p.G469E", "norag_citations": ["PMID: 12345678", "ClinGen"]},
        {"variant_key": "TP53 p.R175H", "norag_citations": ["PMID: 19474124"]}]}
    return cohort, label_only, ablation


def test_build_arms_and_headline_on_stub():
    from scripts.run_citation_taxonomy import (ARMS, build_arms, headline,
                                               paired_contrasts, summarise_arm)
    cohort, label_only, ablation = _stub_inputs()
    arms = build_arms(cohort, label_only, ablation)
    assert tuple(arms) == ARMS
    rep = {n: summarise_arm(v, classify_variants(v, CACHE)) for n, v in arms.items()}
    rag = rep["retrieval_gpt4o_mini_106"]
    assert rag["citation_counts"]["a_in_bundle"] == 1
    assert rag["citation_counts"]["d_non_identifier"] == 2
    assert rag["identifier_bearing"]["n_out_of_bundle"] == 0
    assert rag["identifier_bearing_plus_uniquely_resolvable_source_names"]["n_citations"] == 2
    nr = rep["no_retrieval_E_empty_bundle"]
    assert nr["variant_level"]["any_citation"]["k"] == 2          # old-style "ungrounded" count
    assert nr["variant_level"]["any_fabricated"]["k"] == 1        # placeholder PMID
    assert nr["variant_level"]["any_fabricated_or_misattributed"]["k"] == 2  # + unrelated PMID
    h = headline(rep, paired_contrasts({n: r["variants"] for n, r in rep.items()}), {})
    assert h["no_retrieval_definitions_agree"] is True
    assert h["arms"]["no_retrieval_R_reference_bundle"]["variant_any_fabricated_identifier"][
        "k"] == 1
    assert h["arms"]["retrieval_gpt4o_mini_106"]["identifier_tokens_out_of_bundle"][
        "zero_event_bound_citation_level"]["n"] == 1


def test_build_arms_rejects_misaligned_inputs():
    from scripts.run_citation_taxonomy import build_arms
    cohort, label_only, ablation = _stub_inputs()
    ablation["rows"].reverse()
    with pytest.raises(ValueError):
        build_arms(cohort, label_only, ablation)
