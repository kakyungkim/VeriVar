"""Unit tests for the VICC point engine (src.classify.vicc_rules)."""
from src.classify.vicc_rules import (
    CONFIGS, PRIMARY_CONFIG, TUMOUR_SUPPRESSORS, V2_FAMILY, CivicSignal, VICCPointClassifier,
    civic_signal_from_rows, classify_points, domain_feature_at, grantham, parse_protein_change,
)
from src.models.standards import VICCOncogenicity as O


def test_parse_protein_change():
    assert parse_protein_change("p.V600E") == ("V", 600, "E")
    assert parse_protein_change("R130*") == ("R", 130, "*")
    assert parse_protein_change("nonsense") is None


def test_point_thresholds():
    assert classify_points(10) is O.ONCOGENIC
    assert classify_points(6) is O.LIKELY_ONCOGENIC
    assert classify_points(5) is O.VUS
    assert classify_points(0) is O.VUS
    assert classify_points(-1) is O.LIKELY_BENIGN
    assert classify_points(-7) is O.BENIGN


def test_ovs1_null_in_tsg():
    clf = VICCPointClassifier(hotspots={})
    assert "TP53" in TUMOUR_SUPPRESSORS
    res = clf.score("TP53", "p.R213*")
    assert any(c.code == "OVS1" for c in res.criteria)
    # OVS1 alone = 8 points -> Likely Oncogenic (6-9); Oncogenic needs >=10.
    assert res.points >= 8 and res.oncogenicity is O.LIKELY_ONCOGENIC
    assert res.citation_ids() == ["VICC:OVS1"]            # criteria are citable


def test_hotspot_drives_oncogenic():
    clf = VICCPointClassifier(hotspots={"BRAF": {"600": {"E": 833}}})
    res = clf.score("BRAF", "p.V600E", am_pathogenicity=0.99, gnomad_af=0.0)
    codes = {c.code for c in res.criteria}
    assert "OS3" in codes and "OP1" in codes and "OP4" in codes      # 4 + 1 + 1 = 6
    assert res.oncogenicity in (O.ONCOGENIC, O.LIKELY_ONCOGENIC)


def test_gnomad_common_is_benign():
    clf = VICCPointClassifier(hotspots={})
    res = clf.score("BRAF", "p.A31G", am_pathogenicity=0.2, gnomad_af=0.12)
    assert any(c.code == "SBVS1" for c in res.criteria)
    assert res.oncogenicity in (O.BENIGN, O.LIKELY_BENIGN)


def test_lone_sbp1_stays_vus():
    """Legacy (non-SOP) guard, kept in the os2_fixed/original sensitivity configs only."""
    clf = VICCPointClassifier(hotspots={}, config="os2_fixed")
    res = clf.score("BRAF", "p.P14R", am_pathogenicity=0.1)   # SBP1 only -> -1
    assert {c.code for c in res.criteria} == {"SBP1"}
    assert res.oncogenicity is O.VUS


def test_lone_sbs2_stays_vus():
    """A single functional-neutral line (DMS SBS2, -4) without populational support
    is too weak for Likely Benign -> abstain to VUS (generalises the SBP1 guard;
    fixes e.g. TP53 G334R where the DMS classifier mislabels a non-DBD residue)."""
    clf = VICCPointClassifier(hotspots={}, config="os2_fixed")
    res = clf.score("TP53", "p.G334R", functional_neutral=True)   # SBS2 only -> -4
    assert {c.code for c in res.criteria} == {"SBS2"}
    assert res.oncogenicity is O.VUS


def test_two_benign_lines_reach_likely_benign():
    """Two independent benign lines (SBS2 + SBP1) DO reach Likely Benign — the guard
    only abstains on a single lone benign line."""
    clf = VICCPointClassifier(hotspots={})
    res = clf.score("TP53", "p.P36L", am_pathogenicity=0.1, functional_neutral=True)
    assert {c.code for c in res.criteria} == {"SBS2", "SBP1"}    # -4 + -1 = -5
    assert res.oncogenicity is O.LIKELY_BENIGN


