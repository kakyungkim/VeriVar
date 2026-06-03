"""Integration test for the hybrid evidence orchestrator (Phase 3e, offline)."""
from src.models import Variant
from src.knowledge.civic import CivicSource
from src.knowledge.aggregator import EvidenceAggregator
from src.retrieval.corpus import RetrievalDoc
from src.retrieval.embedders import HashingEmbedder
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.graph import KnowledgeGraph
from src.retrieval.orchestrator import HybridEvidenceRetriever


class _StubCivic(CivicSource):
    """CivicSource without a file, seeded with one in-memory evidence row."""
    def __init__(self):
        self._index = {
            ("BRAF", "V600E"): [{
                "evidence_id": "100", "molecular_profile": "BRAF V600E",
                "disease": "Melanoma", "therapies": "Vemurafenib",
                "evidence_statement": "BRAF V600E confers vemurafenib sensitivity.",
                "evidence_level": "B", "evidence_direction": "Supports",
                "source_type": "PubMed", "citation_id": "123",
                "evidence_civic_url": "http://x", "nct_ids": "NCT01",
                "therapy_interaction_type": "",
            }]
        }


def _retriever():
    agg = EvidenceAggregator([_StubCivic()])
    docs = [
        RetrievalDoc(id="CIViC:EID100", text="BRAF V600E (Melanoma): vemurafenib sensitivity",
                     gene="BRAF", variant="V600E", disease="Melanoma", drugs="Vemurafenib"),
        RetrievalDoc(id="CIViC:EID200", text="BRAF V600E (Colorectal): cetuximab resistance context",
                     gene="BRAF", variant="V600E", disease="Colorectal", drugs="Cetuximab"),
    ]
    dense = HybridRetriever(docs, embedder=HashingEmbedder())
    graph = KnowledgeGraph.from_corpus(docs)
    return HybridEvidenceRetriever(agg, dense=dense, graph=graph, dense_k=3)


def test_orchestrator_fuses_structured_dense_graph():
    r = _retriever()
    v = Variant(chrom="7", pos=140453136, ref="A", alt="T", gene="BRAF",
                hgvsp="p.V600E", cancer_type="Cutaneous Melanoma", variant_type="SNV")
    res = r.retrieve(v)

    ids = {e.id for e in res.bundle.evidences}
    # Structured (EID100) + dense-only (EID200) both present, de-duped.
    assert "CIViC:EID100" in ids and "CIViC:EID200" in ids
    assert res.bundle.has_variant_evidence is True
    assert res.bundle.citation_ids()
    # Graph context attached.
    assert res.graph is not None
    assert "Vemurafenib" in res.graph.drugs


def test_orchestrator_abstains_without_evidence():
    r = _retriever()
    v = Variant(chrom="1", pos=1, ref="C", alt="T", gene="BRAF",
                hgvsp="p.Z999Z", variant_type="SNV")
    res = r.retrieve(v)
    assert res.bundle.has_variant_evidence is False
