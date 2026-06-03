"""Hybrid retriever: BM25 (sparse) + dense vectors, fused by Reciprocal Rank Fusion.

Hybrid beats dense-only on this corpus because exact tokens (gene symbol, protein
change like 'V600E') matter as much as semantics. Dense vectors live in an
in-memory Chroma collection; sparse uses rank_bm25. Each retrieved doc keeps its
CIViC evidence id so hits remain citable.
"""
import itertools
from dataclasses import dataclass
from typing import List, Optional

from src.retrieval.corpus import RetrievalDoc
from src.retrieval.embedders import DenseEmbedder, HashingEmbedder, _tokenize

# Chroma's in-process client shares collections across instances, so each
# retriever needs a unique collection name to avoid name collisions.
_COLLECTION_COUNTER = itertools.count()


@dataclass
class RetrievalHit:
    doc: RetrievalDoc
    score: float


def _rrf(rankings: List[List[str]], k: int = 60) -> dict:
    """Reciprocal Rank Fusion over several ranked id-lists -> {id: score}."""
    scores: dict = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


class HybridRetriever:
    def __init__(self, docs: List[RetrievalDoc], embedder: Optional[DenseEmbedder] = None,
                 collection_name: str = "civic", persist_path: Optional[str] = None):
        self.docs = docs
        self.by_id = {d.id: d for d in docs}
        self.embedder = embedder or HashingEmbedder()
        self._build_sparse()
        self._build_dense(collection_name, persist_path)

    def _build_sparse(self):
        from rank_bm25 import BM25Okapi
        self._tokenized = [_tokenize(d.text) for d in self.docs]
        self._bm25 = BM25Okapi(self._tokenized) if self.docs else None

    def _build_dense(self, collection_name: str, persist_path: Optional[str]):
        import chromadb
        if persist_path:
            # Persistent store: embed once, reuse across runs (avoids the ~5min
            # CPU re-embed). Re-embeds only if the collection is missing/stale.
            self._client = chromadb.PersistentClient(path=persist_path)
            self._col = self._client.get_or_create_collection(collection_name)
            if self.docs and self._col.count() != len(self.docs):
                if self._col.count():
                    self._client.delete_collection(collection_name)
                    self._col = self._client.create_collection(collection_name)
                self._index_docs()
        else:
            self._client = chromadb.EphemeralClient()
            self._col = self._client.create_collection(f"{collection_name}_{next(_COLLECTION_COUNTER)}")
            self._index_docs()

    def _index_docs(self):
        if not self.docs:
            return
        embeddings = self.embedder.embed_documents([d.text for d in self.docs])
        self._col.add(
            ids=[d.id for d in self.docs],
            embeddings=embeddings,
            documents=[d.text for d in self.docs],
            metadatas=[d.metadata() for d in self.docs],
        )

    def search(self, query: str, k: int = 5) -> List[RetrievalHit]:
        if not self.docs:
            return []
        pool = min(max(k * 4, 10), len(self.docs))

        # Sparse ranking
        sparse_ids: List[str] = []
        if self._bm25 is not None:
            scores = self._bm25.get_scores(_tokenize(query))
            order = sorted(range(len(self.docs)), key=lambda i: -scores[i])[:pool]
            sparse_ids = [self.docs[i].id for i in order]

        # Dense ranking
        q_emb = self.embedder.embed_query(query)
        res = self._col.query(query_embeddings=[q_emb], n_results=pool)
        dense_ids = res.get("ids", [[]])[0]

        fused = _rrf([sparse_ids, dense_ids])
        ranked = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        return [RetrievalHit(doc=self.by_id[i], score=s) for i, s in ranked if i in self.by_id]
