"""External oncogenicity benchmark vs the Horak 2022 VICC gold standard.

For each of the 70 expert-classified variants, build evidence (Horak-gene CIViC +
DGIdb + AlphaMissense + dense over the Horak corpus) and compare rule / LLM+RAG /
LLM-no-RAG oncogenicity to the gold label. Reports 5-class accuracy, collapsed
3-class accuracy, and Cohen's kappa.

LEAKAGE NOTE: famous variants' CIViC evidence is in the corpus, so this is
"retrieval-augmented accuracy vs a published expert standard", not held-out
generalisation. The no-RAG arm isolates the LLM's parametric knowledge.

Prereq: python -m scripts.build_horak_benchmark && python -m scripts.fetch_horak_evidence
Run:    python -m scripts.run_horak_benchmark
Output: data/benchmark/horak_results.json
"""
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
from src.retrieval import build_civic_corpus, HybridRetriever, SentenceTransformerEmbedder
from src.retrieval.graph import KnowledgeGraph
from src.retrieval.orchestrator import HybridEvidenceRetriever
from src.classify.rules import RuleClassifier
from src.classify.llm import LLMClassifier
from src.eval.metrics import cohens_kappa

BENCH = Path("data/benchmark/horak_benchmark.tsv")
CIVIC = Path("data/benchmark/horak_civic.tsv")
DGIDB = Path("data/benchmark/horak_dgidb.json")
OUT = Path("data/benchmark/horak_results.json")
ENV = Path(__file__).resolve().parent.parent / ".env"

_ONC = {"Oncogenic", "Likely Oncogenic"}
_BEN = {"Benign", "Likely Benign"}


def collapse(x):
    if x in _ONC:
        return "oncogenic"
    if x in _BEN:
        return "benign"
    return "vus"


def _scores(pred, gold):
    acc5 = round(sum(p == g for p, g in zip(pred, gold)) / len(gold), 3)
    cp, cg = [collapse(p) for p in pred], [collapse(g) for g in gold]
    acc3 = round(sum(p == g for p, g in zip(cp, cg)) / len(gold), 3)
    return {"accuracy_5class": acc5, "accuracy_3class": acc3,
            "kappa_5class": cohens_kappa(pred, gold), "kappa_3class": cohens_kappa(cp, cg)}


def main():
    load_dotenv(ENV, override=True)
    d = pd.read_csv(BENCH, sep="\t")
    agg = EvidenceAggregator(
        sources=[CivicSource(CIVIC), DgidbSource(DGIDB)],
        variant_annotators=[AlphaMissenseAnnotator(offline=True)])
    docs = build_civic_corpus(CIVIC)
    dense = HybridRetriever(docs, embedder=SentenceTransformerEmbedder()) if docs else None
    kg = KnowledgeGraph.from_corpus(docs)
    orch = HybridEvidenceRetriever(agg, dense=dense, graph=kg)
    rule_clf, llm = RuleClassifier(), LLMClassifier()
    live = llm.available()
    print(f"[*] {len(d)} Horak variants; corpus={len(docs)} docs; LLM {'live' if live else 'off'}")

    gold, rule_p, llm_p, norag_p, rows = [], [], [], [], []
    for i, r in d.iterrows():
        v = Variant(chrom=str(r["b37_chr"]), pos=int(r["b37_pos"]), ref=str(r["b37_ref"]),
                    alt=str(r["b37_alt"]), gene=r["gene"], hgvsp=r["aa"], variant_type="SNV")
        ret = orch.retrieve(v)
        g = r["oncogenicity"]
        ru = rule_clf.classify(v, ret.bundle).oncogenicity.value
        if live:
            lm = llm.classify(v, ret.bundle, ret.graph).oncogenicity.value
            nr = llm.classify_parametric(v).oncogenicity.value
        else:
            lm = nr = ru
        gold.append(g); rule_p.append(ru); llm_p.append(lm); norag_p.append(nr)
        rows.append({"variant": f"{r['gene']} {r['aa']}", "gold": g, "rule": ru,
                     "llm_rag": lm, "llm_norag": nr, "n_evidence": len(ret.bundle.evidences)})
        if (i + 1) % 10 == 0:
            print(f"    {i+1}/{len(d)}")

    report = {
        "n": len(gold),
        "gold_distribution": dict(Counter(gold)),
        "rule": _scores(rule_p, gold),
        "llm_with_rag": _scores(llm_p, gold),
        "llm_no_rag": _scores(norag_p, gold),
        "leakage_note": "retrieval-augmented accuracy vs published VICC standard (corpus overlap; not held-out)",
        "rows": rows,
    }
    OUT.write_text(json.dumps(report, indent=2))
    for name in ("rule", "llm_with_rag", "llm_no_rag"):
        s = report[name]
        print(f"[+] {name:12s} acc5={s['accuracy_5class']} acc3={s['accuracy_3class']} "
              f"k5={s['kappa_5class']} k3={s['kappa_3class']}")
    print(f"[+] wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
