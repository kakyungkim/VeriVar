"""Is the classifier reproducible at temperature 0 when the input is unchanged?

The input-context ablation's negative control lower-cases the gene symbol, so it
leaves the retrieved bundle bit-identical but not the prompt: the symbol is
rendered into the prompt text (``Variant: {gene} {hgvsp}``). Label changes in
that arm therefore confound two causes, sampling nondeterminism and the model's
sensitivity to symbol case, and cannot establish either on their own.

This script separates them by holding the prompt completely fixed and
classifying each cohort variant several times. Any disagreement across
replicates is nondeterminism, since nothing about the request differs. Read
together with the control arm, it also bounds the case-sensitivity effect: what
the control shows beyond this floor is attributable to the case change.

No response cache and no seed are configured, so replicates are independent
requests.

Usage::

    python -m scripts.run_baseline_repeatability                # 3 replicates
    python -m scripts.run_baseline_repeatability --replicates 5
    python -m scripts.run_baseline_repeatability --limit 10
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

OUT = Path("data/outputs/baseline_repeatability.json")
CHECKPOINT = Path("data/outputs/baseline_repeatability.partial.jsonl")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--replicates", type=int, default=3)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only", action="append", default=None, metavar="GENE:HGVSP",
                    help="restrict to the named variants (repeatable), for following up a "
                         "single boundary case without re-running the cohort")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--checkpoint", type=Path, default=CHECKPOINT)
    ap.add_argument("--restart", action="store_true")
    args = ap.parse_args()

    from dotenv import load_dotenv

    from src.classify.llm import LLMClassifier
    from src.classify.select import select_for_classification
    from src.cohort.loader import load_cohort
    from src.knowledge.factory import build_aggregator
    from src.pipeline import ENV_PATH, build_retriever
    from src.provenance import build_provenance
    from src.retrieval.graph import KnowledgeGraph

    load_dotenv(ENV_PATH, override=True)

    agg = build_aggregator(offline=True)
    selected = select_for_classification(agg, load_cohort())
    if args.only:
        wanted = {o.upper() for o in args.only}
        selected = [s for s in selected
                    if f"{s.variant.gene}:{s.variant.hgvsp}".upper() in wanted]
        if not selected:
            raise SystemExit(f"no cohort variant matches {args.only}")
    if args.limit:
        selected = selected[:args.limit]
    kg = KnowledgeGraph.from_civic()
    retriever = build_retriever(agg=agg, kg=kg)

    llm = LLMClassifier()
    if not llm.available():
        raise SystemExit("OPENAI_API_KEY not set")

    done: Dict[str, dict] = {}
    if args.restart and args.checkpoint.exists():
        args.checkpoint.unlink()
    elif args.checkpoint.exists():
        for line in args.checkpoint.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done[f"{r['gene']}|{r['hgvsp']}|{r['cancer_type']}"] = r
        print(f"[*] resuming: {len(done)} variant(s) cached", flush=True)

    print(f"[*] {len(selected)} variants x {args.replicates} replicates, "
          f"identical prompt, temperature 0", flush=True)

    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    for i, s in enumerate(selected, 1):
        v = s.variant
        key = f"{v.gene}|{v.hgvsp}|{v.cancer_type}"
        if key in done and len(done[key]["replicates"]) >= args.replicates:
            rows.append(done[key])
            print(f"    {i}/{len(selected)} {key} (cached)", flush=True)
            continue
        ret = retriever.retrieve(v)
        reps = []
        for _ in range(args.replicates):
            r = llm.classify(v, ret.bundle, ret.graph, temperature=0.0)
            reps.append({
                "oncogenicity": r.oncogenicity.value,
                "tier": r.tier.value,
                "abstained": bool(r.abstained),
                "citations": sorted(r.citations),
            })
        row = {"gene": v.gene, "hgvsp": v.hgvsp, "cancer_type": v.cancer_type,
               "n_clinical_evidence": sum(1 for e in ret.bundle.evidences
                                          if e.source != "AlphaMissense"),
               "replicates": reps}
        rows.append(row)
        with args.checkpoint.open("a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        print(f"    {i}/{len(selected)} {key}", flush=True)

    def unstable(row: dict, field: str) -> bool:
        return len({json.dumps(r[field], sort_keys=True) for r in row["replicates"]}) > 1

    def pairwise(rows: List[dict], fields: List[str]) -> dict:
        """Disagreement rate over every replicate pair.

        This, not the per-variant instability, is the quantity that governs a
        snapshot check: the golden-set regression compares one stored run
        against one new run, which is a single pair. Reported per field and for
        the union, because a check that compares several fields fails if any
        one of them moves.
        """
        import itertools
        n_pairs = 0
        per_field = {f: 0 for f in fields}
        any_field = 0
        for r in rows:
            for a, b in itertools.combinations(r["replicates"], 2):
                n_pairs += 1
                differs = False
                for f in fields:
                    if json.dumps(a[f], sort_keys=True) != json.dumps(b[f], sort_keys=True):
                        per_field[f] += 1
                        differs = True
                any_field += differs
        rate = lambda k: round(k / n_pairs, 4) if n_pairs else None  # noqa: E731
        return {
            "n_pairs": n_pairs,
            "n_differing_by_field": per_field,
            "rate_by_field": {f: rate(k) for f, k in per_field.items()},
            "n_differing_any_field": any_field,
            "rate_any_field": rate(any_field),
        }

    n = len(rows)
    counts = {f: sum(1 for r in rows if unstable(r, f))
              for f in ("oncogenicity", "tier", "abstained", "citations")}
    any_label = sum(1 for r in rows
                    if unstable(r, "oncogenicity") or unstable(r, "tier")
                    or unstable(r, "abstained"))
    disagreeing = [
        {"gene": r["gene"], "hgvsp": r["hgvsp"],
         "oncogenicity": [x["oncogenicity"] for x in r["replicates"]],
         "tier": [x["tier"] for x in r["replicates"]]}
        for r in rows if unstable(r, "oncogenicity") or unstable(r, "tier")
    ]

    report = {
        "provenance": build_provenance(
            live=True, model_name=llm.model, n_variants=n,
            techniques=["dense-RAG", "single-pass", "temperature=0",
                        f"{args.replicates}-replicate-repeatability"],
            retrieval_index=retriever.index_fingerprint(),
        ).model_dump(mode="json"),
        "design": {
            "n_replicates": args.replicates,
            "prompt": "identical across replicates (no perturbation of any kind)",
            "note": ("isolates sampling nondeterminism from the lower-case-symbol "
                     "control arm, whose prompt text differs by symbol case"),
        },
        "summary": {
            "n_variants": n,
            "n_unstable_any_label": any_label,
            "unstable_by_field": counts,
            "oncogenicity_instability_rate": round(counts["oncogenicity"] / n, 4) if n else None,
            "pairwise": pairwise(rows, ["oncogenicity", "tier", "abstained", "citations"]),
        },
        "disagreeing_variants": disagreeing,
        "variants": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(f"\n[+] wrote {args.out}")
    print(f"  {n} variants x {args.replicates} replicates, identical prompt")
    for f, c in counts.items():
        print(f"    {f:14s} disagreed on {c}/{n}")
    print(f"  any label disagreement: {any_label}/{n}")
    pw = report["summary"]["pairwise"]
    print(f"  pairwise over {pw['n_pairs']} replicate pairs:")
    for f, rt in pw["rate_by_field"].items():
        print(f"    {f:14s} {rt:.3f}")
    print(f"    {'any field':14s} {pw['rate_any_field']:.3f}")
    for d in disagreeing:
        print(f"    {d['gene']} {d['hgvsp']}: onco={Counter(d['oncogenicity']).most_common()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
