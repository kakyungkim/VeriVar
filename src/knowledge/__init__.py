"""Structured knowledge layer (replaces the fabricating MockRAGDatabase).

Adapters answer (gene, protein_change, cancer_type) with citable Evidence and
drugs/trials; the aggregator merges them into one EvidenceBundle per variant.
"""
from src.knowledge.base import KnowledgeSource, normalize_protein_change
from src.knowledge.civic import CivicSource
from src.knowledge.dgidb import DgidbSource
from src.knowledge.aggregator import EvidenceAggregator

__all__ = [
    "KnowledgeSource",
    "normalize_protein_change",
    "CivicSource",
    "DgidbSource",
    "EvidenceAggregator",
]
