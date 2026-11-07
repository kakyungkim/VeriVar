"""Unit tests for the pre-registered sop_strict_v2 family (engine + offline input parsing).

Synthetic inputs only; no benchmark result is computed here."""
import dataclasses

import pytest

from scripts.fetch_vicc_v2_inputs import calibrate, parse_hgvs_pro
from src.classify.vicc_inputs import (aa_matches, parse_vep_v2_record, pop_max5,
                                      variant_inputs, v2_key)
from src.classify.vicc_rules import (CONFIGS, PREDICTOR_THRESHOLDS, V2_FAMILY,
                                     VICCPointClassifier)

V2 = "sop_strict_v2"


def codes(res):
    return {c.code for c in res.criteria}


def clf(config=V2):
    return VICCPointClassifier(hotspots={}, config=config)


# ---- configuration integrity ------------------------------------------------------------

def test_legacy_configs_unchanged_by_new_fields():
    for name in ("sop_strict", "os2_fixed", "original"):
        c = CONFIGS[name]
        assert c.comp_predictors == ("alphamissense",)
        assert c.comp_thresholds == "am_developer"
        assert c.pop_af_mode == "overall"
        assert (c.civic_inputs, c.dms_inputs) == ("v1", "v1")


def test_v2_is_sop_strict_plus_prereg_changes_only():
    base, v2 = CONFIGS["sop_strict"], CONFIGS[V2]
    diff = {f.name for f in dataclasses.fields(base)
            if getattr(base, f.name) != getattr(v2, f.name)}
    assert diff == {"name", "description", "comp_predictors", "comp_thresholds",
                    "pop_af_mode", "civic_inputs", "dms_inputs"}
    assert v2.comp_predictors == ("alphamissense", "revel", "cadd_phred")
    assert v2.om1_scope == "site"                 # OM1 broadening is sensitivity only


def test_prereg_thresholds_literal():
    t = PREDICTOR_THRESHOLDS["clingen"]
    assert (t["alphamissense"].onco, t["alphamissense"].benign) == (0.792, 0.169)
    assert (t["revel"].onco, t["revel"].benign) == (0.644, 0.290)
    assert (t["cadd_phred"].onco, t["cadd_phred"].benign) == (25.3, 22.7)
    assert (t["sift"].onco, t["sift"].benign, t["sift"].higher_is_onco) == (0.001, 0.080, False)
    assert (t["polyphen"].onco, t["polyphen"].benign) == (0.978, 0.113)


def test_v2_family_names():
    assert set(V2_FAMILY) == {
        "sop_strict_v2", "sop_strict_v2_5pred", "sop_strict_v2_revel", "sop_strict_v2_devcut",
        "sop_strict_v2_om1domain", "abl_strict_plus_a", "abl_strict_plus_a0",
        "abl_strict_plus_b", "abl_strict_plus_c1", "abl_strict_plus_c2", "abl_v2_minus_a",
        "abl_v2_minus_b", "abl_v2_minus_c1", "abl_v2_minus_c2"}


def test_legacy_config_ignores_v2_inputs():
    """sop_strict must give identical output whether or not v2 inputs are passed."""
    kw = dict(am_pathogenicity=0.2, gnomad_af=0.0)
    a = clf("sop_strict").score("TP53", "p.R175H", **kw)
    b = clf("sop_strict").score("TP53", "p.R175H", predictors={"revel": 0.99, "cadd_phred": 35},
                                pop_af_max5=0.2, **kw)
    assert (a.points, [c.code for c in a.criteria]) == (b.points, [c.code for c in b.criteria])
    assert "SBP1" in codes(a)


# ---- change a: all utilised lines must agree ----------------------------------------------

def test_op1_requires_all_lines_onco():
    r = clf().score("TP53", "p.R175H", am_pathogenicity=0.95,
                    predictors={"revel": 0.9, "cadd_phred": 30})
    assert "OP1" in codes(r)
    op1 = next(c for c in r.criteria if c.code == "OP1")
    assert op1.points == 1 and "AlphaMissense" in op1.source and "CADD" in op1.source


def test_disagreement_or_indeterminate_gives_no_code():
    c = clf()
    # AM onco, REVEL benign -> disagreement
    assert not codes(c.score("TP53", "p.R175H", am_pathogenicity=0.95,
                             predictors={"revel": 0.2, "cadd_phred": 30})) & {"OP1", "SBP1"}
    # CADD indeterminate (between 22.7 and 25.3)
    assert not codes(c.score("TP53", "p.R175H", am_pathogenicity=0.95,
                             predictors={"revel": 0.9, "cadd_phred": 24.0})) & {"OP1", "SBP1"}
    # AM 0.6 is OP1 under the legacy developer cut but indeterminate at ClinGen (<0.792)
    assert not codes(c.score("TP53", "p.R175H", am_pathogenicity=0.6,
                             predictors={"revel": 0.9, "cadd_phred": 30})) & {"OP1", "SBP1"}


