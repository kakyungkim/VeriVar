"""OS1 lookup must require an exact gene + protein-change match (no neighbour inheritance).

Regression for the PIK3CA p.H1047Q bug: the E-utilities search returned H1047R's record
(VCV000013652, Oncogenic) and the old lookup took it without checking the protein change.
"""
import json
import os

import pytest

from scripts.fetch_horak_clinvar import (SNAPSHOT, aa3, is_positive, match_records,
                                         norm_protein)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OS1 = os.path.join(ROOT, "data", "benchmark", "horak_clinvar_os1.json")

# What esummary actually returns for "PIK3CA[gene] AND p.His1047Gln" (checked 2026-09-24).
_H1047_RECORDS = [
    {"gene": "PIK3CA", "protein": "His1047Gln", "label": "Uncertain significance",
     "vcv": "VCV003765059"},
    {"gene": "PIK3CA", "protein": "His1047Tyr", "label": "", "vcv": "VCV000039705"},
    {"gene": "PIK3CA", "protein": "His1047Arg", "label": "Oncogenic", "vcv": "VCV000013652"},
]


@pytest.mark.parametrize("raw", ["p.H1047Q", "H1047Q", "p.His1047Gln", "His1047Gln",
                                 "p.HIS1047GLN", "(p.His1047Gln)"])
def test_norm_protein_one_and_three_letter(raw):
    assert norm_protein(raw) == "H1047Q"


def test_norm_protein_rejects_non_missense():
    assert norm_protein("p.Glu746_Ala750del") is None
    assert norm_protein("") is None and norm_protein(None) is None
    assert aa3("H1047Q") == "p.His1047Gln"


def test_neighbour_record_does_not_grant_os1():
    rec = match_records("PIK3CA", "H1047Q", _H1047_RECORDS)
    assert rec["oncogenic"] is False
    assert rec["vcv"] == "VCV003765059" and rec["label"] == "Uncertain significance"


def test_exact_positive_record_grants_os1():
    rec = match_records("PIK3CA", "p.H1047R", _H1047_RECORDS)
    assert rec["oncogenic"] is True and rec["vcv"] == "VCV000013652"


def test_gene_must_match():
    recs = [{"gene": "PIK3CB", "protein": "p.H1047R", "label": "Oncogenic", "vcv": 1}]
    assert match_records("PIK3CA", "H1047R", recs)["oncogenic"] is False


def test_only_positive_labels_grant_os1():
    assert is_positive("Oncogenic") and is_positive("Likely oncogenic")
    for lab in ("Uncertain significance", "Likely benign", "Benign",
                "Conflicting classifications of oncogenicity", "", None):
        assert not is_positive(lab)
    recs = [{"gene": "PIK3CA", "protein": "p.I391M", "label": "Likely benign", "vcv": 135038}]
    assert match_records("PIK3CA", "I391M", recs)["oncogenic"] is False


def test_no_match_returns_none():
    rec = match_records("KRAS", "G12D", _H1047_RECORDS)
    assert rec == {"oncogenic": False, "vcv": None, "label": None}


@pytest.mark.skipif(not (os.path.exists(OS1) and os.path.exists(SNAPSHOT)),
                    reason="OS1 lookup or ClinVar snapshot not present")
def test_committed_os1_lookup_is_exact():
    d = json.load(open(OS1))
    assert d["PIK3CA|H1047Q"]["oncogenic"] is False
    assert d["PIK3CA|H1047R"]["oncogenic"] is True
    assert d["PIK3CA|E418K"]["oncogenic"] is True
    variants = {k: v for k, v in d.items() if not k.startswith("_")}
    assert len(variants) == 70
    assert sum(v["oncogenic"] for v in variants.values()) == d["_provenance"]["n_os1"]
