"""Input-context ablation tests (offline, no API key needed).

Covers the perturbation functions, the alias table, and the aggregation logic.
The perturbations must be exactly right: a malformed perturbation would look
like a robustness failure when it is really a harness bug, so each one is
checked against hand-written expected notation.
"""
import json
from pathlib import Path

import pytest

from scripts.run_context_ablation import (
    ALIASES, INVARIANCE_ARMS, NOTATION_ARMS, TEXT_KEYED_SOURCES, TRANSCRIPT_OFFSET,
    alternative_symbols, perturb_case_lower, perturb_legacy_stop,
    perturb_three_letter, perturb_transcript_shift, primary_alias, summarise,
)


# --------------------------------------------------------------------------- #
# Perturbations
# --------------------------------------------------------------------------- #
def test_case_lower_only_touches_the_symbol():
    assert perturb_case_lower("BRAF", "p.V600E") == ("braf", "p.V600E")


@pytest.mark.parametrize("hgvsp,expected", [
    ("p.V600E", "p.Val600Glu"),
    ("p.G12V", "p.Gly12Val"),
    ("p.R130*", "p.Arg130Ter"),
    ("p.H1047R", "p.His1047Arg"),
])
def test_three_letter_notation_is_valid_hgvs(hgvsp, expected):
    assert perturb_three_letter("X", hgvsp) == ("X", expected)


@pytest.mark.parametrize("hgvsp", ["p.N1784Kfs*3", "p.E69Afs*74", "p.X263_splice", ""])
def test_three_letter_declines_forms_it_cannot_render(hgvsp):
    """Frameshift/splice forms are excluded rather than mangled."""
    assert perturb_three_letter("X", hgvsp) is None


def test_legacy_stop_applies_only_to_nonsense():
    assert perturb_legacy_stop("PTEN", "p.R130*") == ("PTEN", "p.R130X")
    assert perturb_legacy_stop("BRAF", "p.V600E") is None
    assert perturb_legacy_stop("BRCA2", "p.N1784Kfs*3") is None


def test_transcript_shift_moves_the_residue_number_only():
    gene, hgvsp = perturb_transcript_shift("BRAF", "p.V600E")
    assert (gene, hgvsp) == ("BRAF", f"p.V{600 + TRANSCRIPT_OFFSET}E")
    # Tail forms are preserved so the perturbed string stays well-formed.
    assert perturb_transcript_shift("PTEN", "p.R130*")[1] == f"p.R{130 + TRANSCRIPT_OFFSET}*"
    assert perturb_transcript_shift("BRCA2", "p.N1784Kfs*3")[1] == f"p.N{1784 + TRANSCRIPT_OFFSET}Kfs*3"


def test_transcript_shift_is_excluded_from_the_invariance_arms():
    """It names a different residue, so a changed answer there is correct."""
    assert "transcript_shift" in NOTATION_ARMS
    assert "transcript_shift" not in INVARIANCE_ARMS


def test_alphamissense_is_not_treated_as_text_keyed():
    """It is keyed on coordinates, so it survives every perturbation by design."""
    assert "CIViC" in TEXT_KEYED_SOURCES
    assert "AlphaMissense" not in TEXT_KEYED_SOURCES


# --------------------------------------------------------------------------- #
# Alias table
# --------------------------------------------------------------------------- #
def test_alias_table_is_committed_and_sourced_from_hgnc():
    if not ALIASES.exists():
        pytest.skip("gene_aliases.json not fetched")
    payload = json.loads(ALIASES.read_text())
    assert "HGNC" in payload["provenance"]["source"]
    assert not payload["provenance"]["missing"]
    for gene, rec in payload["genes"].items():
        assert rec["hgnc_id"].startswith("HGNC:"), gene
        assert alternative_symbols(rec), f"{gene} has no alternative symbol to test"


def test_alternative_symbols_dedups_and_puts_withdrawn_symbols_first():
    rec = {"prev_symbol": ["ESR"], "alias_symbol": ["ER", "esr", "NR3A1"]}
    assert alternative_symbols(rec) == ["ESR", "ER", "NR3A1"]  # case-insensitive dedup


def test_primary_alias_is_deterministic():
    rec = {"prev_symbol": ["NGL"], "alias_symbol": ["HER2", "NEU"]}
    assert primary_alias(rec) == "NGL"
    assert primary_alias({"prev_symbol": [], "alias_symbol": ["p53"]}) == "p53"
    assert primary_alias({"prev_symbol": [], "alias_symbol": []}) is None


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def _row(clinical_before=2, clinical_after=0, onco_before="Oncogenic", onco_after="VUS"):
    collapsed = bool(clinical_before and not clinical_after)
    return {
        "gene": "BRAF", "hgvsp": "p.V600E", "cancer_type": "Melanoma", "evidence_tier": "civic",
        "baseline": {
            "n_evidence": clinical_before + 1, "n_clinical_evidence": clinical_before,
            "classification": {"oncogenicity": onco_before, "tier": "Tier I",
                               "abstained": False, "citations": []},
        },
        "alias_sweep": [{"symbol": "BRAF1", "n_evidence": 1, "n_clinical_evidence": clinical_after,
                         "jaccard": 0.0, "clinical_jaccard": 0.0,
                         "clinical_collapsed": collapsed, "n_drugs": 0, "by_source": {}}],
        "arms": {"alias": {
            "applicable": True, "input": "BRAF1 p.V600E",
            "n_evidence": 1, "n_clinical_evidence": clinical_after,
            "jaccard": 0.0, "clinical_jaccard": 0.0, "by_source": {}, "n_drugs": 0,
            "evidence_collapsed": False, "clinical_collapsed": collapsed,
            "prior_only_after": True,
            "classification": {"oncogenicity": onco_after, "tier": "Tier III",
                               "abstained": True, "citations": []},
        }},
    }


def test_summary_counts_clinical_collapse_not_total_collapse():
    """The prior survives, so total-collapse would report zero loss and mislead."""
    s = summarise([_row()], use_llm=False)
    assert s["arms"]["alias"]["n_clinical_collapsed"] == 1
    assert s["arms"]["alias"]["n_prior_only_after"] == 1
    assert s["alias_sweep"]["clinical_collapse_rate"] == 1.0


def test_summary_counts_an_abstention_after_evidence_loss_as_safe():
    s = summarise([_row(onco_after="VUS")], use_llm=True)
    assert s["arms"]["alias"]["driver_calls_after_clinical_loss"] == 0
    assert s["arms"]["alias"]["safe_downgrades_after_clinical_loss"] == 1
    assert s["arms"]["alias"]["oncogenicity_flips"] == 1


def test_summary_counts_a_retained_driver_call_after_evidence_loss_as_unsafe():
    """Asserting a driver on evidence that is no longer retrieved is the real hazard."""
    s = summarise([_row(onco_after="Oncogenic")], use_llm=True)
    assert s["arms"]["alias"]["driver_calls_after_clinical_loss"] == 1
    assert s["arms"]["alias"]["safe_downgrades_after_clinical_loss"] == 0
    assert s["arms"]["alias"]["oncogenicity_flips"] == 0


def test_summary_skips_inapplicable_arms():
    row = _row()
    row["arms"]["legacy_stop"] = {"applicable": False}
    s = summarise([row], use_llm=False)
    assert s["arms"]["legacy_stop"]["n_applicable"] == 0
    assert s["arms"]["legacy_stop"]["mean_clinical_jaccard"] is None
