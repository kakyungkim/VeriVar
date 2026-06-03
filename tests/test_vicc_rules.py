"""Unit tests for the VICC point engine (src.classify.vicc_rules)."""
from src.classify.vicc_rules import (
    TUMOUR_SUPPRESSORS, VICCPointClassifier, classify_points, parse_protein_change,
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
    res = clf.score("BRAF", "p.V600E", am_pathogenicity=0.99,
                    civic_onco=1, civic_best_level="B")
    codes = {c.code for c in res.criteria}
    assert "OS3" in codes and "OP1" in codes and "OS2" in codes
    assert res.oncogenicity in (O.ONCOGENIC, O.LIKELY_ONCOGENIC)


def test_gnomad_common_is_benign():
    clf = VICCPointClassifier(hotspots={})
    res = clf.score("BRAF", "p.A31G", am_pathogenicity=0.2, gnomad_af=0.12)
    assert any(c.code == "SBVS1" for c in res.criteria)
    assert res.oncogenicity in (O.BENIGN, O.LIKELY_BENIGN)


def test_lone_sbp1_stays_vus():
    """A single computational-benign line is too weak for Likely Benign."""
    clf = VICCPointClassifier(hotspots={})
    res = clf.score("BRAF", "p.P14R", am_pathogenicity=0.1)   # SBP1 only -> -1
    assert {c.code for c in res.criteria} == {"SBP1"}
    assert res.oncogenicity is O.VUS


def test_lone_sbs2_stays_vus():
    """A single functional-neutral line (DMS SBS2, -4) without populational support
    is too weak for Likely Benign -> abstain to VUS (generalises the SBP1 guard;
    fixes e.g. TP53 G334R where the DMS classifier mislabels a non-DBD residue)."""
    clf = VICCPointClassifier(hotspots={})
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
    """The optional OS1 lever (established-oncogenic, off by default) adds +4 and is citable."""
    clf = VICCPointClassifier(hotspots={})
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
