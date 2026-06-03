"""Temporal-holdout leakage control for the Horak benchmark.

Restricts the RAG corpus (structured CIViC lookup + dense index) to evidence
PUBLISHED before a cutoff year (parsed from the CIViC citation), then re-runs
LLM+RAG oncogenicity classification vs the Horak 2022 gold. If accuracy holds as
the cutoff tightens, the system is not merely retrieving recent answer-stating
evidence — a stronger, leakage-controlled claim.

Note: this controls the RAG channel. LLM parametric knowledge (training cutoff)
still leaks; the no-RAG baseline (run_horak_benchmark) quantifies that floor.

Run:  python -m scripts.run_horak_temporal
Output: data/benchmark/horak_temporal.json
"""
import csv
import json
import re
import sys
import tempfile
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
from src.classify.llm import LLMClassifier
from src.eval.metrics import cohens_kappa

BENCH = Path("data/benchmark/horak_benchmark.tsv")
CIVIC = Path("data/benchmark/horak_civic.tsv")
DGIDB = Path("data/benchmark/horak_dgidb.json")
OUT = Path("data/benchmark/horak_temporal.json")
ENV = Path(__file__).resolve().parent.parent / ".env"

_ONC = {"Oncogenic", "Likely Oncogenic"}
_BEN = {"Benign", "Likely Benign"}
CUTOFFS = [None, 2018, 2015, 2012]


def collapse(x):
    return "oncogenic" if x in _ONC else ("benign" if x in _BEN else "vus")


def _year(citation):
    m = re.search(r"(19|20)\d\d", citation or "")
    return int(m.group(0)) if m else None


def filtered_civic(before):
    """Write a CIViC tsv restricted to citations published before `before` (year)."""
    rows = list(csv.DictReader(CIVIC.open(encoding="utf-8"), delimiter="\t"))
    if before is not None:
        rows = [r for r in rows if (_year(r.get("citation")) or 9999) < before]
    fd = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, newline="", encoding="utf-8")
    w = csv.DictWriter(fd, fieldnames=rows[0].keys() if rows else
                       list(csv.DictReader(CIVIC.open(encoding="utf-8"), delimiter="\t").fieldnames),
                       delimiter="\t")
    w.writeheader(); w.writerows(rows)
    fd.close()
    return Path(fd.name), len(rows)


def main():
    load_dotenv(ENV, override=True)
    d = pd.read_csv(BENCH, sep="\t")
    gold = [r["oncogenicity"] for _, r in d.iterrows()]
    llm = LLMClassifier()
    results = []

    for cutoff in CUTOFFS:
        civ_path, n_ev = filtered_civic(cutoff)
        agg = EvidenceAggregator(sources=[CivicSource(civ_path), DgidbSource(DGIDB)],
                                 variant_annotators=[AlphaMissenseAnnotator(offline=True)])
        docs = build_civic_corpus(civ_path)
        dense = HybridRetriever(docs, embedder=SentenceTransformerEmbedder()) if docs else None
        orch = HybridEvidenceRetriever(agg, dense=dense, graph=KnowledgeGraph.from_corpus(docs))

        preds = []
        for _, r in d.iterrows():
            v = Variant(chrom=str(r["b37_chr"]), pos=int(r["b37_pos"]), ref=str(r["b37_ref"]),
                        alt=str(r["b37_alt"]), gene=r["gene"], hgvsp=r["aa"], variant_type="SNV")
            ret = orch.retrieve(v)
            preds.append(llm.classify(v, ret.bundle, ret.graph).oncogenicity.value)
        civ_path.unlink(missing_ok=True)

        cp, cg = [collapse(p) for p in preds], [collapse(g) for g in gold]
        onc = [(p, g) for p, g in zip(preds, gold) if collapse(g) == "oncogenic"]
        res = {
            "cutoff_before": cutoff or "full",
            "corpus_evidence": n_ev,
            "acc_3class": round(sum(p == g for p, g in zip(cp, cg)) / len(cg), 3),
            "kappa_3class": cohens_kappa(cp, cg),
            "oncogenic_recall": round(sum(collapse(p) == "oncogenic" for p, _ in onc) / len(onc), 3),
        }
        results.append(res)
        print(f"[+] before {str(cutoff or 'full'):5s}: corpus={n_ev:3d} "
              f"acc3={res['acc_3class']} k3={res['kappa_3class']} onc_recall={res['oncogenic_recall']}")

    OUT.write_text(json.dumps({"results": results,
                               "note": "RAG corpus restricted to pre-cutoff literature; parametric floor = no-RAG in horak_results.json"}, indent=2))
    print(f"[+] wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
