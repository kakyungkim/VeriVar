"""Tests for the structured knowledge layer (Phase 3a).

The honest-abstention behaviour (empty bundle for unsupported variants) is the
direct fix for the old fabricating mock RAG, so it is asserted explicitly.
"""
from pathlib import Path

import pytest

from src.knowledge.base import normalize_protein_change
from src.knowledge.civic import CivicSource, _split_profile
from src.knowledge.aggregator import EvidenceAggregator

CIVIC_SNAPSHOT = Path("data/knowledge/civic/civic_evidence_panel.tsv")
DGIDB_SNAPSHOT = Path("data/knowledge/dgidb/dgidb_panel.json")
_have_civic = CIVIC_SNAPSHOT.exists()


def test_normalize_protein_change():
    assert normalize_protein_change("p.V600E") == "V600E"
    assert normalize_protein_change("V600E") == "V600E"
    assert normalize_protein_change("") == ""


def test_split_profile():
    assert _split_profile("BRAF V600E") == ("BRAF", "V600E")
    assert _split_profile("") == ("", "")


@pytest.mark.skipif(not _have_civic, reason="CIViC snapshot not fetched")
def test_civic_returns_evidence_for_braf_v600e():
    civic = CivicSource()
    ev = civic.evidence("BRAF", "p.V600E")
    assert len(ev) > 0
    assert all(e.id.startswith("CIViC:EID") for e in ev)
    assert any(e.statement for e in ev)            # corpus text present
    # 'p.' and bare forms resolve to the same record set.
    assert len(civic.evidence("BRAF", "V600E")) == len(ev)


@pytest.mark.skipif(not _have_civic, reason="CIViC snapshot not fetched")
def test_civic_empty_for_unsupported_variant():
    civic = CivicSource()
    # A variant with no CIViC entry must return nothing (drives abstention).
    assert civic.evidence("BRAF", "p.Z999Z") == []


@pytest.mark.skipif(not _have_civic, reason="CIViC snapshot not fetched")
def test_aggregator_bundle_and_abstention():
    from src.knowledge.dgidb import DgidbSource
    agg = EvidenceAggregator([CivicSource(), DgidbSource()])

    supported = agg.for_variant("BRAF", "p.V600E", "Cutaneous Melanoma")
    assert supported.has_variant_evidence is True
    assert supported.citation_ids()                       # citable ids exist
    assert len(supported.drugs) > 0                        # CIViC/DGIdb drugs

    # A nonexistent BRAF variant: DGIdb still returns BRAF gene-level drugs, but
    # there is NO variant-specific evidence -> must still abstain.
    unsupported = agg.for_variant("BRAF", "p.Z999Z")
    assert unsupported.evidences == []
    assert unsupported.has_variant_evidence is False      # abstention signal
    # (gene-level drugs may be present; they do not justify a variant call)