def test_os1_known_oncogenic_lever():
    """The optional OS1 lever (established-oncogenic, off by default) adds +4 and is citable
    (legacy config, where OS1 does not trigger the SOP exclusions)."""
    clf = VICCPointClassifier(hotspots={}, config="os2_fixed")
    base = clf.score("RB1", "p.R661W", am_pathogenicity=0.9, in_domain="Pocket")
    boosted = clf.score("RB1", "p.R661W", am_pathogenicity=0.9, in_domain="Pocket",
                        known_oncogenic=True)
    assert boosted.points == base.points + 4
    os1 = [c for c in boosted.criteria if c.code == "OS1"]
    assert os1 and os1[0].id == "VICC:OS1"             # citable
    assert base.oncogenicity is O.VUS and boosted.oncogenicity is O.LIKELY_ONCOGENIC


def test_residue_hotspot_flag_tiers_on_residue_total():
    """residue_hotspot=True tiers OS3/OM3 on total residue recurrence, not the alt count."""
    hot = {"FLT3": {"835": {"Y": 11, "E": 3, "H": 2, "V": 1}}}   # alt E=3, residue total=17
    alt = VICCPointClassifier(hotspots=hot, residue_hotspot=False)
    res = VICCPointClassifier(hotspots=hot, residue_hotspot=True)
    assert any(c.code == "OP3" for c in alt.score("FLT3", "p.D835E").criteria)   # alt=3 -> OP3
    assert any(c.code == "OM3" for c in res.score("FLT3", "p.D835E").criteria)   # total=17 -> OM3


def test_functional_lof_adds_os2():
    clf = VICCPointClassifier(hotspots={})
    base = clf.score("PTEN", "p.T131I", am_pathogenicity=0.9, in_domain="Phosphatase")
    boosted = clf.score("PTEN", "p.T131I", am_pathogenicity=0.9, in_domain="Phosphatase",
                        functional_lof=True)
    assert boosted.points >= base.points + 4
    assert any(c.code == "OS2" for c in boosted.criteria)


# ---- CIViC -> VICC code mapping (SOP: only functional studies grant OS2/SBS2) ----------

def _civ(eid, etype, sig, level="B", direction="Supports", cit=None, mp="EGFR C797S"):
    return {"molecular_profile": mp, "evidence_id": str(eid), "evidence_type": etype,
            "evidence_direction": direction, "significance": sig, "evidence_level": level,
            "citation_id": str(cit if cit is not None else 1000 + eid)}


def test_clinical_evidence_never_grants_os2():
    """Resistance, Sensitivity, Prognostic, Adverse Response, Diagnostic and Predisposing
    evidence (even level A/B, many items) are not oncogenicity evidence under the SOP."""
    rows = [_civ(1, "Predictive", "Resistance", "A"),
            _civ(2, "Predictive", "Sensitivity/Response", "A"),
            _civ(3, "Prognostic", "Poor Outcome", "B"),
            _civ(4, "Predictive", "Adverse Response", "B"),
            _civ(5, "Diagnostic", "Positive", "B"),
            _civ(6, "Predisposing", "Predisposition", "B")]
    sig = civic_signal_from_rows(rows, "EGFR", "C", 797, "S")
    assert sig.onco_citations == 0 and sig.benign_citations == 0
    assert sum(sig.ignored.values()) == 6
    clf = VICCPointClassifier(hotspots={})
    res = clf.score("EGFR", "p.C797S", civic=sig)
    assert not any(c.code.startswith(("OS2", "OM4", "SBS2")) for c in res.criteria)
    assert res.points == 0 and res.oncogenicity is O.VUS


def test_prognostic_level_b_no_longer_os2_tp53_r273h_pattern():
    """The TP53 R273H pattern (level-B Poor Outcome) used to grant OS2 (+4)."""
    rows = [_civ(10, "Prognostic", "Poor Outcome", "B", mp="TP53 R273H")]
    sig = civic_signal_from_rows(rows, "TP53", "R", 273, "H")
    res = VICCPointClassifier(hotspots={}).score("TP53", "p.R273H", civic=sig)
    assert res.points == 0


