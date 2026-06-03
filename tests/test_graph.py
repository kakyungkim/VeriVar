"""Tests for the GraphRAG knowledge graph (Phase 3c)."""
from pathlib import Path

import pytest

from src.retrieval.corpus import RetrievalDoc
from src.retrieval.graph import KnowledgeGraph

CIVIC_SNAPSHOT = Path("data/knowledge/civic/civic_evidence_panel.tsv")

CORPUS = [
    RetrievalDoc(id="CIViC:EID1", text="...", gene="BRAF", variant="V600E",
                 disease="Melanoma", drugs="Vemurafenib", nct_ids="NCT01"),
    RetrievalDoc(id="CIViC:EID2", text="...", gene="BRAF", variant="V600E",
                 disease="Colorectal Cancer", drugs="Vemurafenib, Cetuximab"),
    # A different variant that shares the drug Vemurafenib -> multi-hop related.
    RetrievalDoc(id="CIViC:EID3", text="...", gene="BRAF", variant="V600K",
                 disease="Melanoma", drugs="Vemurafenib"),
]


def test_context_collects_direct_neighbors():
    kg = KnowledgeGraph.from_corpus(CORPUS)
    ctx = kg.context("BRAF", "p.V600E")
    assert set(ctx.evidence_ids) == {"CIViC:EID1", "CIViC:EID2"}
    assert "Vemurafenib" in ctx.drugs and "Cetuximab" in ctx.drugs
    assert "Melanoma" in ctx.diseases and "Colorectal Cancer" in ctx.diseases
    assert "NCT01" in ctx.trials


def test_multihop_related_variants_via_shared_drug():
    kg = KnowledgeGraph.from_corpus(CORPUS)
    ctx = kg.context("BRAF", "V600E")
    # V600K shares Vemurafenib with V600E -> surfaced as related (self excluded).
    assert "BRAF V600K" in ctx.related_variants
    assert "BRAF V600E" not in ctx.related_variants


def test_unknown_variant_returns_empty_context():
    kg = KnowledgeGraph.from_corpus(CORPUS)
    ctx = kg.context("BRAF", "p.Z999Z")
    assert ctx.evidence_ids == [] and ctx.drugs == [] and ctx.related_variants == []


@pytest.mark.skipif(not CIVIC_SNAPSHOT.exists(), reason="CIViC snapshot not fetched")
def test_real_graph_braf_v600e():
    kg = KnowledgeGraph.from_civic()
    ctx = kg.context("BRAF", "p.V600E")
    assert ctx.evidence_ids                      # has citable evidence
    assert any("Vemurafenib" in d or "Dabrafenib" in d for d in ctx.drugs)
