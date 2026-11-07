"""The dashboard / Fig S3 VICC rule arm must be the SOP-strict engine's own output."""
import json
from pathlib import Path

import pytest

from src.classify.vicc_rules import VICCPointClassifier
from src.dashboard.vicc_arm import score_record

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "outputs" / "cohort_interpretation.json"


def _record(key, cancer):
    if not RESULTS.exists():
        pytest.skip("cohort_interpretation.json not present")
    data = json.loads(RESULTS.read_text())
    return next(v for v in data["variants"]
                if v["variant_key"] == key and v["cancer_type"] == cancer)


def test_truncating_tsg_gets_ovs1_not_no_call():
    arm = score_record(_record("APC p.R1450*", "Colorectal Adenocarcinoma"))
    assert arm.config == "sop_strict"
    assert [r["code"] for r in arm.rows()] == ["OVS1"]
    assert (arm.points, arm.call) == (8, "Likely Oncogenic")


def test_oncogene_hotspot_never_gets_ovs1_and_matches_engine():
    rec = _record("BRAF p.V600E", "Cutaneous Melanoma")
    arm = score_record(rec)
    codes = [r["code"] for r in arm.rows()]
    assert "OVS1" not in codes          # OVS1 is for null variants in tumour suppressors
    direct = VICCPointClassifier().score(
        "BRAF", "p.V600E", am_pathogenicity=0.9927, gnomad_af=arm.gnomad_af)
    assert codes == [c.code for c in direct.criteria]
    assert arm.points == direct.points and arm.call == direct.oncogenicity.value


def test_demo_html_has_no_ovs1_for_braf():
    html = (ROOT / "docs/manuscript/figures/_dashboard_demo.html").read_text()
    braf = html.split("APC p.R1450*")[0]
    assert "OVS1" not in braf
