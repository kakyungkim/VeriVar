"""Dense embedders for the RAG layer.

Pluggable so the pipeline can swap a domain biomedical model (primary) for the
OpenAI baseline (ablation), and so unit tests can use a fast deterministic
embedder with no model download or network.
"""
import hashlib
import math
from abc import ABC, abstractmethod
from typing import List, Optional

# Domain biomedical sentence-transformer (PubMedBERT tuned for embeddings).
# Must ship safetensors: transformers refuses .bin under torch<2.6 (CVE-2025-32434),
# and torch>2.2 has no Intel-macOS wheels. NeuML model ships safetensors + is ST-native.
DEFAULT_DOMAIN_MODEL = "NeuML/pubmedbert-base-embeddings"
# Safetensors fallbacks tried in order if the primary fails to load.
FALLBACK_MODELS = ["BAAI/bge-small-en-v1.5", "sentence-transformers/all-MiniLM-L6-v2"]


class DenseEmbedder(ABC):
    dim: int

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        ...

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


class SentenceTransformerEmbedder(DenseEmbedder):
    """Local domain embedding model via sentence-transformers (lazy-loaded)."""

    def __init__(self, model_name: str = DEFAULT_DOMAIN_MODEL, allow_fallback: bool = True):
        self.model_name = model_name
        self.allow_fallback = allow_fallback
        self._model = None

    def _ensure(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            candidates = [self.model_name] + (FALLBACK_MODELS if self.allow_fallback else [])
            last_err = None
            for name in candidates:
                try:
                    self._model = SentenceTransformer(name)
                    self.model_name = name
                    self.dim = self._model.get_sentence_embedding_dimension()
                    return self._model
                except Exception as e:  # noqa: BLE001 - try next safetensors fallback
                    last_err = e
            raise RuntimeError(f"Could not load any embedding model: {last_err}")
        return self._model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        model = self._ensure()
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()


class OpenAIEmbedder(DenseEmbedder):
    """OpenAI text-embedding baseline (requires OPENAI_API_KEY)."""

    def __init__(self, model_name: str = "text-embedding-3-small"):
        self.model_name = model_name
        self.dim = 1536
        self._client = None

    def _ensure(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI()
        return self._client

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        client = self._ensure()
        resp = client.embeddings.create(model=self.model_name, input=texts)
        return [d.embedding for d in resp.data]


class HashingEmbedder(DenseEmbedder):
    """Deterministic bag-of-words hashing embedder — no deps, no network.

    Token-overlap similarity only (not semantic), but enough for fast, offline
    unit tests and as a graceful fallback when no model is available.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(t) for t in texts]

    def _embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        for tok in _tokenize(text):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def _tokenize(text: str) -> List[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if t]
