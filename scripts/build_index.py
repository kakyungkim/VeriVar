"""Build the persistent dense-RAG index over the CIViC corpus (one-time).

Embeds all CIViC evidence statements with the domain model into a persistent
Chroma store so the pipeline's dense arm loads instantly on later runs instead
of re-embedding (~5 min on CPU). Re-run only when the CIViC snapshot changes.

Run:  python -m scripts.build_index
"""
import sys
import time

from src.retrieval import build_civic_corpus, HybridRetriever, SentenceTransformerEmbedder

PERSIST = "data/knowledge/chroma_index"


def main():
    t0 = time.time()
    docs = build_civic_corpus()
    print(f"[*] {len(docs)} CIViC docs; embedding into {PERSIST} (first build is slow)…")
    r = HybridRetriever(docs, embedder=SentenceTransformerEmbedder(), persist_path=PERSIST)
    # sanity query
    hits = r.search("BRAF V600E melanoma vemurafenib", k=2)
    print(f"[+] indexed in {time.time()-t0:.0f}s; sample hit: {hits[0].doc.id if hits else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
