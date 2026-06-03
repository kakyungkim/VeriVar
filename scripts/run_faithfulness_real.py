#!/usr/bin/env python3
"""Real-data anchor for the faithfulness gate: apply it to the ACTUAL no-retrieval LLM run.

The fault-injection ablation (`run_faithfulness_ablation.py`) shows the gate works on
synthetically corrupted calls. This script applies the *same* deterministic gate to the
REAL no-retrieval gpt-4o-mini arm recorded in `ablation_report.json` — the model that, with
no evidence bundle, still emitted confident citations (e.g. "ClinGen: BRAF") on 46.4% of
variants. With no bundle to ground them, every such citation is ungrounded; the gate drops
them (gate 1) and forces abstention (gate 2), converting real confident fabrication into
honest abstention. This is the real-model counterpart of the by-construction guarantee.

Usage:  python -m scripts.run_faithfulness_real
"""
import json
import os

from src.classify.faithfulness import enforce_faithfulness

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ABLATION = os.path.join(ROOT, "data", "outputs", "ablation_report.json")
OUT = os.path.join(ROOT, "data", "outputs", "faithfulness_real_norag.json")


def ungrounded_rate(variants):
    """Fraction of variants emitting >=1 citation that is absent from their bundle."""
    n = bad = 0
    for v in variants:
        cites = v["mode_a"].get("citations") or []
        if not cites:
            continue
        n += 1
        bundle_ids = {e["id"] for e in (v.get("bundle") or {}).get("evidences", [])}
        if any(c not in bundle_ids for c in cites):
            bad += 1
    return round(bad / len(variants), 3), bad, n


def main():
    if not os.path.exists(ABLATION):
        print(f"[!] {ABLATION} not found; run the ablation first.")
        return 1
    rows = json.load(open(ABLATION))["rows"]
    # Build the no-retrieval arm as faithfulness-gate inputs: the model's own norag call +
    # the citations it emitted, with an EMPTY bundle (no retrieval => nothing to cite).
    variants = []
    for r in rows:
        call = (r.get("llm_norag") or ["VUS"])[0]
        variants.append({
            "variant_key": r["variant_key"],
            "mode_a": {"oncogenicity": call, "tier": (r.get("llm_norag") or [None, None])[1],
                       "rationale": "", "citations": list(r.get("norag_citations") or []),
                       "confidence": 0.9, "abstained": False},
            "bundle": {"evidences": []},
        })

    before_rate, before_bad, before_n = ungrounded_rate(variants)
    enforced = [enforce_faithfulness(v) for v in variants]
    after_rate, after_bad, after_n = ungrounded_rate(enforced)
    n_abstained = sum(1 for v in enforced if v["mode_a"].get("abstained"))
    n_corrected = sum(1 for v in enforced if v["faithfulness_audit"]["corrected"])

    report = {
        "n_variants": len(variants),
        "arm": "real no-retrieval gpt-4o-mini (from ablation_report.json)",
        "before_enforcement": {"ungrounded_citation_rate": before_rate,
                               "variants_with_ungrounded_citations": before_bad},
        "after_enforcement": {"ungrounded_citation_rate": after_rate,
                              "variants_with_ungrounded_citations": after_bad,
                              "variants_abstained": n_abstained},
        "variants_corrected_by_gate": n_corrected,
        "note": "Real model, not fault injection: with no evidence bundle every emitted citation "
                "is ungrounded; the gate drops them and forces abstention, so a real 46% confident-"
                "fabrication rate becomes 0% by construction (honest abstention).",
    }
    json.dump(report, open(OUT, "w"), indent=2)
    print(f"[+] Faithfulness gate on the REAL no-retrieval arm (n={len(variants)})")
    print(f"    ungrounded-citation rate : {before_rate} ({before_bad}/{len(variants)}) "
          f"-> {after_rate} (0 by construction)")
    print(f"    variants forced to abstain by the gate : {n_abstained}/{len(variants)}")
    print(f"    -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    raise SystemExit(main())
