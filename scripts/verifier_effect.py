"""Quantify the agentic verifier's net effect + clean (un-capped) calibration.

Compares the canonical verified run against a no-verifier run, and computes
voting-confidence calibration on the no-verifier output (whose confidence is the
raw voting agreement, not capped by the verifier).

Prereq: python -m src.pipeline --vote --dense --out cohort_noverify
Run:     python -m scripts.verifier_effect
Output:  data/outputs/verifier_effect.json
"""
import json
import sys
from pathlib import Path

from src.eval.analyses import verifier_effect, confidence_calibration

VERIFIED = Path("data/outputs/cohort_interpretation.json")
NOVERIFY = Path("data/outputs/cohort_noverify.json")
OUT = Path("data/outputs/verifier_effect.json")


def main():
    if not (VERIFIED.exists() and NOVERIFY.exists()):
        print("[!] need both cohort_interpretation.json and cohort_noverify.json")
        return 1
    ver = json.loads(VERIFIED.read_text())["variants"]
    nov = json.loads(NOVERIFY.read_text())["variants"]

    eff = verifier_effect(ver, nov)
    eff["clean_calibration_no_verify"] = confidence_calibration(nov)
    OUT.write_text(json.dumps(eff, indent=2))

    print(f"[8] verifier changed Mode-A tier on {eff['tier_changed_by_verifier']} variants: "
          f"{eff['moved_toward_rule']} toward rule, {eff['moved_away_from_rule']} away")
    print(f"    tier concordance: no-verify {eff['tier_concordance_no_verify']} "
          f"-> verified {eff['tier_concordance_verified']}")
    print("    clean calibration (raw voting agreement, no verifier cap):")
    for k, b in eff["clean_calibration_no_verify"].items():
        print(f"      {k:14s} n={b['n']:2d} discordance={b['discordance_rate']}")
    print(f"[+] wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
