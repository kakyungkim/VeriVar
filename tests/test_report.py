"""Tests for the cohort report generator (Phase 5)."""
from src.report.cohort_report import _prepare, generate_report

SAMPLE = {
    "provenance": {"model_name": "gpt-4o-mini", "timestamp": "2026-05-31T00:00:00Z",
                   "data_sources": {"civic": "CIViC"}},
    "discordance_summary": {
        "overall": {"n": 2, "tier_concordance_rate": 0.5, "oncogenicity_concordance_rate": 1.0,
                    "any_discordant": 1},
        "by_cancer": {"Melanoma": {"n": 2, "tier_discordant": 1, "oncogenicity_discordant": 0,
                                   "tier_concordance_rate": 0.5, "oncogenicity_concordance_rate": 1.0}},
        "discordant_variants": [],
    },
    "variants": [
        {"variant_key": "BRAF p.V600E", "gene": "BRAF", "hgvsp": "p.V600E",
         "cancer_type": "Melanoma", "variant_type": "SNV", "evidence_tier": "civic",
         "sample_ids": ["S1"], "n_evidence": 2, "n_drugs": 3, "n_trials": 1, "discordant": False,
         "mode_a": {"oncogenicity": "Oncogenic", "tier": "Tier I", "tier_level": "Level A",
                    "rationale": "x", "citations": ["CIViC:EID1"], "confidence": 0.9, "abstained": False},
         "mode_b": {"oncogenicity": "Oncogenic", "tier": "Tier I", "tier_level": "Level A",
                    "rationale": "y", "citations": ["CIViC:EID1"], "confidence": None, "abstained": False}},
        {"variant_key": "KRAS p.G12C", "gene": "KRAS", "hgvsp": "p.G12C",
         "cancer_type": "Melanoma", "variant_type": "SNV", "evidence_tier": "civic",
         "sample_ids": ["S2"], "n_evidence": 1, "n_drugs": 1, "n_trials": 0, "discordant": True,
         "mode_a": {"oncogenicity": "Oncogenic", "tier": "Tier II", "tier_level": None,
                    "rationale": "x", "citations": [], "confidence": 0.7, "abstained": False},
         "mode_b": {"oncogenicity": "Oncogenic", "tier": "Tier I", "tier_level": "Level A",
                    "rationale": "y", "citations": [], "confidence": None, "abstained": False}},
    ],
}


def test_prepare_splits_discordant():
    ctx = _prepare(SAMPLE)
    assert ctx["n_total"] == 2
    assert ctx["n_discordant"] == 1
    assert ctx["discordant"][0]["variant_key"] == "KRAS p.G12C"


def test_generate_report_writes_html(tmp_path):
    out = generate_report(SAMPLE, out_dir=tmp_path, basename="r")
    html = (tmp_path / "r.html")
    assert html.exists()
    text = html.read_text()
    assert "VeriVar" in text and "BRAF p.V600E" in text and "KRAS p.G12C" in text
    # interactive controls (search/sort/filter) are present in the HTML artifact
    assert "vsearch" in text and "fbtn" in text and "addEventListener" in text
    # per-row filter attributes for the JS filters
    assert "data-discordant" in text and "data-trials" in text