def test_sbp1_requires_all_lines_benign_and_counts_once():
    r = clf().score("KRAS", "p.R164Q", am_pathogenicity=0.1,
                    predictors={"revel": 0.1, "cadd_phred": 15})
    assert [c.code for c in r.criteria].count("SBP1") == 1
    # AlphaMissense 0.30 is benign under the legacy cut but indeterminate at ClinGen (>0.169)
    r2 = clf().score("KRAS", "p.R164Q", am_pathogenicity=0.30,
                     predictors={"revel": 0.1, "cadd_phred": 15})
    assert "SBP1" not in codes(r2)


def test_missing_lines_are_not_utilised():
    r = clf().score("TP53", "p.R175H", am_pathogenicity=None,
                    predictors={"revel": None, "cadd_phred": 30})
    assert "OP1" in codes(r)                       # CADD is the only utilised line
    assert not codes(clf().score("TP53", "p.R175H")) & {"OP1", "SBP1"}


def test_sensitivity_predictor_sets():
    kw = dict(am_pathogenicity=0.95, predictors={"revel": 0.9, "cadd_phred": 30,
                                                 "sift": 0.3, "polyphen": 0.99})
    assert "OP1" in codes(clf().score("TP53", "p.R175H", **kw))
    assert "OP1" not in codes(clf("sop_strict_v2_5pred").score("TP53", "p.R175H", **kw))  # SIFT
    only_revel = clf("sop_strict_v2_revel").score("TP53", "p.R175H", am_pathogenicity=0.1,
                                                  predictors={"revel": 0.9, "cadd_phred": 5})
    assert "OP1" in codes(only_revel)
    dev = clf("sop_strict_v2_devcut").score("TP53", "p.R175H", am_pathogenicity=0.6,
                                            predictors={"revel": 0.55, "cadd_phred": 21})
    assert "OP1" in codes(dev)
    dev_b = clf("sop_strict_v2_devcut").score("TP53", "p.R175H", am_pathogenicity=0.3,
                                              predictors={"revel": 0.49, "cadd_phred": 19.9})
    assert "SBP1" in codes(dev_b)


def test_ablation_a0_is_am_only_at_clingen():
    c = clf("abl_strict_plus_a0")
    assert "OP1" in codes(c.score("TP53", "p.R175H", am_pathogenicity=0.95,
                                  predictors={"revel": 0.1}))       # REVEL not utilised
    assert "OP1" not in codes(c.score("TP53", "p.R175H", am_pathogenicity=0.7))


# ---- change b: continental maximum, strict > ----------------------------------------------

def test_continental_population_codes():
    c = clf()
    assert "SBVS1" in codes(c.score("TP53", "p.P72R", pop_af_max5=0.30, gnomad_af=0.001))
    assert "SBS1" in codes(c.score("TP53", "p.P72R", pop_af_max5=0.02, gnomad_af=0.001))
    assert not codes(c.score("TP53", "p.P72R", pop_af_max5=0.05)) & {"SBVS1"}   # strict >
    assert "SBS1" in codes(c.score("TP53", "p.P72R", pop_af_max5=0.05))
    assert not codes(c.score("TP53", "p.P72R", pop_af_max5=0.01)) & {"SBS1", "SBVS1"}
    # overall AF is ignored for SBVS1/SBS1 in v2 ...
    assert not codes(c.score("TP53", "p.P72R", gnomad_af=0.2)) & {"SBS1", "SBVS1"}
    # ... but still drives OP4 (unchanged input)
    assert "OP4" in codes(c.score("TP53", "p.P72R", gnomad_af=0.0, pop_af_max5=0.0))


def test_pop_max5_uses_only_the_five_sop_populations():
    freqs = {"gnomade_fin": 0.2, "gnomadg_asj": 0.3, "gnomade_nfe": 0.001,
             "gnomadg_afr": 0.02, "gnomade": 0.1}
    assert pop_max5(freqs) == (0.02, "gnomadg_afr")
    assert pop_max5({}) == (0.0, None)


# ---- input parsing ----------------------------------------------------------------------

def _rec():
    return {"input": "7 140753336 . A T . . .", "allele_string": "A/T",
            "most_severe_consequence": "missense_variant",
            "colocated_variants": [{"frequencies": {"T": {"gnomade_sas": 1.2e-5,
                                                          "gnomade_fin": 0.5}}}],
            "transcript_consequences": [
                {"transcript_id": "ENST0002", "gene_symbol": "BRAF", "amino_acids": "V/E",
                 "revel": 0.931, "cadd_phred": 29.8},
                {"transcript_id": "ENST0001", "gene_symbol": "BRAF", "amino_acids": "V/E",
                 "revel": 0.930, "cadd_phred": 29.8},
                {"transcript_id": "ENST0009", "gene_symbol": "BRAF", "amino_acids": "V/E",
                 "mane_select": "NM_004333.6", "canonical": 1, "protein_start": 600,
                 "sift_score": 0, "polyphen_score": 0.935, "cadd_phred": 29.8,
                 "alphamissense": {"am_pathogenicity": 0.9927}},
                {"transcript_id": "ENST0003", "gene_symbol": "OTHER", "amino_acids": "V/E",
                 "revel": 0.1}]}


