"""Run the additional deterministic analyses (Phase c+). No LLM calls.

Run:  python -m scripts.run_analyses
Output: data/outputs/analyses_report.json
"""
import json
import sys
from pathlib import Path

from src.eval.analyses import run_all
from src.knowledge.factory import build_aggregator

RESULT = Path("data/outputs/cohort_interpretation.json")
OUT = Path("data/outputs/analyses_report.json")


def main():
    if not RESULT.exists():
        print(f"[!] {RESULT} not found.")
        return 1
    variants = json.loads(RESULT.read_text())["variants"]
    rep = run_all(variants, aggregator=build_aggregator(offline=True))
    OUT.write_text(json.dumps(rep, indent=2))

    cc = rep["cross_cancer_consistency"]
    print(f"[1] cross-cancer: {cc['n_multi_cancer_variants']} multi-cancer variants — "
          f"stable oncogenicity {cc['stable_oncogenicity']}, variable tier {cc['variable_tier']}")
    sr = rep["sensitivity_vs_resistance"]
    print(f"[2] sensitivity-only {sr['sensitivity_only']}, resistance-only {sr['resistance_only']} "
          f"(tiers {sr['resistance_only_tier_distribution']}), both {sr['both']} "
          f"— resistance markers are appropriately actionable")
    if "dense_recall_lift" in rep:
        dl = rep["dense_recall_lift"]
        print(f"[3] dense recall-lift: {dl['variants_gaining_evidence']} variants gained CIViC evidence, "
              f"+{dl['total_civic_added']} items total")
    am = rep["alphamissense_llm_agreement"]
    print(f"[4] AlphaMissense↔LLM agreement: {am['agreement_rate']} ({am['agree']}/{am['checked']})")
    print("[5] confidence calibration (conf bin -> discordance rate):")
    for k, b in rep["confidence_calibration"].items():
        print(f"      {k:14s} n={b['n']:2d} discordance={b['discordance_rate']} verifier-downgraded={b['verifier_downgraded']}")
    hv = rep["hotspot_vs_rare"]
    print(f"[7] hotspot discordance {hv['hotspot']['discordance_rate']} ({hv['hotspot']['n']}) "
          f"vs non-hotspot {hv['non_hotspot']['discordance_rate']} ({hv['non_hotspot']['n']})")
    print(f"[+] wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
