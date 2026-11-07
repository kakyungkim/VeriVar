"""Known/Novel evidence stratification of the Horak-70 external benchmark.

Splits the 70 gold-standard variants by whether the retrieval layer found any
CURATED CIViC evidence for that exact protein change:

  known : >= 1 CIViC evidence item  (curated clinical evidence exists)
  novel :    0 CIViC evidence items (only the coordinate-keyed AlphaMissense
             prior, or nothing at all)

and reports, per stratum, three-class accuracy with bootstrap CIs, the class
base rate and majority-class baseline, and the oncogenic-versus-rest operating
point (sensitivity / specificity) for every arm. This is a post-hoc, descriptive
re-aggregation of an existing run: it makes no LLM calls and needs no network.
Predictions are read from the committed benchmark outputs; only the evidence
composition is recomputed, and the recomputed bundle sizes are asserted against
the ``n_evidence`` recorded by the original run.

Prereq: python -m scripts.run_horak_benchmark && python -m scripts.run_horak_vicc
Run:    python -m scripts.run_horak_known_novel
Output: data/benchmark/horak_known_novel.json

Options (added 2026-09-24 for the per-configuration VICC suite): ``--vicc`` reads the rule-arm
predictions from another horak_vicc.json, ``--out`` writes elsewhere, and
``--composition-from`` reuses the evidence composition recorded in an earlier output of this
script instead of rebuilding the retrieval stack (~15 min). The composition does not depend
on the VICC configuration, so only the "vicc" arm changes between configurations.
"""
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from src.models import Variant
from src.knowledge.aggregator import EvidenceAggregator
from src.knowledge.civic import CivicSource
from src.knowledge.dgidb import DgidbSource
from src.knowledge.alphamissense import AlphaMissenseAnnotator
from src.retrieval import build_civic_corpus, HybridRetriever, SentenceTransformerEmbedder
from src.retrieval.graph import KnowledgeGraph
from src.retrieval.orchestrator import HybridEvidenceRetriever
from src.eval.stats import boundary_ci, bootstrap_ci, mcnemar

BENCH = Path("data/benchmark/horak_benchmark.tsv")
CIVIC = Path("data/benchmark/horak_civic.tsv")
DGIDB = Path("data/benchmark/horak_dgidb.json")
RESULTS = Path("data/benchmark/horak_results.json")
VICC = Path("data/benchmark/horak_vicc.json")
OUT = Path("data/benchmark/horak_known_novel.json")

_ONC = {"Oncogenic", "Likely Oncogenic"}
_BEN = {"Benign", "Likely Benign"}
ARMS = [("vicc", "citable VICC rule arm"), ("rule", "simplified rule"),
        ("llm_rag", "generative (retrieval)"), ("llm_norag", "generative (no retrieval)")]


def collapse(x: str) -> str:
    if x in _ONC:
        return "oncogenic"
    if x in _BEN:
        return "benign"
    return "vus"


def _binary(sub, key):
    """Oncogenic-versus-rest confusion counts for one arm on one stratum."""
    tp = sum(1 for r in sub if collapse(r["gold"]) == "oncogenic" and collapse(r[key]) == "oncogenic")
    fn = sum(1 for r in sub if collapse(r["gold"]) == "oncogenic" and collapse(r[key]) != "oncogenic")
    fp = sum(1 for r in sub if collapse(r["gold"]) != "oncogenic" and collapse(r[key]) == "oncogenic")
    tn = sum(1 for r in sub if collapse(r["gold"]) != "oncogenic" and collapse(r[key]) != "oncogenic")
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "sensitivity_onc": round(tp / (tp + fn), 3) if tp + fn else None,
            "specificity_onc": round(tn / (tn + fp), 3) if tn + fp else None,
            "sensitivity_onc_exact_ci": boundary_ci(tp, tp + fn),
            "specificity_onc_exact_ci": boundary_ci(tn, tn + fp)}