def test_functional_two_citations_grants_full_os2():
    rows = [_civ(20, "Functional", "Gain of Function", "D", cit=111),
            _civ(21, "Functional", "Loss of Function", "D", cit=222)]
    sig = civic_signal_from_rows(rows, "EGFR", "C", 797, "S")
    assert sig.onco_citations == 2
    res = VICCPointClassifier(hotspots={}).score("EGFR", "p.C797S", civic=sig)
    os2 = [c for c in res.criteria if c.code == "OS2"]
    assert os2 and os2[0].points == 4 and "EID20" in os2[0].statement   # citable
    assert os2[0].source == "CIViC"


def test_functional_level_a_b_grants_os2_when_replicated():
    """Level A/B functional evidence grants OS2 (strength follows replication, not level)."""
    rows = [_civ(22, "Functional", "Loss of Function", "A", cit=1),
            _civ(23, "Functional", "Loss of Function", "B", cit=2)]
    sig = civic_signal_from_rows(rows, "EGFR", "C", 797, "S")
    res = VICCPointClassifier(hotspots={}).score("EGFR", "p.C797S", civic=sig)
    assert any(c.code == "OS2" and c.points == 4 for c in res.criteria)


def test_single_functional_citation_downgrades_to_moderate():
    """One study = SOP-permitted downgrade: OS2_Moderate (+2). Two items from the SAME
    paper still count as one independent citation."""
    rows = [_civ(30, "Functional", "Gain of Function", "D", cit=555),
            _civ(31, "Functional", "Loss of Function", "D", cit=555)]
    sig = civic_signal_from_rows(rows, "EGFR", "C", 797, "S")
    assert len(sig.onco_eids) == 2 and sig.onco_citations == 1
    res = VICCPointClassifier(hotspots={}).score("EGFR", "p.C797S", civic=sig)
    assert [c.code for c in res.criteria if c.code.startswith("OS2")] == ["OS2_Moderate"]
    assert res.points == 2              # SOP-strict: no OP4 without population data
    legacy = VICCPointClassifier(hotspots={}, config="os2_fixed").score("EGFR", "p.C797S",
                                                                         civic=sig)
    assert legacy.points == 2 + 1       # legacy: + approximated OP4


def test_oncogenic_type_counts_only_at_preclinical_level():
    """CIViC 'Oncogenic' evidence is a functional study only at level D (in vitro/in vivo);
    level B/C items (patient observations) grant nothing."""
    rows = [_civ(40, "Oncogenic", "Oncogenicity", "B", cit=1),
            _civ(41, "Oncogenic", "Oncogenicity", "C", cit=2)]
    assert civic_signal_from_rows(rows, "EGFR", "C", 797, "S").onco_citations == 0
    rows.append(_civ(42, "Oncogenic", "Oncogenicity", "D", cit=3))
    assert civic_signal_from_rows(rows, "EGFR", "C", 797, "S").onco_eids == ["42"]


def test_functional_benign_maps_to_sbs2_and_clinical_negative_does_not():
    rows = [_civ(50, "Functional", "Unaltered Function", "D", cit=1),
            _civ(51, "Oncogenic", "Oncogenicity", "D", direction="Does Not Support", cit=2),
            _civ(52, "Diagnostic", "Negative", "B", cit=3)]       # clinical: ignored
    sig = civic_signal_from_rows(rows, "EGFR", "C", 797, "S")
    assert sig.benign_eids == ["50", "51"] and sig.benign_citations == 2
    res = VICCPointClassifier(hotspots={}).score("EGFR", "p.C797S", civic=sig)
    assert any(c.code == "SBS2" and c.points == -4 for c in res.criteria)


def test_civic_exact_variant_only():
    rows = [_civ(60, "Functional", "Gain of Function", "D", mp="PIK3CA H1047R")]
    assert civic_signal_from_rows(rows, "PIK3CA", "H", 1047, "Q").n_matched == 0
    assert civic_signal_from_rows(rows, "PIK3CA", "H", 1047, "R").n_matched == 1


def test_dms_and_civic_os2_not_double_counted():
    sig = CivicSignal(onco_eids=["1", "2"], onco_citations=2)
    res = VICCPointClassifier(hotspots={}).score("PTEN", "p.T131I", functional_lof=True,
                                                  civic=sig)
    assert sum(c.code.startswith("OS2") for c in res.criteria) == 1


# ---- OM4 per the SOP (opt-in; the evaluation scripts do not supply it) ---------------

