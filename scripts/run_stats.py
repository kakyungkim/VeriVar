"""Bootstrap CIs + McNemar significance on the headline numbers (no LLM).

Run:  python -m scripts.run_stats
Output: data/outputs/stats_report.json
"""
import json
import sys
from pathlib import Path

from src.eval.stats import bootstrap_ci, mcnemar

OUT = Path("data/outputs/stats_report.json")
_ONC = {"Oncogenic", "Likely Oncogenic"}
_BEN = {"Benign", "Likely Benign"}


def coll(x):
    return "oncogenic" if x in _ONC else ("benign" if x in _BEN else "vus")


def main():
    rep = {}

    # --- Horak external benchmark: accuracy CIs + McNemar ---
    hr = json.loads(Path("data/benchmark/horak_results.json").read_text())
    rows = hr["rows"]
    c_rule = [coll(r["rule"]) == coll(r["gold"]) for r in rows]
    c_rag = [coll(r["llm_rag"]) == coll(r["gold"]) for r in rows]
    c_norag = [coll(r["llm_norag"]) == coll(r["gold"]) for r in rows]
    rep["horak_3class_accuracy_ci"] = {
        "rule": bootstrap_ci([int(x) for x in c_rule]),
        "llm_rag": bootstrap_ci([int(x) for x in c_rag]),
        "llm_norag": bootstrap_ci([int(x) for x in c_norag]),
    }
    rep["horak_mcnemar"] = {
        "rag_vs_norag": mcnemar(c_rag, c_norag),
        "rag_vs_rule": mcnemar(c_rag, c_rule),
    }

    # --- Cohort dual-mode concordance CIs ---
    ci = json.loads(Path("data/outputs/cohort_interpretation.json").read_text())["variants"]
    rep["cohort_concordance_ci"] = {
        "oncogenicity": bootstrap_ci([int(v["mode_a"]["oncogenicity"] == v["mode_b"]["oncogenicity"]) for v in ci]),
        "tier": bootstrap_ci([int(v["mode_a"]["tier"] == v["mode_b"]["tier"]) for v in ci]),
    }

    # --- Ablation: citation-fabrication rate CI (no-RAG) ---
    ab = json.loads(Path("data/outputs/ablation_report.json").read_text())
    fab = [1 if r["norag_citations"] else 0 for r in ab["rows"]]
    rep["norag_citation_fabrication_ci"] = bootstrap_ci(fab)

    OUT.write_text(json.dumps(rep, indent=2))
    print("=== Horak 3-class accuracy (95% CI) ===")
    for k, v in rep["horak_3class_accuracy_ci"].items():
        print(f"  {k:10s} {v['point']} [{v['lo']}, {v['hi']}]  (n={v['n']})")
    print("=== McNemar (paired) ===")
    for k, v in rep["horak_mcnemar"].items():
        print(f"  {k:14s} a_better={v['a_better']} b_better={v['b_better']} p={v['p_value']}")
    print("=== Cohort concordance (95% CI) ===")
    for k, v in rep["cohort_concordance_ci"].items():
        print(f"  {k:14s} {v['point']} [{v['lo']}, {v['hi']}]")
    f = rep["norag_citation_fabrication_ci"]
    print(f"no-RAG citation fabrication: {f['point']} [{f['lo']}, {f['hi']}]")
    print(f"[+] wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
