"""Tests for dense/hybrid retrieval (Phase 3b).

Unit tests use the deterministic HashingEmbedder (no model download, no network).
A separate skippable integration test builds the real CIViC index.
"""
from pathlib import Path

import pytest

from src.retrieval.corpus import RetrievalDoc, build_civic_corpus
from src.retrieval.embedders import HashingEmbedder, _tokenize
from src.retrieval.hybrid import HybridRetriever, _rrf

CIVIC_SNAPSHOT = Path("data/knowledge/civic/civic_evidence_panel.tsv")

TINY_CORPUS = [
    RetrievalDoc(id="CIViC:EID1", text="BRAF V600E (Melanoma): vemurafenib is effective in BRAF V600E melanoma",
                 gene="BRAF", variant="V600E", disease="Melanoma"),
    RetrievalDoc(id="CIViC:EID2", text="EGFR L858R (Lung): erlotinib sensitivity in EGFR L858R lung adenocarcinoma",
                 gene="EGFR", variant="L858R", disease="Lung"),
    RetrievalDoc(id="CIViC:EID3", text="KRAS G12C (Lung): sotorasib targets KRAS G12C",
                 gene="KRAS", variant="G12C", disease="Lung"),
]


def test_tokenize():
    assert _tokenize("BRAF V600E, melanoma!") == ["braf", "v600e", "melanoma"]


def test_rrf_fuses_rankings():
    fused = _rrf([["a", "b", "c"], ["b", "a", "d"]])
    # 'a' and 'b' appear high in both -> outrank singletons.
    top = sorted(fused, key=lambda k: -fused[k])[:2]
    assert set(top) == {"a", "b"}


def test_hybrid_retrieves_relevant_doc():
    r = HybridRetriever(TINY_CORPUS, embedder=HashingEmbedder())
    hits = r.search("BRAF V600E melanoma treatment", k=1)
    assert hits and hits[0].doc.id == "CIViC:EID1"


def test_hybrid_empty_corpus():
    r = HybridRetriever([], embedder=HashingEmbedder())
    assert r.search("anything") == []


def test_hits_are_citable():
    r = HybridRetriever(TINY_CORPUS, embedder=HashingEmbedder())
    hits = r.search("KRAS G12C", k=2)
    assert all(h.doc.id.startswith("CIViC:EID") for h in hits)


@pytest.mark.skipif(not CIVIC_SNAPSHOT.exists(), reason="CIViC snapshot not fetched")
def test_build_real_corpus():
    docs = build_civic_corpus()
    assert len(docs) > 100
    assert any(d.gene == "BRAF" and "V600E" in d.variant for d in docs)