def test_grantham_matches_sop_example():
    assert grantham("R", "H") == 29 and grantham("R", "C") == 180
    assert grantham("L", "I") == 5 and grantham("C", "W") == 215 and grantham("A", "A") == 0


def test_om4_sop_definition():
    clf = VICCPointClassifier(hotspots={})
    # SOP example: p.Arg156His oncogenic, p.Arg156Cys observed (Grantham 180 >= 29) -> OM4.
    res = clf.score("TP53", "p.R156C", residue_oncogenic_alts=["H"])
    assert [c.code for c in res.criteria if c.code == "OM4"] == ["OM4"]
    # Reverse direction (His less distant than Cys) -> no OM4.
    assert not any(c.code == "OM4" for c in
                   clf.score("TP53", "p.R156H", residue_oncogenic_alts=["C"]).criteria)
    # Excluded if OM1 or OS1 applies.
    assert not any(c.code == "OM4" for c in clf.score(
        "TP53", "p.R156C", residue_oncogenic_alts=["H"], in_domain="DNA-binding").criteria)
    assert not any(c.code == "OM4" for c in clf.score(
        "TP53", "p.R156C", residue_oncogenic_alts=["H"], known_oncogenic=True).criteria)
    # Default (no registry supplied) never fires OM4.
    assert not any(c.code == "OM4" for c in clf.score("TP53", "p.R156C").criteria)


def test_om4_excluded_by_os3_and_suppresses_om3():
    hot_os3 = {"TP53": {"156": {"C": 60}}}
    res = VICCPointClassifier(hotspots=hot_os3).score("TP53", "p.R156C",
                                                       residue_oncogenic_alts=["H"])
    codes = [c.code for c in res.criteria]
    assert "OS3" in codes and "OM4" not in codes
    hot_om3 = {"TP53": {"156": {"C": 12}}}
    res = VICCPointClassifier(hotspots=hot_om3).score("TP53", "p.R156C",
                                                       residue_oncogenic_alts=["H"])
    codes = [c.code for c in res.criteria]
    assert "OM4" in codes and "OM3" not in codes


# ---- SOP-strict configuration (primary) ---------------------------------------------

def test_primary_config_is_sop_strict_and_unknown_config_rejected():
    assert PRIMARY_CONFIG == "sop_strict" and VICCPointClassifier(hotspots={}).config.name == "sop_strict"
    # the three published configurations; the pre-registered v2 family is added alongside
    assert {"sop_strict", "os2_fixed", "original"} <= set(CONFIGS)
    assert set(CONFIGS) - {"sop_strict", "os2_fixed", "original"} == set(V2_FAMILY)
    import pytest
    with pytest.raises(ValueError):
        VICCPointClassifier(hotspots={}, config="nope")


def test_sop_hotspot_tiers():
    """OS3: >=50 at the position AND same change >=10; OM3: <50 and same change >=10;
    OP3: same change <10 (Horak 2022 Table 2)."""
    clf = VICCPointClassifier(hotspots={"NRAS": {"12": {"D": 41, "C": 11, "S": 8}}})
    assert {c.code for c in clf.score("NRAS", "p.G12D").criteria} == {"OS3"}    # 60 / 41
    assert {c.code for c in clf.score("NRAS", "p.G12S").criteria} == {"OP3"}    # 60 / 8
    clf2 = VICCPointClassifier(hotspots={"FLT3": {"835": {"Y": 11, "E": 3}}})
    assert {c.code for c in clf2.score("FLT3", "p.D835Y").criteria} == {"OM3"}  # 14 / 11
    legacy = VICCPointClassifier(hotspots={"NRAS": {"12": {"D": 41, "C": 11}}},
                                 config="os2_fixed")
    codes = {c.code for c in legacy.score("NRAS", "p.G12D").criteria}
    assert "OM3" in codes and "OS3" not in codes                     # alt-count tiers


