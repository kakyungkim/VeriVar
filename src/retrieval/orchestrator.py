"""Hybrid evidence orchestrator — the single entry point for Phase 4.

Fuses the three retrieval arms into one citable EvidenceBundle per variant:
  * structured  : exact gene+variant lookups (CIViC/DGIdb) + AlphaMissense
  * dense       : semantic hits over CIViC statements (catches evidence whose
                  molecular_profile didn't exact-match the key)
  * graph       : multi-hop relational context (related variants via shared drug)

Every evidence item keeps its citable id, so the downstream LLM can ground each
claim and abstain when ``has_variant_evidence`` is False.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from src.models import Evidence, EvidenceBundle, Modality, Variant
from src.knowledge.aggregator import EvidenceAggregator
from src.knowledge.base import normalize_protein_change
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.graph import KnowledgeGraph, GraphContext


@dataclass
class RetrievedEvidence:
    """Bundle plus the graph context (kept separate from the citable bundle)."""
    bundle: EvidenceBundle
    graph: Optional[GraphContext] = None


class HybridEvidenceRetriever:
    def __init__(self, aggregator: EvidenceAggregator,
                 dense: Optional[HybridRetriever] = None,
                 graph: Optional[KnowledgeGraph] = None,
                 dense_k: int = 5):
        self.aggregator = aggregator
        self.dense = dense
        self.graph = graph
        self.dense_k = dense_k

    def index_fingerprint(self) -> Optional[dict]:
        """Dense-index identity for the run record; None when the dense arm is off."""
        if self.dense is None:
            return None
        fp = self.dense.fingerprint()
        fp["dense_k"] = self.dense_k
        return fp

    def retrieve(self, variant: Variant) -> RetrievedEvidence:
        bundle = self.aggregator.for_variant_obj(variant)
        have = {e.id for e in bundle.evidences}

        # Dense arm: add semantically-retrieved CIViC evidence not already present.
        # Guard against topic drift: a dense hit must concern the SAME variant,
        # not just the same gene — otherwise evidence for a different variant of
        # a druggable gene would falsely support a passenger variant. Substring
        # match handles complex profiles like "V600E OR V600K".
        q_pc = normalize_protein_change(variant.hgvsp).upper()
        if self.dense is not None and q_pc:
            query = f"{variant.gene} {variant.hgvsp} {variant.cancer_type or ''}".strip()
            for hit in self.dense.search(query, k=self.dense_k):
                d = hit.doc
                if d.id in have:
                    continue
                if d.gene.upper() != variant.gene.upper():
                    continue
                if q_pc not in normalize_protein_change(d.variant).upper():
                    continue
                have.add(d.id)
                bundle.evidences.append(Evidence(
                    id=d.id, source="CIViC", modality=Modality.GENOMIC_SNV_INDEL,
                    gene=d.gene, variant=d.variant, disease=d.disease or None,
                    statement=d.text, evidence_level=d.evidence_level or None,
                    direction=d.direction or None,
                ))

        graph_ctx = self.graph.context(variant.gene, variant.hgvsp) if self.graph else None
        return RetrievedEvidence(bundle=bundle, graph=graph_ctx)
