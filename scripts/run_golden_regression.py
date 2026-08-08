"""Golden-set regression check — has the system's behaviour moved?

This pipeline sits on a third-party model API whose updates are neither
announced nor versioned in a way the application can see: the same model
identifier can behave differently over time. Substituting or silently receiving
a different model is therefore the one modification this system cannot avoid,
and the burden of detecting the resulting change falls on the application. This
script is the detector.

It pins a small, fixed set of variants and records, for each, the parts of the
output that a change would move: the two classification axes, the abstention
flag, and the exact set of evidence identifiers cited. Free text (the rationale)
is deliberately NOT compared — it varies without the classification having
changed, and comparing it would produce noise instead of a signal.

The check runs the deterministic configuration (temperature 0, single pass, no
self-consistency voting) so that a difference means the model, the prompts, or
the evidence snapshot moved, rather than sampling variation.

Usage::

    python -m scripts.run_golden_regression --build    # (re)create the snapshot; needs OPENAI_API_KEY
    python -m scripts.run_golden_regression            # live check against the snapshot; needs the key
    python -m scripts.run_golden_regression --offline  # config-only check; no API calls, used by pytest

Exit code is 0 when the check passes and 1 when it does not, so it can gate a
release the same way ``scripts/verify_manuscript.py`` gates a publication.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SNAPSHOT = Path("data/golden/golden_set.json")

#: The pinned variants, as (gene, hgvsp, cancer_type). Chosen from the study
#: cohort to span the behaviours that matter rather than to be easy: strongly
#: evidenced hotspots, a context-dependent tier, the discordance-heavy gene, an
#: abstention case with no variant-specific evidence, and two of the
#: "beyond-rules" cases where the rule and the model disagree. Keep this list
#: FIXED — changing it invalidates comparison against older snapshots.
GOLDEN_VARIANTS: List[Tuple[str, str, str]] = [
    # Canonical, strongly evidenced actionable calls.
    ("BRAF", "p.V600E", "Cutaneous Melanoma"),
    ("EGFR", "p.L858R", "Lung Adenocarcinoma (NSCLC)"),
    # Same variant in two tumour types — the context-dependence cases.
    ("BRAF", "p.V600E", "Colorectal Adenocarcinoma"),
    ("KRAS", "p.G12V", "Colorectal Adenocarcinoma"),
    ("KRAS", "p.G12V", "Pancreatic Adenocarcinoma"),
    # Retrieval-sensitive: the dense arm is what recovers the decisive evidence.
    ("PIK3CA", "p.H1047R", "Breast Carcinoma"),
    # The three "beyond-rules" discordances (rule calls a driver, model abstains).
    ("PIK3CA", "p.R88Q", "Colorectal Adenocarcinoma"),
    ("PTEN", "p.R130*", "Cutaneous Melanoma"),
    ("ESR1", "p.E247K", "Colorectal Adenocarcinoma"),
    # Abstention: truncating variant with no variant-specific clinical evidence.
    ("APC", "p.R1450*", "Colorectal Adenocarcinoma"),
    # The discordance-heavy gene, and a computational-prior-only missense.
    ("TP53", "p.R175H", "Breast Carcinoma"),
    ("ALK", "p.G1121D", "Breast Carcinoma"),
]


# --------------------------------------------------------------------------- #
# Fingerprinting
# --------------------------------------------------------------------------- #
def _key(gene: str, hgvsp: str, cancer: Optional[str]) -> str:
    return f"{gene.upper()}|{hgvsp.upper()}|{(cancer or '').lower()}"


def _fingerprint(result) -> dict:
    """The comparable part of a classification (free text excluded)."""
    return {
        "oncogenicity": result.oncogenicity.value,
        "tier": result.tier.value,
        "tier_level": result.tier_level.value if result.tier_level else None,
        "abstained": bool(result.abstained),
        "citations": sorted(result.citations),
    }


# --------------------------------------------------------------------------- #
# Running the pinned set
# --------------------------------------------------------------------------- #
def run_golden(limit: Optional[int] = None, replicates: int = 1) -> dict:
    """Classify the pinned variants under the deterministic configuration.

    Requires a live API key; raises otherwise, because an offline mock run would
    produce a snapshot that certifies nothing about the real model.
    """
    from dotenv import load_dotenv

    from src.classify.llm import LLMClassifier
    from src.classify.rules import RuleClassifier
    from src.classify.select import select_for_classification
    from src.cohort.loader import load_cohort
    from src.knowledge.factory import build_aggregator
    from src.pipeline import ENV_PATH, build_retriever
    from src.provenance import build_provenance
    from src.retrieval.graph import KnowledgeGraph

    load_dotenv(ENV_PATH, override=True)
    llm = LLMClassifier()
    if not llm.available():
        raise RuntimeError(
            "OPENAI_API_KEY is not set. The golden set must be built and checked against the "
            "live model; the offline mock path would certify nothing. Use --offline for the "
            "configuration-only check."
        )

    wanted = {_key(g, p, c) for g, p, c in GOLDEN_VARIANTS}
    agg = build_aggregator(offline=True)
    selected = [s for s in select_for_classification(agg, load_cohort())
                if _key(s.variant.gene, s.variant.hgvsp, s.variant.cancer_type) in wanted]
    if limit:
        selected = selected[:limit]

    missing = wanted - {_key(s.variant.gene, s.variant.hgvsp, s.variant.cancer_type) for s in selected}
    kg = KnowledgeGraph.from_civic()
    retriever = build_retriever(agg=agg, kg=kg)
    rule_clf = RuleClassifier()

    entries: Dict[str, dict] = {}
    for i, s in enumerate(selected, 1):
        v = s.variant
        retrieved = retriever.retrieve(v)
        bundle, graph = retrieved.bundle, retrieved.graph
        # Mode A goes through the model, which does not reproduce itself exactly
        # even at temperature 0, so the check draws it more than once and asks
        # whether the pinned value is still reachable. Mode B is the rule engine,
        # pure code with no model call, so one draw is the whole story there.
        draws = [_fingerprint(llm.classify(v, bundle, graph, temperature=0.0))
                 for _ in range(max(1, replicates))]
        mode_b = rule_clf.classify(v, bundle)
        entry = {
            "gene": v.gene, "hgvsp": v.hgvsp, "cancer_type": v.cancer_type,
            "n_evidence": len(bundle.evidences),
            "mode_a": draws[0],
            "mode_b": _fingerprint(mode_b),
        }
        if len(draws) > 1:
            entry["mode_a_replicates"] = draws
        entries[_key(v.gene, v.hgvsp, v.cancer_type)] = entry
        print(f"    {i}/{len(selected)} {v.gene} {v.hgvsp} ({v.cancer_type})")

    provenance = build_provenance(
        live=True,
        model_name=llm.model,
        data_sources={"civic": "CIViC nightly (committed snapshot)",
                      "cohort": "cBioPortal TCGA PanCancer Atlas (committed snapshot)"},
        n_variants=len(entries),
        techniques=["dense-RAG", "single-pass", "temperature=0"],
    )
    return {
        "provenance": provenance.model_dump(mode="json"),
        "missing_from_cohort": sorted(missing),
        "entries": entries,
    }


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #
LABEL_FIELDS = ("oncogenicity", "tier", "tier_level", "abstained")


def _exact_diffs(key: str, mode: str, was: dict, now: dict) -> List[str]:
    """Strict field-by-field comparison, for the deterministic mode."""
    diffs = []
    for field in LABEL_FIELDS:
        if was.get(field) != now.get(field):
            diffs.append(f"{key} [{mode}] {field}: {was.get(field)!r} -> {now.get(field)!r}")
    lost = sorted(set(was.get("citations", [])) - set(now.get("citations", [])))
    gained = sorted(set(now.get("citations", [])) - set(was.get("citations", [])))
    if lost or gained:
        diffs.append(f"{key} [{mode}] citations: -{lost} +{gained}")
    return diffs


def _reachable_diffs(key: str, was: dict, draws: List[dict]) -> List[str]:
    """Did any draw still produce the pinned value?

    Strict equality against a single draw makes this check fire on sampling
    noise rather than on drift: measured on the cohort, some compared field
    differs between two draws of an identical prompt in about one comparison in
    six, most of it the exact citation set. A difference is therefore only
    reported when the pinned value failed to reappear in *any* of the draws,
    which is the observation that actually indicates the model, the prompts, or
    the evidence moved.
    """
    diffs = []
    for field in LABEL_FIELDS:
        observed = [d.get(field) for d in draws]
        if was.get(field) not in observed:
            seen = sorted({repr(o) for o in observed})
            diffs.append(f"{key} [mode_a] {field}: {was.get(field)!r} not reproduced in "
                         f"{len(draws)} draws (saw {', '.join(seen)})")
    # Citations get a weaker test than the labels, because the exact set is the
    # least stable thing the model produces: it differs between two draws of an
    # identical prompt about ten times in a hundred, and the pinned variants are
    # the heavily-curated ones where the set is largest and moves most. Requiring
    # the exact set back would fail on sampling alone. What does indicate drift
    # is a pinned identifier the model can no longer reach at all, so the test is
    # that every pinned citation appears in at least one draw. Extra identifiers
    # are reported as context on a failure but never cause one.
    pinned = set(was.get("citations", []))
    union = set().union(*(set(d.get("citations", [])) for d in draws)) if draws else set()
    unreachable = sorted(pinned - union)
    if unreachable:
        diffs.append(f"{key} [mode_a] citations: {unreachable} absent from all {len(draws)} draws "
                     f"(also seen, not a failure: {sorted(union - pinned)})")
    return diffs


def compare(snapshot: dict, current: dict) -> List[str]:
    """Return a list of human-readable differences (empty when equivalent)."""
    diffs: List[str] = []
    snap_e, cur_e = snapshot.get("entries", {}), current.get("entries", {})

    for key in sorted(set(snap_e) - set(cur_e)):
        diffs.append(f"{key}: present in snapshot, absent from this run")
    for key in sorted(set(cur_e) - set(snap_e)):
        diffs.append(f"{key}: present in this run, absent from snapshot")

    for key in sorted(set(snap_e) & set(cur_e)):
        # Mode B is deterministic code; anything that moves there is real.
        diffs += _exact_diffs(key, "mode_b",
                              snap_e[key].get("mode_b", {}), cur_e[key].get("mode_b", {}))
        draws = cur_e[key].get("mode_a_replicates")
        if draws:
            diffs += _reachable_diffs(key, snap_e[key].get("mode_a", {}), draws)
        else:
            diffs += _exact_diffs(key, "mode_a",
                                  snap_e[key].get("mode_a", {}), cur_e[key].get("mode_a", {}))
    return diffs


def snapshot_from_run(run: dict) -> dict:
    """Turn a replicated run into a snapshot that pins what is stably produced.

    Pinning one draw pins its accidents too. Measured on the committed snapshot,
    BRAF V600E in colorectal was pinned at 11 cited identifiers while five fresh
    draws produced two or three, so the pinned set was never going to come back
    and the check failed on the snapshot rather than on any change in the system.

    So: labels are pinned at the majority across draws, and citations at the
    identifiers every draw produced. The rest of the observed spread is recorded
    beside the entry as context rather than as something to reproduce.
    """
    entries: Dict[str, dict] = {}
    for key, e in run.get("entries", {}).items():
        draws = e.get("mode_a_replicates") or [e["mode_a"]]
        pinned = {}
        for field in LABEL_FIELDS:
            counts = Counter(d.get(field) for d in draws)
            pinned[field] = counts.most_common(1)[0][0]
        sets = [set(d.get("citations", [])) for d in draws]
        core = sorted(set.intersection(*sets)) if sets else []
        seen = sorted(set().union(*sets)) if sets else []
        pinned["citations"] = core
        entries[key] = {
            **{k: v for k, v in e.items() if k in ("gene", "hgvsp", "cancer_type", "n_evidence")},
            "mode_a": pinned,
            "mode_b": e["mode_b"],
            "observed": {
                "n_draws": len(draws),
                "label_spread": {f: sorted({str(d.get(f)) for d in draws}) for f in LABEL_FIELDS},
                "citations_seen_but_not_pinned": sorted(set(seen) - set(core)),
            },
        }
    return {
        "provenance": run.get("provenance", {}),
        "missing_from_cohort": run.get("missing_from_cohort", []),
        "entries": entries,
    }


def config_drift(snapshot: dict, current_prov: dict) -> List[str]:
    """Differences in the run configuration, which explain a behavioural diff."""
    was = snapshot.get("provenance", {})
    notes: List[str] = []
    for field in ("model_name", "prompt_hash", "guardrail_version"):
        if was.get(field) != current_prov.get(field):
            notes.append(f"{field}: {was.get(field)!r} -> {current_prov.get(field)!r}")
    was_p, now_p = was.get("prompt_hashes", {}), current_prov.get("prompt_hashes", {})
    for name in sorted(set(was_p) | set(now_p)):
        if was_p.get(name) != now_p.get(name):
            notes.append(f"prompt[{name}]: {was_p.get(name)!r} -> {now_p.get(name)!r}")
    return notes


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true", help="(re)create the snapshot from a live run")
    ap.add_argument("--offline", action="store_true",
                    help="compare only the run configuration against the snapshot; no API calls")
    ap.add_argument("--limit", type=int, default=None, help="classify at most N pinned variants")
    ap.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    ap.add_argument("--build-from", type=Path, default=None,
                    help="build the snapshot from a saved replicated run (--save-run output) "
                         "instead of calling the API: labels pinned at the majority across "
                         "draws, citations at the identifiers every draw produced")
    ap.add_argument("--save-run", type=Path, default=None,
                    help="write this run's draws to PATH; a live check costs real calls, so "
                         "keeping it allows the comparison to be re-evaluated without re-running")
    ap.add_argument("--replicates", type=int, default=3,
                    help="Mode A draws per variant when checking; a pinned value counts as "
                         "reproduced if any draw matches it (default 3, 1 restores strict "
                         "single-draw equality). Ignored with --build, which pins one draw.")
    args = ap.parse_args()

    if args.build:
        if args.build_from:
            current = snapshot_from_run(json.loads(args.build_from.read_text()))
        else:
            run = run_golden(limit=args.limit, replicates=args.replicates)
            if args.save_run:
                args.save_run.parent.mkdir(parents=True, exist_ok=True)
                args.save_run.write_text(json.dumps(run, indent=2, sort_keys=True) + "\n")
                print(f"[i] run saved to {args.save_run}")
            current = snapshot_from_run(run) if args.replicates > 1 else run
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        # Read-then-write: keep the previous snapshot beside the new one so a
        # bad build never destroys the only record of prior behaviour.
        if args.snapshot.exists():
            prev = args.snapshot.read_text()
            args.snapshot.with_suffix(".json.bak").write_text(prev)
        args.snapshot.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        n = len(current["entries"])
        print(f"[+] snapshot written: {args.snapshot} ({n}/{len(GOLDEN_VARIANTS)} pinned variants)")
        if current["missing_from_cohort"]:
            print(f"[!] not found in the cohort selection: {current['missing_from_cohort']}")
        return 0

    if not args.snapshot.exists():
        print(f"[FAIL] no snapshot at {args.snapshot}; run with --build first")
        return 1
    snapshot = json.loads(args.snapshot.read_text())

    if args.offline:
        from src.provenance import (
            GUARDRAIL_VERSION, prompt_hash, prompt_hashes,
        )
        current_prov = {
            "model_name": snapshot.get("provenance", {}).get("model_name"),  # not checkable offline
            "prompt_hash": prompt_hash(),
            "prompt_hashes": prompt_hashes(),
            "guardrail_version": GUARDRAIL_VERSION,
        }
        notes = config_drift(snapshot, current_prov)
        if notes:
            print("[FAIL] run configuration has changed since the snapshot:")
            for n in notes:
                print(f"  - {n}")
            print("  Rebuild the snapshot (--build) after confirming the new behaviour is intended.")
            return 1
        print(f"[+] configuration unchanged since the snapshot "
              f"(prompt {current_prov['prompt_hash']}, guardrail {GUARDRAIL_VERSION})")
        return 0

    current = run_golden(limit=args.limit, replicates=args.replicates)
    if args.save_run:
        args.save_run.parent.mkdir(parents=True, exist_ok=True)
        args.save_run.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        print(f"[i] run saved to {args.save_run}")
    notes = config_drift(snapshot, current["provenance"])
    diffs = compare(snapshot, current)
    if notes:
        print("[i] run configuration changed since the snapshot:")
        for n in notes:
            print(f"  - {n}")
    if diffs:
        print(f"[FAIL] {len(diffs)} behavioural difference(s) against the snapshot:")
        for d in diffs:
            print(f"  - {d}")
        return 1
    print(f"[+] golden set unchanged: {len(current['entries'])} variants match the snapshot "
          f"(Mode A reproduced within {args.replicates} draw(s); Mode B exact)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