def test_parse_vep_v2_record_transcript_rules():
    a = parse_vep_v2_record(_rec(), "BRAF")
    assert a["main_is_mane"] and a["main_transcript"] == "ENST0009"
    assert (a["sift"], a["polyphen"], a["cadd_phred"], a["am_vep"]) == (0, 0.935, 29.8, 0.9927)
    assert a["revel"] == 0.930 and a["revel_transcript"] == "ENST0001"   # first by id
    assert a["revel_n_distinct"] == 2
    assert a["pop_max5"] == 1.2e-5 and a["pop_max5_source"] == "gnomade_sas"  # fin ignored


def test_aa_match_masks_transcript_level_predictors():
    assert aa_matches("p.V600E", "V/E", 600)
    assert not aa_matches("p.V600E", "V/E", 601)
    vep = {v2_key("chr7", 140753336, "A", "T"): parse_vep_v2_record(_rec(), "BRAF")}
    ok = variant_inputs({"gene": "BRAF", "aa": "p.V600E", "chrom": "7", "pos": 140753336,
                         "ref": "A", "alt": "T"}, vep)
    assert ok["aa_match"] and ok["predictors"]["revel"] == 0.930
    bad = variant_inputs({"gene": "BRAF", "aa": "p.V601E", "chrom": "7", "pos": 140753336,
                          "ref": "A", "alt": "T"}, vep)
    assert not bad["aa_match"]
    assert bad["predictors"]["revel"] is None and bad["predictors"]["cadd_phred"] == 29.8
    missing = variant_inputs({"gene": "BRAF", "aa": "p.V600E", "chrom": "1", "pos": 1,
                              "ref": "A", "alt": "T"}, vep)
    assert missing["pop_af_max5"] is None and not missing["vep_returned"]


# ---- MaveDB calibration (existing PTEN method, direction-general) -------------------------

def _rows(miss_lo=True):
    rows = []
    for i in range(1, 61):                       # 60 missense, mostly WT-like
        s = 1.0 if i > 10 else 0.0
        rows.append((f"p.Ala{i}Val", s if miss_lo else 1.0 - s))
    for i in range(1, 13):                       # 12 nonsense
        rows.append((f"p.Ala{i}Ter", 0.0 if miss_lo else 1.0))
    rows.append(("p.Ala5=", 1.0 if miss_lo else 0.0))
    return rows


def test_parse_hgvs_pro():
    assert parse_hgvs_pro("p.Thr131Ile") == ("T", 131, "I")
    assert parse_hgvs_pro("NP_000537.3:p.(Arg175His)") == ("R", 175, "H")
    assert parse_hgvs_pro("p.Arg12=") == ("R", 12, "=")
    assert parse_hgvs_pro("p.Arg12Ter") == ("R", 12, "*")
    assert parse_hgvs_pro("_wt") is None


def test_calibrate_low_and_high_lof_sides():
    seq = "A" * 100
    lo = calibrate(_rows(True), seq)
    assert lo["summary"]["eligible"] and lo["summary"]["lof_side"] == "low"
    assert set(lo["lof"]) == {f"A{i}V" for i in range(1, 11)}
    hi = calibrate(_rows(False), seq)
    assert hi["summary"]["lof_side"] == "high" and set(hi["lof"]) == set(lo["lof"])


def test_calibrate_exclusions():
    assert not calibrate(_rows(True), "C" * 100)["summary"]["eligible"]     # numbering
    few = [r for r in _rows(True) if not r[0].endswith("Ter")][:30]
    assert not calibrate(few, "A" * 100)["summary"]["eligible"]
    inverted = _rows(True)[:-1] + [("p.Ala5=", 0.0)]
    s = calibrate(inverted, "A" * 100)["summary"]
    assert not s["eligible"] and "synonymous" in s["reason"]


@pytest.mark.parametrize("name", sorted(V2_FAMILY))
def test_every_v2_config_scores(name):
    r = VICCPointClassifier(hotspots={}, config=name).score(
        "TP53", "p.R175H", am_pathogenicity=0.95, predictors={"revel": 0.9, "cadd_phred": 30},
        pop_af_max5=0.0, gnomad_af=0.0)
    assert r.points >= 1


def test_provider_without_coordinates_gives_no_v2_inputs():
    from src.classify.vicc_inputs import V2InputProvider
    legacy = V2InputProvider(CONFIGS["sop_strict"])
    assert legacy.kwargs("TP53", "p.R175H") == {}
    v2 = V2InputProvider(CONFIGS[V2], vep={"x": {}})
    kw = v2.kwargs("TP53", "p.R175H")
    assert kw == {"predictors": {}, "pop_af_max5": None} and v2.n_missing == 1
    r = clf().score("TP53", "p.R175H", am_pathogenicity=0.95, **kw)
    assert "OP1" in codes(r)          # AlphaMissense is the only utilised line