def evidence_composition() -> dict:
    """Recompute per-variant evidence composition with the benchmark's retrieval stack."""
    d = pd.read_csv(BENCH, sep="\t")
    agg = EvidenceAggregator(sources=[CivicSource(CIVIC), DgidbSource(DGIDB)],
                             variant_annotators=[AlphaMissenseAnnotator(offline=True)])
    docs = build_civic_corpus(CIVIC)
    dense = HybridRetriever(docs, embedder=SentenceTransformerEmbedder()) if docs else None
    orch = HybridEvidenceRetriever(agg, dense=dense, graph=KnowledgeGraph.from_corpus(docs))
    print(f"[*] {len(d)} Horak variants; corpus={len(docs)} docs", flush=True)

    comp = {}
    for i, r in d.iterrows():
        v = Variant(chrom=str(r["b37_chr"]), pos=int(r["b37_pos"]), ref=str(r["b37_ref"]),
                    alt=str(r["b37_alt"]), gene=r["gene"], hgvsp=r["aa"], variant_type="SNV")
        b = orch.retrieve(v).bundle
        src = Counter(e.source for e in b.evidences)
        comp[f"{r['gene']} {r['aa']}"] = {
            "n_evidence": len(b.evidences), "n_civic": src.get("CIViC", 0),
            "n_alphamissense": src.get("AlphaMissense", 0),
            "n_drugs": len(b.drugs), "n_trials": len(b.trials)}
        if (i + 1) % 20 == 0:
            print(f"    {i+1}/{len(d)}", flush=True)
    return comp


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Horak-70 known/novel stratification")
    ap.add_argument("--vicc", default=str(VICC))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--composition-from", default=None,
                    help="reuse per-variant evidence composition from an earlier output")
    args = ap.parse_args()
    out_path = Path(args.out)
    if args.composition_from:
        keys = ("n_evidence", "n_civic", "n_alphamissense", "n_drugs", "n_trials")
        comp = {r["variant"]: {k: r[k] for k in keys}
                for r in json.loads(Path(args.composition_from).read_text())["rows"]}
    else:
        comp = evidence_composition()
    res = json.loads(RESULTS.read_text())["rows"]
    vicc = {r["variant"]: r for r in json.loads(Path(args.vicc).read_text())["rows"]}

    # Integrity: the recomputed bundle must match the bundle the original run scored.
    bad = [(r["variant"], r["n_evidence"], comp[r["variant"]]["n_evidence"])
           for r in res if comp[r["variant"]]["n_evidence"] != r["n_evidence"]]
    if bad:
        raise SystemExit(f"[FAIL] evidence recompute diverged from the scored run: {bad[:5]}")
    print(f"[check] n_evidence reproduced for {len(res)}/{len(res)} variants")

    rows = [{**r, **comp[r["variant"]], "vicc": vicc[r["variant"]]["vicc"],
             "stratum": "known" if comp[r["variant"]]["n_civic"] > 0 else "novel"} for r in res]

    out = {
        "definition": ("known = >=1 curated CIViC evidence item retrieved for the exact protein "
                       "change; novel = 0 such items (AlphaMissense prior only, or nothing)"),
        "note": ("Post-hoc descriptive stratification of an existing run. Class base rates differ "
                 "between strata, so accuracies are reported against each stratum's majority-class "
                 "baseline and are not comparable across strata as a difficulty measure."),
        "n_total": len(rows), "strata": {},
    }
    for name in ("known", "novel", "all"):
        sub = rows if name == "all" else [r for r in rows if r["stratum"] == name]
        gold3 = Counter(collapse(r["gold"]) for r in sub)
        maj, majn = gold3.most_common(1)[0]
        blk = {
            "n": len(sub),
            "gold_3class": dict(gold3),
            "gold_5class": dict(Counter(r["gold"] for r in sub)),
            "majority_class": maj,
            "majority_baseline_accuracy": round(majn / len(sub), 3),
            "evidence": {
                "civic_items_total": sum(r["n_civic"] for r in sub),
                "alphamissense_items_total": sum(r["n_alphamissense"] for r in sub),
                "variants_with_alphamissense": sum(1 for r in sub if r["n_alphamissense"] > 0),
                "variants_with_no_evidence_at_all": sum(
                    1 for r in sub if r["n_civic"] == 0 and r["n_alphamissense"] == 0),
            },
            "arms": {},
        }
        for key, label in ARMS:
            corr = [1.0 if collapse(r[key]) == collapse(r["gold"]) else 0.0 for r in sub]
            ci = bootstrap_ci(corr)
            blk["arms"][key] = {
                "label": label,
                "accuracy_3class": ci,
                "accuracy_5class": round(sum(r[key] == r["gold"] for r in sub) / len(sub), 3),
                "lift_over_majority": round(ci["point"] - blk["majority_baseline_accuracy"], 3),
                "pred_3class": dict(Counter(collapse(r[key]) for r in sub)),
                "vus_rate": round(sum(collapse(r[key]) == "vus" for r in sub) / len(sub), 3),
                "oncogenic_vs_rest": _binary(sub, key),
            }
        a = [collapse(r["llm_rag"]) == collapse(r["gold"]) for r in sub]
        b = [collapse(r["llm_norag"]) == collapse(r["gold"]) for r in sub]
        blk["mcnemar_rag_vs_norag_3class"] = mcnemar(a, b)
        out["strata"][name] = blk

    out["vicc_arm_misses"] = [
        {"variant": r["variant"], "gold": r["gold"], "vicc": r["vicc"], "stratum": r["stratum"],
         "n_civic": r["n_civic"], "n_alphamissense": r["n_alphamissense"]}
        for r in rows if collapse(r["gold"]) == "oncogenic" and collapse(r["vicc"]) != "oncogenic"]
    out["vicc_arm_overcalls"] = [
        {"variant": r["variant"], "gold": r["gold"], "vicc": r["vicc"], "stratum": r["stratum"],
         "n_civic": r["n_civic"], "n_alphamissense": r["n_alphamissense"]}
        for r in rows if collapse(r["gold"]) != "oncogenic" and collapse(r["vicc"]) == "oncogenic"]
    out["rows"] = rows

    if args.composition_from:
        out["composition_from"] = args.composition_from
    out_path.write_text(json.dumps(out, indent=1))
    print(f"[ok] wrote {out_path}")
    for name in ("known", "novel", "all"):
        s = out["strata"][name]
        v = s["arms"]["vicc"]
        print(f"  {name:6} n={s['n']:>2}  VICC acc={v['accuracy_3class']['point']:.3f} "
              f"[{v['accuracy_3class']['lo']:.3f}-{v['accuracy_3class']['hi']:.3f}]  "
              f"majority={s['majority_baseline_accuracy']:.3f}  "
              f"sens={v['oncogenic_vs_rest']['sensitivity_onc']}  "
              f"spec={v['oncogenic_vs_rest']['specificity_onc']}")


if __name__ == "__main__":
    main()
