"""Embedding ablation (no LLM): retrieval recall@5 of each variant's own evidence.

Compares domain (NeuML/PubMedBERT), general (MiniLM), and OpenAI embeddings on the
Horak CIViC corpus. Metric: for each of the 70 variants, does a top-5 dense hit match
its gene+protein-change? (a retrieval-quality proxy). OpenAI needs OPENAI_API_KEY.

Run:  python -m scripts.run_embed_ablation
Output: data/benchmark/embed_ablation.json
"""
import json
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from src.knowledge.base import normalize_protein_change
from src.retrieval import build_civic_corpus, HybridRetriever, SentenceTransformerEmbedder, OpenAIEmbedder

BENCH = Path("data/benchmark/horak_benchmark.tsv")
CIVIC = Path("data/benchmark/horak_civic.tsv")
OUT = Path("data/benchmark/embed_ablation.json")
ENV = Path(__file__).resolve().parent.parent / ".env"


def recall_at_5(retriever, d):
    hit = 0
    for _, r in d.iterrows():
        g = r["gene"].upper(); pc = normalize_protein_change(r["aa"]).upper()
        for h in retriever.search(f"{r['gene']} {r['aa']}", k=5):
            if h.doc.gene.upper() == g and normalize_protein_change(h.doc.variant or "").upper() == pc:
                hit += 1
                break
    return round(hit / len(d), 3)


def main():
    load_dotenv(ENV, override=True)
    d = pd.read_csv(BENCH, sep="\t")
    docs = build_civic_corpus(CIVIC)
    embedders = {
        "pubmedbert(domain)": SentenceTransformerEmbedder("NeuML/pubmedbert-base-embeddings"),
        "minilm(general)": SentenceTransformerEmbedder("sentence-transformers/all-MiniLM-L6-v2"),
        "openai-3-small": OpenAIEmbedder(),
    }
    res = {}
    for name, emb in embedders.items():
        try:
            r5 = recall_at_5(HybridRetriever(docs, embedder=emb), d)
            res[name] = r5
            print(f"[+] {name:20s} recall@5={r5}")
        except Exception as e:  # noqa: BLE001
            res[name] = f"ERR: {e}"
            print(f"[!] {name}: {e}")
    OUT.write_text(json.dumps({"corpus": len(docs), "n_variants": len(d), "recall_at_5": res}, indent=2))
    print(f"[+] wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
