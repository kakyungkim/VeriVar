"""Recompute the citation-grounding claim for the input-context ablation.

``run_context_ablation.py`` records each arm's citations but not the evidence
identifiers that were available to the model, so the manuscript's claim that no
ablation citation fell outside its retrieved bundle cannot be recomputed from
``context_ablation.json`` alone. Retrieval is deterministic and costs nothing,
so this script rebuilds every arm's bundle and checks the already-recorded
citations against it. No model call is made, and the saved labels are left
untouched, so the numbers the manuscript already reports do not move.

The baseline arm doubles as a self-check: ``context_ablation.json`` does store
baseline identifiers, so a mismatch there means the retrieval state has drifted
since the run and the rest of the output cannot be trusted either.

Usage::

    python -m scripts.check_ablation_citation_grounding
    python -m scripts.check_ablation_citation_grounding --out data/outputs/x.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

ABLATION = Path("data/outputs/context_ablation.json")
OUT = Path("data/outputs/context_ablation_grounding.json")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ablation", type=Path, default=ABLATION)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    from dotenv import load_dotenv

    from src.classify.select import select_for_classification
    from src.cohort.loader import load_cohort
    from src.knowledge.factory import build_aggregator
    from src.pipeline import ENV_PATH, build_retriever
    from src.retrieval.graph import KnowledgeGraph

    load_dotenv(ENV_PATH, override=True)

    report = json.loads(args.ablation.read_text())
    rows = report["variants"]

    agg = build_aggregator(offline=True)
    selected = select_for_classification(agg, load_cohort())
    kg = KnowledgeGraph.from_civic()
    retriever = build_retriever(agg=agg, kg=kg)

    by_key = {f"{s.variant.gene}|{s.variant.hgvsp}|{s.variant.cancer_type}": s.variant
              for s in selected}

    print(f"[*] {len(rows)} variants · retrieval-only recomputation (no model calls)", flush=True)

    baseline_ok = baseline_drift = 0
    totals: Dict[str, Dict[str, int]] = {}
    violations: List[dict] = []
    missing_variant = 0

    for i, r in enumerate(rows, 1):
        key = f"{r['gene']}|{r['hgvsp']}|{r['cancer_type']}"
        v = by_key.get(key)
        if v is None:
            missing_variant += 1
            continue

        # Self-check: the baseline bundle must reproduce the stored identifiers.
        base_ids = sorted(e.id for e in retriever.retrieve(v).bundle.evidences)
        if base_ids == r["baseline"]["ids"]:
            baseline_ok += 1
        else:
            baseline_drift += 1

        scopes = [("baseline", r["baseline"], set(base_ids))]
        for name, entry in r["arms"].items():
            if not entry.get("applicable"):
                continue
            gene, hgvsp = entry["input"].split(None, 1)
            pv = v.model_copy(update={"gene": gene, "hgvsp": hgvsp})
            ids = {e.id for e in retriever.retrieve(pv).bundle.evidences}
            scopes.append((name, entry, ids))

        for name, entry, ids in scopes:
            cls = entry.get("classification")
            if not cls:
                continue
            t = totals.setdefault(name, {"n_citations": 0, "n_outside_bundle": 0,
                                         "n_classifications": 0})
            t["n_classifications"] += 1
            for cit in cls.get("citations", []):
                t["n_citations"] += 1
                if cit not in ids:
                    t["n_outside_bundle"] += 1
                    violations.append({"gene": r["gene"], "hgvsp": r["hgvsp"],
                                       "arm": name, "citation": cit})

        if i % 10 == 0 or i == len(rows):
            print(f"    {i}/{len(rows)} done", flush=True)

    arms_only = {k: v for k, v in totals.items() if k != "baseline"}
    n_arm_cit = sum(v["n_citations"] for v in arms_only.values())
    n_arm_out = sum(v["n_outside_bundle"] for v in arms_only.values())
    base = totals.get("baseline", {"n_citations": 0, "n_outside_bundle": 0})

    out = {
        "source": str(args.ablation),
        "method": ("retrieval re-run only; labels and citations read from the ablation "
                   "output, evidence identifiers recomputed"),
        "baseline_self_check": {
            "n_reproduced": baseline_ok,
            "n_drifted": baseline_drift,
            "trustworthy": baseline_drift == 0,
        },
        "n_variants_not_found_in_cohort": missing_variant,
        "by_arm": totals,
        "arms_total": {"n_citations": n_arm_cit, "n_outside_bundle": n_arm_out},
        "baseline_total": {"n_citations": base["n_citations"],
                           "n_outside_bundle": base["n_outside_bundle"]},
        "violations": violations,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")

    print(f"\n[+] wrote {args.out}")
    print(f"  baseline self-check: {baseline_ok} reproduced, {baseline_drift} drifted")
    print(f"  {'arm':18s} {'classifs':>9s} {'citations':>10s} {'outside':>8s}")
    for name in sorted(totals):
        t = totals[name]
        print(f"  {name:18s} {t['n_classifications']:9d} {t['n_citations']:10d} "
              f"{t['n_outside_bundle']:8d}")
    print(f"\n  ablation arms: {n_arm_out} of {n_arm_cit} citations outside the retrieved bundle")
    print(f"  baseline:      {base['n_outside_bundle']} of {base['n_citations']}")

    if baseline_drift:
        print("\n[!] baseline identifiers did not reproduce — retrieval state has drifted; "
              "treat the arm numbers as unverified")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
