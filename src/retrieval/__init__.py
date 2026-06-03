"""Dense + hybrid retrieval (RAG) over the CIViC evidence corpus."""
from src.retrieval.corpus import RetrievalDoc, build_civic_corpus
from src.retrieval.embedders import (
    DenseEmbedder,
    SentenceTransformerEmbedder,
    OpenAIEmbedder,
    HashingEmbedder,
    DEFAULT_DOMAIN_MODEL,
)
from src.retrieval.hybrid import HybridRetriever, RetrievalHit
from src.retrieval.graph import KnowledgeGraph, GraphContext
from src.retrieval.orchestrator import HybridEvidenceRetriever, RetrievedEvidence

__all__ = [
    "RetrievalDoc",
    "build_civic_corpus",
    "DenseEmbedder",
    "SentenceTransformerEmbedder",
    "OpenAIEmbedder",
    "HashingEmbedder",
    "DEFAULT_DOMAIN_MODEL",
    "HybridRetriever",
    "RetrievalHit",
    "KnowledgeGraph",
    "GraphContext",
    "HybridEvidenceRetriever",
    "RetrievedEvidence",
]
