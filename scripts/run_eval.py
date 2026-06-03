"""Run the evaluation suite over a cohort_interpretation.json (no LLM calls).

Computes leakage-free faithfulness metrics + inter-mode agreement, plus the
external CIViC-assertion tier-accuracy check, and writes data/outputs/eval_report.json.

Run:  python -m scripts.run_eval
"""
import json
import sys
from pathlib import Path

from src.eval import evaluate, benchmark_tier_accuracy

RESULT = Path("data/outputs/cohort_interpretation.json")
OUT = Path("data/outputs/eval_report.json")


def main():
    if not RESULT.exists():
        print(f"[!] {RESULT} not found; run the pipeline first.")
        return 1
    data = json.loads(RESULT.read_text())
    variants = data["variants"]

    report = evaluate(variants)
    report["benchmark_civic_assertions"] = benchmark_tier_accuracy(variants)
    report["provenance"] = data.get("provenance", {})
    OUT.write_text(json.dumps(report, indent=2))

    h = report["hallucination"]
    f = report["directional_faithfulness"]
    ab = report["abstention"]
    g = report["citation_grounding"]
    k = report["inter_mode_agreement"]
    b = report["benchmark_civic_assertions"]
    print(f"[+] eval over {report['n_variants']} variants (techniques: {report['provenance'].get('techniques')})")
    print(f"    hallucinated-citation rate : {h['hallucination_rate']} ({h['n_hallucinating']}/{h['n_with_citations']})")
    print(f"    citation grounding rate    : {g['grounding_rate']} ({g['grounded']}/{g['n']})")
    print(f"    directional faithfulness   : {f['faithfulness_rate']} ({f['faithful']}/{f['checked']})")
    print(f"    abstention recall          : {ab['abstention_recall']} ({ab['abstained_when_no_evidence']}/{ab['no_evidence_variants']})")
    print(f"    inter-mode kappa           : onco={k['oncogenicity_kappa']} tier={k['tier_kappa']}")
    print(f"    CIViC-assertion tier acc   : A={b['mode_a_tier_accuracy']} B={b['mode_b_tier_accuracy']} (n={b['n_matched_cohort']})")
    print(f"[+] wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
