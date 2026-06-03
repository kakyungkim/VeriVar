#!/usr/bin/env python3
"""Fault-injection ablation: does the faithfulness gate hold under an unfaithful model?

The deterministic mock cohort already scores 1.0 on every faithfulness metric, so it
cannot *show* the gate working. This script simulates a fallible Generative model by
injecting the three real LLM failure modes into a copy of the cohort —

  * fabricated citation  (cite an id that was never retrieved),
  * directional contradiction  (assert oncogenic while citing only benign evidence),
  * over-confidence  (a non-abstained call on an empty bundle),

deterministically over a fixed fraction of variants — then measures the faithfulness
metrics (a) on the corrupted cohort and (b) after :func:`enforce_faithfulness`. The gate
is a *worst-case guarantee*: however unfaithful the upstream model, the shipped metrics
return to their ideal. This is the auditability claim, demonstrated rather than asserted.

Usage:  python -m scripts.run_faithfulness_ablation
"""
import copy
import json
import os

from src.classify.faithfulness import enforce_cohort
from src.eval.metrics import (
    hallucination_rate, citation_grounding_rate, directional_faithfulness,
    abstention_metrics,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COHORT = os.path.join(ROOT, "data", "outputs", "cohort_interpretation.json")
OUT = os.path.join(ROOT, "data", "outputs", "faithfulness_ablation.json")

_BENIGN_EV = {"id": "CIViC:INJECTED_BENIGN", "source": "CIViC", "direction": "Supports",
              "significance": "Benign"}


def corrupt(variants):
    """Inject one of three faithfulness violations into every third variant (deterministic)."""
    out = copy.deepcopy(variants)
    injected = {"fabricated": 0, "contradiction": 0, "overconfident": 0}
    for i, v in enumerate(out):
        a = v.get("mode_a") or {}
        if a.get("abstained"):
            continue
        mode = i % 3
        if mode == 0:                                   # fabricated citation
            a["citations"] = list(a.get("citations") or []) + ["CIViC:EID_FABRICATED"]
            injected["fabricated"] += 1
        elif mode == 1:                                 # directional contradiction
            a["oncogenicity"] = "Oncogenic"
            a["citations"] = ["CIViC:INJECTED_BENIGN"]
            v["bundle"] = {"evidences": [_BENIGN_EV]}
            injected["contradiction"] += 1
        else:                                           # over-confident, no evidence
            a["oncogenicity"] = "Oncogenic"
            a["abstained"] = False
            a["citations"] = []
            v["bundle"] = {"evidences": []}
            injected["overconfident"] += 1
        v["mode_a"] = a
    return out, injected


def metrics(variants):
    return {
        "hallucination_rate": hallucination_rate(variants)["hallucination_rate"],
        "citation_grounding_rate": citation_grounding_rate(variants)["grounding_rate"],
        "directional_faithfulness": directional_faithfulness(variants)["faithfulness_rate"],
        "abstention_recall": abstention_metrics(variants)["abstention_recall"],
    }


def main():
    if not os.path.exists(COHORT):
        print(f"[!] {COHORT} not found; run the pipeline first.")
        return 1
    variants = json.load(open(COHORT))["variants"]
    corrupted, injected = corrupt(variants)
    enforced = enforce_cohort(corrupted)

    report = {
        "n_variants": len(variants),
        "injected_violations": injected,
        "before_enforcement": metrics(corrupted),
        "after_enforcement": metrics(enforced),
        "n_corrected": sum(e["faithfulness_audit"]["corrected"] for e in enforced),
        "note": "Fault-injection stress test: faithfulness metrics on a deliberately "
                "corrupted cohort, before vs after the deterministic enforcement gate. "
                "The gate is a worst-case guarantee, not a measurement of any real model.",
    }
    json.dump(report, open(OUT, "w"), indent=2)
    b, a = report["before_enforcement"], report["after_enforcement"]
    print(f"[+] Faithfulness fault-injection ablation (n={len(variants)}, "
          f"injected={sum(injected.values())} violations)")
    print(f"    {'metric':26s} {'corrupted':>10s} -> {'enforced':>9s}")
    for k in b:
        print(f"    {k:26s} {str(b[k]):>10s} -> {str(a[k]):>9s}")
    print(f"    variants corrected by gate : {report['n_corrected']}")
    print(f"    -> written to {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    raise SystemExit(main())
