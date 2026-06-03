"""Backfill evidence bundles into an existing cohort_interpretation.json.

Adds the (offline, deterministic) evidence bundle + graph related-variants to
each variant row WITHOUT re-running the LLM, so the dashboard chat can ground on
the same evidence the classification used. Idempotent.

Run:  python -m scripts.backfill_bundles
"""
import json
import sys
from pathlib import Path

from src.cohort.loader import load_cohort
from src.knowledge.factory import build_aggregator
from src.classify.select import select_for_classification, dedup_key
from src.retrieval.graph import KnowledgeGraph

OUT = Path("data/outputs/cohort_interpretation.json")


def main():
    if not OUT.exists():
        print(f"[!] {OUT} not found; run the pipeline first.")
        return 1
    output = json.loads(OUT.read_text())

    variants = load_cohort()
    agg = build_aggregator(offline=True)
    selected = select_for_classification(agg, variants)
    kg = KnowledgeGraph.from_civic()

    # Map by (gene, hgvsp, cancer) so we attach the exact bundle per row.
    by_key = {}
    for s in selected:
        bundle = agg.for_variant_obj(s.variant)
        graph = kg.context(s.variant.gene, s.variant.hgvsp)
        by_key[dedup_key(s.variant)] = (bundle, graph)

    n = 0
    for row in output["variants"]:
        key = (row["gene"].upper(), row["hgvsp"].upper(), (row["cancer_type"] or "").lower())
        if key in by_key:
            bundle, graph = by_key[key]
            row["bundle"] = bundle.model_dump(mode="json")
            row["related_variants"] = graph.related_variants[:8]
            n += 1

    OUT.write_text(json.dumps(output, indent=2))
    print(f"[+] backfilled bundles into {n}/{len(output['variants'])} rows -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
