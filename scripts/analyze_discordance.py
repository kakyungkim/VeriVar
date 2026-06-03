"""Typed discordance error analysis (Phase c). No LLM calls.

Run:  python -m scripts.analyze_discordance
Output: data/outputs/discordance_analysis.json
"""
import json
import sys
from pathlib import Path

from src.eval.discordance import analyze

RESULT = Path("data/outputs/cohort_interpretation.json")
OUT = Path("data/outputs/discordance_analysis.json")

_LABELS = {
    "rule_overcall_corrected_by_llm": "Rule over-calls a driver; LLM reads evidence → not a driver (beyond-rules)",
    "llm_overcall_vs_rule": "LLM calls driver; rule does not",
    "verifier_tier_downgrade": "Verifier downgraded LLM tier vs rule",
    "oncogenic_confidence": "Oncogenic vs Likely Oncogenic (confidence)",
    "benign_label": "VUS vs Likely Benign (both not a driver)",
    "tier_boundary": "Same oncogenicity, adjacent tier boundary",
    "other": "Other",
}


def main():
    if not RESULT.exists():
        print(f"[!] {RESULT} not found.")
        return 1
    data = json.loads(RESULT.read_text())
    rep = analyze(data["variants"])
    rep["provenance"] = data.get("provenance", {})
    OUT.write_text(json.dumps(rep, indent=2))

    print(f"[+] {rep['n_discordant']}/{rep['n_total']} discordant "
          f"({rep['adjacent']} adjacent, {rep['gross']} gross); "
          f"LLM more conservative in {rep['llm_more_conservative']}.")
    print("    Categories:")
    for cat, n in rep["category_counts"].items():
        print(f"      {n:2d}  {_LABELS.get(cat, cat)}")
    print("    Examples (beyond-rules):")
    for x in rep["categories"].get("rule_overcall_corrected_by_llm", [])[:6]:
        print(f"      {x['variant']:18s} {x['cancer'][:11]:11s} A={x['mode_a']:24s} B={x['mode_b']}")
    print(f"[+] wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