def test_om1_excluded_by_os3_and_om3_excluded_by_om1():
    hot = {"IDH1": {"132": {"H": 60}}, "BRAF": {"601": {"E": 20}}}
    clf = VICCPointClassifier(hotspots=hot)
    codes = [c.code for c in clf.score("IDH1", "p.R132H", in_domain="Binding site").criteria]
    assert "OS3" in codes and "OM1" not in codes
    codes = [c.code for c in clf.score("BRAF", "p.K601E", in_domain="Binding site").criteria]
    assert "OM1" in codes and "OM3" not in codes
    legacy = VICCPointClassifier(hotspots=hot, config="os2_fixed")
    codes = [c.code for c in legacy.score("IDH1", "p.R132H", in_domain="kinase").criteria]
    assert "OM1" in codes                                   # legacy: no exclusion


def test_os1_excludes_os3_os2_om1_under_sop():
    clf = VICCPointClassifier(hotspots={"IDH1": {"132": {"H": 60}}})
    res = clf.score("IDH1", "p.R132H", known_oncogenic=True, functional_lof=True,
                    in_domain="Binding site")
    assert {c.code for c in res.criteria} == {"OS1"}


def test_op4_only_from_observed_population_data():
    clf = VICCPointClassifier(hotspots={})
    assert "OP4" not in {c.code for c in clf.score("BRAF", "p.D445H").criteria}          # no data
    assert "OP4" in {c.code for c in clf.score("BRAF", "p.D445H", gnomad_af=0.0).criteria}  # absent
    assert "OP4" in {c.code for c in clf.score("BRAF", "p.D445H", gnomad_af=5e-5).criteria}
    assert "OP4" not in {c.code for c in clf.score("BRAF", "p.D445H", gnomad_af=5e-3).criteria}
    # not gated on other oncogenic evidence, and allowed alongside OVS1
    assert "OP4" in {c.code for c in clf.score("TP53", "p.R213*", gnomad_af=0.0).criteria}


def test_no_lone_benign_guard_under_sop():
    clf = VICCPointClassifier(hotspots={})
    res = clf.score("BRAF", "p.P14R", am_pathogenicity=0.1)       # SBP1 only, -1
    assert res.points == -1 and res.oncogenicity is O.LIKELY_BENIGN


def test_stoploss_is_om2_not_ovs1_and_inframe_indel_om2():
    clf = VICCPointClassifier(hotspots={})
    res = clf.score("TP53", "p.*394Qext*28")
    assert [c.code for c in res.criteria] == ["OM2"]
    assert [c.code for c in clf.score("EGFR", "p.E746_A750del").criteria] == ["OM2"]
    assert [c.code for c in clf.score("TP53", "p.R213*").criteria] == ["OVS1"]
    assert [c.code for c in clf.score("TP53", "p.M1?").criteria] == ["OVS1"]      # initiation codon
    legacy = VICCPointClassifier(hotspots={}, config="original")
    assert [c.code for c in legacy.score("TP53", "p.*394Qext*28").criteria] == ["OVS1"]


def test_domain_feature_scope():
    dom = {"BRAF": [[457, 717, "Domain", "Protein kinase"], [463, 471, "Binding site", ""]]}
    assert domain_feature_at(dom, "BRAF", 600, "site") is None
    assert domain_feature_at(dom, "BRAF", 600, "domain") == "Protein kinase"
    assert domain_feature_at(dom, "BRAF", 469, "site").startswith("Binding site")


def test_original_config_reproduces_legacy_civic_mapping():
    """original: any Supports item counts; level A/B -> OS2, else legacy 'OM4'."""
    rows = [_civ(1, "Predictive", "Resistance", "B")]
    sig = civic_signal_from_rows(rows, "EGFR", "C", 797, "S")
    orig = VICCPointClassifier(hotspots={}, config="original").score("EGFR", "p.C797S", civic=sig)
    assert "OS2" in {c.code for c in orig.criteria}
    rows = [_civ(2, "Predictive", "Resistance", "D")]
    sig = civic_signal_from_rows(rows, "EGFR", "C", 797, "S")
    orig = VICCPointClassifier(hotspots={}, config="original").score("EGFR", "p.C797S", civic=sig)
    assert "OM4" in {c.code for c in orig.criteria}
    fixed = VICCPointClassifier(hotspots={}, config="os2_fixed").score("EGFR", "p.C797S", civic=sig)
    assert not any(c.code in ("OS2", "OM4") for c in fixed.criteria)
