"""Horak rigor variants: second LLM model (--model) and LOVO holdout (--lovo).

--model NAME : run LLM+RAG oncogenicity on a different model (robustness to single-model).
--lovo       : leave-one-variant-out — remove each variant's OWN CIViC evidence from its
               bundle (curated-leakage holdout; keeps AlphaMissense + other-variant hits).
RAG-only (no rule/no-RAG) to keep cost low. Output: data/benchmark/horak_<tag>.json
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from src.models import Variant
from src.knowledge.aggregator import EvidenceAggregator
from src.knowledge.civic import CivicSource
from src.knowledge.dgidb import DgidbSource
from src.knowledge.alphamissense import AlphaMissenseAnnotator
from src.knowledge.base import normalize_protein_change
from src.retrieval import build_civic_corpus, HybridRetriever, SentenceTransformerEmbedder
from src.retrieval.graph import KnowledgeGraph
from src.retrieval.orchestrator import HybridEvidenceRetriever
from src.classify.llm import LLMClassifier
from src.eval.metrics import cohens_kappa

BENCH = Path("data/benchmark/horak_benchmark.tsv")
CIVIC = Path("data/benchmark/horak_civic.tsv")
DGIDB = Path("data/benchmark/horak_dgidb.json")
ENV = Path(__file__).resolve().parent.parent / ".env"
_ONC = {"Oncogenic", "Likely Oncogenic"}
_BEN = {"Benign", "Likely Benign"}


def coll(x):
    return "oncogenic" if x in _ONC else ("benign" if x in _BEN else "vus")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--lovo", action="store_true")
    ap.add_argument("--tag", default="run")
    a = ap.parse_args()
    load_dotenv(ENV, override=True)

    d = pd.read_csv(BENCH, sep="\t")
    agg = EvidenceAggregator(sources=[CivicSource(CIVIC), DgidbSource(DGIDB)],
                             variant_annotators=[AlphaMissenseAnnotator(offline=True)])
    docs = build_civic_corpus(CIVIC)
    dense = HybridRetriever(docs, embedder=SentenceTransformerEmbedder()) if docs else None
    orch = HybridEvidenceRetriever(agg, dense=dense, graph=KnowledgeGraph.from_corpus(docs))
    llm = LLMClassifier(model=a.model)
    print(f"[*] tag={a.tag} model={a.model} lovo={a.lovo} corpus={len(docs)}")

    gold, pred, rows = [], [], []
    for i, r in d.iterrows():
        v = Variant(chrom=str(r["b37_chr"]), pos=int(r["b37_pos"]), ref=str(r["b37_ref"]),
                    alt=str(r["b37_alt"]), gene=r["gene"], hgvsp=r["aa"], variant_type="SNV")
        ret = orch.retrieve(v)
        if a.lovo:
            own = normalize_protein_change(r["aa"]).upper()
            ret.bundle.evidences = [e for e in ret.bundle.evidences
                                    if not (e.source == "CIViC"
                                            and normalize_protein_change(e.variant or "").upper() == own)]
        lm = llm.classify(v, ret.bundle, ret.graph).oncogenicity.value
        gold.append(r["oncogenicity"]); pred.append(lm)
        rows.append({"variant": f"{r['gene']} {r['aa']}", "gold": r["oncogenicity"], "pred": lm,
                     "n_evidence": len(ret.bundle.evidences)})
        if (i + 1) % 10 == 0:
            print(f"    {i+1}/{len(d)}")

    cp, cg = [coll(p) for p in pred], [coll(g) for g in gold]
    onc = [(coll(p), coll(g)) for p, g in zip(pred, gold) if coll(g) == "oncogenic"]
    rep = {"model": a.model, "lovo": a.lovo, "n": len(gold),
           "acc_5class": round(sum(p == g for p, g in zip(pred, gold)) / len(gold), 3),
           "acc_3class": round(sum(p == g for p, g in zip(cp, cg)) / len(cg), 3),
           "kappa_3class": cohens_kappa(cp, cg),
           "oncogenic_recall": round(sum(p == "oncogenic" for p, _ in onc) / len(onc), 3),
           "mean_evidence": round(sum(r["n_evidence"] for r in rows) / len(rows), 2),
           "rows": rows}
    out = Path(f"data/benchmark/horak_{a.tag}.json"); out.write_text(json.dumps(rep, indent=2))
    print(f"[+] {a.tag}: acc5={rep['acc_5class']} acc3={rep['acc_3class']} "
          f"k3={rep['kappa_3class']} onc_recall={rep['oncogenic_recall']} mean_ev={rep['mean_evidence']} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
