#!/usr/bin/env python3
"""Head-to-head: our citable VICC engine (rule arm) vs HemaGuide, on the Horak 70.

This is the THIRD external comparator, alongside OncoVI (run_oncovi_headtohead.py) and
CancerVar (run_cancervar_headtohead.py).

HemaGuide (Zoller et al., Nat Med 2026;32(9):3224-3234, doi:10.1038/s41591-026-04494-4,
PMC13577921) has a "molecular mode" that implements the ClinGen/CGC/VICC point-based SOP
(Horak et al. 2022) with automated knowledge-base queries. It was benchmarked on the same 70
Horak missense variants we use and reported 56/70 concordance in three bins (LB/B, VUS, LO/O),
sensitivity 0.88 and specificity 0.84. Its per-variant calls are published as Supplementary
Table 6 (CC BY 4.0), extracted verbatim by scripts/fetch_hemaguide.py into
data/benchmark/hemaguide/hemaguide_st6.csv.

We join ST6 to our gold (data/benchmark/horak_benchmark.tsv) on gene + protein change,
ASSERT that all 70 variants match and that ST6's reference decision/points agree with our
gold (so both tools are scored against the identical expert labels), then score HemaGuide's
calls and our rule arm (data/benchmark/horak_vicc.json) in the same ONC/VUS/BEN scheme.

Unlike CancerVar, HemaGuide answers the native VICC oncogenicity question, so there is no
cross-axis mapping: LO/O -> ONC, VUS -> VUS, LB/B -> BEN.

Statistics: 3-class accuracy with percentile bootstrap 95% CI (src.eval.stats.bootstrap_ci,
5,000 resamples, seed 0, same as scripts/run_stats.py), oncogenic-vs-rest sensitivity and
specificity (with bootstrap CIs, same helper as the CancerVar head-to-head), typed errors
(over-call / miss), and a paired exact two-sided McNemar test on 3-class correctness.

ANTI-FABRICATION: HemaGuide calls are copied from the published table; nothing is inferred.
At n = 70 an accuracy difference of a few variants is not significant; do not read the point
estimates as a ranking.

Usage:  python -m scripts.run_hemaguide_headtohead
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import Counter
from typing import Dict, List, Optional

from scripts.run_cancervar_headtohead import (
    acc,
    boot_ci,
    classify_error,
    collapse,
    mcnemar_exact,
    sens,
    spec,
)
from src.eval.stats import bootstrap_ci, onc_vs_rest_exact_ci

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
HEMA_CSV = os.path.join(BENCH, "hemaguide", "hemaguide_st6.csv")
GOLD = os.path.join(BENCH, "horak_benchmark.tsv")
OUR_PRED = os.path.join(BENCH, "horak_vicc.json")
OUT = os.path.join(BENCH, "hemaguide_headtohead.json")

# HemaGuide / Horak ST6 three-bin decision -> our 3-class scheme (same axis, no remapping).
DECISION_TO_3 = {"LO/O": "ONC", "VUS": "VUS", "LB/B": "BEN"}

# Figures stated in the HemaGuide paper text (Results, "Molecular mode reproduces ...").
PUBLISHED = {"concordant": 56, "n": 70, "accuracy": 0.800,
             "sensitivity_onc": 0.88, "specificity_onc": 0.84,
             "source": "Zoller et al. Nat Med 2026, Results + Fig. 3b"}

PROVENANCE = {
    "tool": "HemaGuide molecular mode (Zoller et al.)",
    "citation": ("Zoller et al. HemaGuide. Nat Med 2026;32(9):3224-3234. "
                 "doi:10.1038/s41591-026-04494-4. PMC13577921."),
    "source_table": "Supplementary Table 6 (sheet 'Supplementary Table 6' of MOESM4_ESM.xlsx)",
    "source_url": ("https://static-content.springer.com/esm/art%3A10.1038%2Fs41591-026-04494-4/"
                   "MediaObjects/41591_2026_4494_MOESM4_ESM.xlsx"),
    "license": "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)",
    "accessed": "2026-09-24",
    "xlsx_sha256": "9bf1a0bf59fabc1181907ee290cefc9533c6cd13d905149a7300490a6b056afa",
    "xlsx_md5_matches_pmc_suppdata": "0083985b2fcffc217cb202623f87e75b",
    "extracted_by": "scripts/fetch_hemaguide.py",
}


def points_int(s) -> Optional[int]:
    """'10 points' / '10' / '-5.0' -> int; None if unparseable."""
    m = re.search(r"-?\d+(?:\.\d+)?", str(s))
    return int(round(float(m.group(0)))) if m else None


def points_to_5class(p: Optional[int]) -> Optional[str]:
    """Horak 2022 point thresholds -> 5-class label (O >=10, LO 6-9, VUS 0-5, LB -6..-1, B <=-7)."""
    if p is None:
        return None
    if p >= 10:
        return "Oncogenic"
    if p >= 6:
        return "Likely Oncogenic"
    if p >= 0:
        return "VUS"
    if p >= -6:
        return "Likely Benign"
    return "Benign"


def variant_key(gene: str, aa: str) -> str:
    """Canonical join key: 'FLT3 p.D835Y'."""
    aa = aa.strip()
    return f"{gene.strip()} {aa if aa.startswith('p.') else 'p.' + aa}"


def load_hemaguide(path: str = HEMA_CSV) -> List[Dict[str, str]]:
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def load_gold(path: str = GOLD) -> Dict[str, Dict[str, str]]:
    with open(path, newline="") as fh:
        return {variant_key(r["gene"], r["aa"]): r for r in csv.DictReader(fh, delimiter="\t")}


def join_and_check(hema: List[Dict[str, str]], gold: Dict[str, Dict[str, str]],
                   ours: Dict[str, dict]) -> List[dict]:
    """Join ST6 to gold and rule-arm rows; raise if any variant or reference label mismatches."""
    rows, missing, label_mismatch, point_mismatch = [], [], [], []
    for h in hema:
        k = variant_key(h["Gene"], h["AA_change"])
        g, o = gold.get(k), ours.get(k)
        if g is None or o is None:
            missing.append(k)
            continue
        if collapse(g["oncogenicity"]) != DECISION_TO_3[h["Horak_2022_decision"]]:
            label_mismatch.append((k, g["oncogenicity"], h["Horak_2022_decision"]))
        if points_int(g["points"]) != points_int(h["Horak_2022_points"]):
            point_mismatch.append((k, g["points"], h["Horak_2022_points"]))
        rows.append({
            "variant": k,
            "gold": g["oncogenicity"].strip(),
            "gold_points": points_int(g["points"]),
            "gold_codes": g.get("sop_codes", ""),
            "hemaguide_decision": h["Hemaguide_decision"],
            "hemaguide_points": points_int(h["HemaGuide_points"]),
            "hemaguide_codes": h["HemaGuide_codes"],
            "ours": o["vicc"],
            "ours_points": o.get("points"),
            "ours_codes": o.get("codes"),
        })
    if missing or label_mismatch or point_mismatch:
        raise AssertionError(f"join failed: missing={missing} label_mismatch={label_mismatch} "
                             f"point_mismatch={point_mismatch}")
    if len(rows) != len(gold) or len({r["variant"] for r in rows}) != len(rows):
        raise AssertionError(f"expected a 1:1 join over {len(gold)} gold variants, got {len(rows)}")
    return rows


def score(rows: List[dict]) -> dict:
    """Compute the full head-to-head report body from joined rows."""
    g3 = [collapse(r["gold"]) for r in rows]
    u3 = [collapse(r["ours"]) for r in rows]
    h3 = [DECISION_TO_3[r["hemaguide_decision"]] for r in rows]
    g5 = [r["gold"] for r in rows]
    u5 = [r["ours"] for r in rows]
    h5 = [points_to_5class(r["hemaguide_points"]) for r in rows]

    def metrics(pred3: List[str], pred5: List[Optional[str]]) -> dict:
        correct = [p == q for p, q in zip(pred3, g3)]
        err = Counter(classify_error(q, p) for p, q in zip(pred3, g3))
        s, sp = sens(pred3, g3), spec(pred3, g3)
        return {
            "n_correct_3class": sum(correct),
            "accuracy_3class": round(acc(pred3, g3), 3),
            "accuracy_3class_ci": bootstrap_ci([float(c) for c in correct]),
            "accuracy_5class": round(acc(pred5, g5), 3),
            "sensitivity_onc": round(s, 3),
            "sensitivity_onc_ci": boot_ci(pred3, g3, sens),
            "specificity_onc": round(sp, 3),
            "specificity_onc_ci": boot_ci(pred3, g3, spec),
            "onc_exact_ci95": onc_vs_rest_exact_ci(pred3, g3),
            "over_calls": err.get("over_call", 0),
            "misses": err.get("miss", 0),
            "onc_called_benign": sum(1 for p, q in zip(pred3, g3) if q == "ONC" and p == "BEN"),
            "error_breakdown_vs_gold": dict(err),
        }

    p, ours_only, hema_only = mcnemar_exact(g3, u3, h3)
    disagreements = []
    for r, gg, uu, hh in zip(rows, g3, u3, h3):
        if uu == hh:
            continue
        disagreements.append({
            "variant": r["variant"], "gold": r["gold"], "gold3": gg,
            "ours3": uu, "ours": r["ours"], "ours_points": r["ours_points"],
            "ours_codes": r["ours_codes"],
            "hemaguide3": hh, "hemaguide_points": r["hemaguide_points"],
            "hemaguide_codes": r["hemaguide_codes"],
            "ours_correct": uu == gg, "hemaguide_correct": hh == gg,
            "ours_error": classify_error(gg, uu), "hemaguide_error": classify_error(gg, hh),
        })
    return {
        "ours": metrics(u3, u5),
        "hemaguide": metrics(h3, h5),
        "paired_mcnemar_3class": {
            "p_two_sided": round(p, 3), "ours_only_correct": ours_only,
            "hemaguide_only_correct": hema_only,
            "note": "exact, two-sided, paired on 3-class correctness vs the same gold"},
        "pred_dist_3class": {"gold": dict(Counter(g3)), "ours": dict(Counter(u3)),
                             "hemaguide": dict(Counter(h3))},
        "n_disagreements_3class": len(disagreements),
        "disagreements": disagreements,
    }


def main() -> None:
    # --ours/--out (added 2026-09-24): per-configuration runs of the VICC suite write to
    # data/benchmark/vicc_configs/<config>/ without touching the top-level primary files.
    import argparse
    global OUR_PRED, OUT
    _ap = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    _ap.add_argument("--ours", default=OUR_PRED)
    _ap.add_argument("--out", default=OUT)
    _args = _ap.parse_args()
    OUR_PRED = _args.ours
    OUT = _args.out
    hema = load_hemaguide()
    gold = load_gold()
    ours = {r["variant"]: r for r in json.load(open(OUR_PRED))["rows"]}
    rows = join_and_check(hema, gold, ours)
    body = score(rows)
    sha = hashlib.sha256(open(HEMA_CSV, "rb").read()).hexdigest()
    report = {
        "n_shared_variants": len(rows),
        "comparator": "HemaGuide molecular mode (Zoller et al., Nat Med 2026)",
        "provenance": {**PROVENANCE, "csv": os.path.relpath(HEMA_CSV, ROOT), "csv_sha256": sha},
        "ours_source": os.path.relpath(OUR_PRED, ROOT),
        "gold_source": os.path.relpath(GOLD, ROOT),
        "join_check": ("all 70 ST6 rows matched gold on gene + protein change; ST6 reference "
                       "decision and points equal our gold for every variant"),
        "decision_to_3class_map": DECISION_TO_3,
        "hemaguide_published": PUBLISHED,
        "notes": [
            "Rule arm vs rule engine: compare with the OncoVI/CancerVar head-to-heads, not "
            "with the generative arm.",
            "HemaGuide's 5-class accuracy is derived from its published points via the Horak "
            "thresholds (ST6 lists only the 3-bin decision); treat it as secondary.",
            "Accuracy difference is not significant at n = 70 (see paired McNemar); the "
            "defensible contrast is the error shape (over-calls vs misses).",
        ],
        **body,
        "variants_compared": [r["variant"] for r in rows],
    }
    tmp = OUT + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(report, fh, indent=2)
    os.replace(tmp, OUT)

    print(f"[+] HemaGuide head-to-head on {len(rows)} Horak variants (same expert gold)")
    print(f"    {'':12s}{'acc3':>7s}{'CI':>15s}{'sens':>7s}{'spec':>7s}{'over':>6s}{'miss':>6s}")
    for name, m in (("ours", report["ours"]), ("HemaGuide", report["hemaguide"])):
        ci = m["accuracy_3class_ci"]
        ci_txt = f"{ci['lo']}-{ci['hi']}"
        print(f"    {name:12s}{m['accuracy_3class']:>7}{ci_txt:>15s}"
              f"{m['sensitivity_onc']:>7}{m['specificity_onc']:>7}"
              f"{m['over_calls']:>6}{m['misses']:>6}")
    mc = report["paired_mcnemar_3class"]
    print(f"    paired McNemar: p={mc['p_two_sided']} (ours-only {mc['ours_only_correct']}, "
          f"HemaGuide-only {mc['hemaguide_only_correct']})")
    print(f"[+] wrote {OUT}")


if __name__ == "__main__":
    main()
