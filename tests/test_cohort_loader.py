"""Tests for the cBioPortal cohort loader (Phase 2)."""
from pathlib import Path

import pytest

from src.cohort.loader import (
    is_candidate,
    variants_from_snapshot,
    variants_by_sample,
    _variant_type,
)

FIXTURE = {
    "study_id": "demo",
    "cancer_type": "Cutaneous Melanoma",
    "samples": ["S1", "S2"],
    "mutations": [
        {"sample_id": "S1", "gene": "BRAF", "chrom": "7", "pos": 140453136,
         "ref": "A", "alt": "T", "protein_change": "V600E",
         "mutation_type": "Missense_Mutation", "variant_type": "SNP"},
        {"sample_id": "S1", "gene": "TP53", "chrom": "17", "pos": 7577120,
         "ref": "C", "alt": "-", "protein_change": "R175fs",
         "mutation_type": "Frame_Shift_Del", "variant_type": "DEL"},
        {"sample_id": "S2", "gene": "TERT", "chrom": "5", "pos": 1295113,
         "ref": "G", "alt": "A", "protein_change": "",
         "mutation_type": "5'Flank", "variant_type": "SNP"},  # non-candidate
        {"sample_id": "S2", "gene": "PTEN", "chrom": "10", "pos": 89000000,
         "ref": "C", "alt": "T", "protein_change": "R130*",
         "mutation_type": "Nonsense_Mutation", "variant_type": "SNP"},
    ],
}


def test_variant_type_mapping():
    assert _variant_type("Missense_Mutation", "SNP") == "SNV"
    assert _variant_type("Frame_Shift_Del", "DEL") == "INDEL"
    assert _variant_type("In_Frame_Ins", "") == "INDEL"


def test_candidate_filter_drops_noncoding():
    assert is_candidate(FIXTURE["mutations"][0]) is True            # BRAF V600E
    assert is_candidate(FIXTURE["mutations"][2]) is False           # 5'Flank, no protein change


def test_variants_from_snapshot_tags_and_normalizes():
    variants = variants_from_snapshot(FIXTURE)
    # 3 candidates (the 5'Flank record is dropped).
    assert len(variants) == 3
    braf = next(v for v in variants if v.gene == "BRAF")
    assert braf.hgvsp == "p.V600E"          # 'p.' prefix added
    assert braf.cancer_type == "Cutaneous Melanoma"
    assert braf.sample_id == "S1"
    assert braf.key == "BRAF p.V600E"
    tp53 = next(v for v in variants if v.gene == "TP53")
    assert tp53.variant_type == "INDEL"


def test_keep_all_when_candidates_only_false():
    assert len(variants_from_snapshot(FIXTURE, candidates_only=False)) == 4


def test_group_by_sample():
    grouped = variants_by_sample(variants_from_snapshot(FIXTURE))
    assert set(grouped) == {"S1", "S2"}
    assert len(grouped["S1"]) == 2


@pytest.mark.skipif(not Path("data/cohorts/cohort_manifest.json").exists(),
                    reason="cohort not fetched (run scripts.fetch_cohort)")
def test_real_cohort_has_braf_v600e_in_two_cancers():
    """Integration guard: the fetched cohort must contain the headline contrast."""
    from src.cohort.loader import load_cohort
    variants = load_cohort()
    cancers_with_braf = {
        v.cancer_type for v in variants if v.gene == "BRAF" and v.hgvsp == "p.V600E"
    }
    assert "Cutaneous Melanoma" in cancers_with_braf
    assert "Colorectal Adenocarcinoma" in cancers_with_braf
