#!/usr/bin/env python3
"""Head-to-head: our citable VICC engine vs CancerVar, on identical Horak variants.

This is the SECOND external comparator (alongside OncoVI, see run_oncovi_headtohead.py),
so the rule arm is benchmarked against more than one published tool on the same gold.

CancerVar (Li et al., Sci. Adv. 2022; github.com/WGLab/CancerVar) is an AI-assisted
AMP/ASCO/CAP somatic interpreter. Crucially it emits an *actionability tier* (Tier_I..IV),
NOT a VICC oncogenicity label. We take CancerVar's OWN per-variant verdicts (fetched live
from its official web server by scripts/fetch_cancervar.py -> data/benchmark/cancervar/),
map tier -> ONC/VUS/BEN, match by gene + protein change to the Horak gold (expert VICC
labels), and score both tools against the same gold on the same variants.

ANTI-FABRICATION: CancerVar tiers come verbatim from the server; nothing is invented here.

Because CancerVar's axis is clinical actionability rather than oncogenicity, its tiers do
not align 1:1 with VICC; we report it as a 3-class (ONC/VUS/BEN) comparison only and flag
this semantic caveat explicitly. We report accuracy, oncogenic-detection specificity &
sensitivity (bootstrap CIs), a paired exact McNemar test, and a typed error breakdown.

Usage:  python -m scripts.run_cancervar_headtohead
"""
import json
import os
import random
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
CANCERVAR_PRED = os.path.join(BENCH, "cancervar", "cancervar_predictions.json")
OUR_PRED = os.path.join(BENCH, "horak_vicc.json")
ONCOVI_H2H = os.path.join(BENCH, "oncovi_headtohead.json")

# CancerVar AMP/ASCO/CAP tier -> 3-class (ONC/VUS/BEN).
# Tier I/II = strong/potential clinical significance -> treated as ONC-equivalent;
# Tier III = uncertain significance -> VUS; Tier IV = benign/likely benign -> BEN.
TIER_TO_3 = {"Tier_I": "ONC", "Tier_II": "ONC", "Tier_III": "VUS", "Tier_IV": "BEN"}


def collapse(c):
    """Collapse a VICC 5-class oncogenicity label to ONC/VUS/BEN."""
    c = (c or "").strip()
    return "ONC" if c in ("Oncogenic", "Likely Oncogenic") else (
        "BEN" if c in ("Benign", "Likely Benign") else "VUS")


def mcnemar_exact(gold, a, b):
    """Two-sided exact McNemar p over paired correctness of predictors a, b vs gold."""
    from math import comb
    b_wins = sum(1 for g, x, y in zip(gold, a, b) if x != g and y == g)
    a_wins = sum(1 for g, x, y in zip(gold, a, b) if x == g and y != g)
    n = a_wins + b_wins
    if n == 0:
        return 1.0, a_wins, b_wins
    k = min(a_wins, b_wins)
    p = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n) * 2
    return min(1.0, p), a_wins, b_wins


def boot_ci(pred, gold, stat, n_boot=2000, seed=7):
    """Percentile bootstrap 95% CI for a paired (pred, gold) statistic fn(pred3, gold3)."""
    rng = random.Random(seed)
    idx = list(range(len(gold)))
    vals = []
    for _ in range(n_boot):
        s = [rng.choice(idx) for _ in idx]
        pv = [pred[i] for i in s]
        gv = [gold[i] for i in s]
        v = stat(pv, gv)
        if v is not None:
            vals.append(v)
    if not vals:
        return [None, None]
    vals.sort()
    lo = vals[int(0.025 * len(vals))]
    hi = vals[int(0.975 * len(vals)) - 1]
    return [round(lo, 3), round(hi, 3)]


def acc(pred, gold):
    return sum(p == q for p, q in zip(pred, gold)) / len(gold) if gold else None


def spec(pred3, gold3):
    tn = sum(1 for p, q in zip(pred3, gold3) if q != "ONC" and p != "ONC")
    fp = sum(1 for p, q in zip(pred3, gold3) if q != "ONC" and p == "ONC")
    return tn / (tn + fp) if tn + fp else None


def sens(pred3, gold3):
    tp = sum(1 for p, q in zip(pred3, gold3) if q == "ONC" and p == "ONC")
    fn = sum(1 for p, q in zip(pred3, gold3) if q == "ONC" and p != "ONC")
    return tp / (tp + fn) if tp + fn else None


def classify_error(gold3, pred3):
    """Type a wrong call relative to the ONC/VUS/BEN gold."""
    if pred3 == gold3:
        return "correct"
    if gold3 != "ONC" and pred3 == "ONC":
        return "over_call"          # called clinically significant when gold is not ONC
    if gold3 == "ONC" and pred3 != "ONC":
        return "miss"               # missed a true oncogenic variant
    if gold3 == "ONC" and pred3 == "VUS":
        return "abstention"         # (covered by miss, kept for clarity)
    return "other"


def main():
    cv = json.load(open(CANCERVAR_PRED))
    if cv.get("n_failed", 0) > 0 or cv["n_parsed"] < cv["n_total"]:
        print(f"[!] WARNING: CancerVar fetch incomplete "
              f"({cv['n_parsed']}/{cv['n_total']} parsed). Scoring parsed rows only.")
    ours = {r["variant"]: r for r in json.load(open(OUR_PRED))["rows"]}

    rows = []
    for r in cv["rows"]:
        if not r["parse_ok"]:
            continue
        o = ours.get(r["variant"])
        if o is None:
            continue
        rows.append({
            "variant": r["variant"],
            "gold": r["gold"],
            "cancervar_tier": r["cancervar_tier"],
            "cancervar_raw_tier": r["cancervar_raw_tier"],
            "cancervar_points": r["cancervar_points"],
            "ours": o["vicc"],
            "ours_points": o.get("points"),
            "ours_codes": o.get("codes"),
        })

    n = len(rows)
    g3 = [collapse(r["gold"]) for r in rows]
    u3 = [collapse(r["ours"]) for r in rows]
    c3 = [TIER_TO_3.get(r["cancervar_tier"], "VUS") for r in rows]

    p3, a3w, c3w = mcnemar_exact(g3, u3, c3)

    # Typed disagreement breakdown (only where the two tools disagree at 3-class).
    disagreements = []
    err_types = {"ours": Counter(), "cancervar": Counter()}
    for r, gg, uu, cc in zip(rows, g3, u3, c3):
        if uu == cc:
            continue
        disagreements.append({
            "variant": r["variant"], "gold3": gg,
            "ours3": uu, "ours": r["ours"],
            "cancervar3": cc, "cancervar_tier": r["cancervar_raw_tier"],
            "ours_correct": uu == gg, "cancervar_correct": cc == gg,
            "ours_error": classify_error(gg, uu),
            "cancervar_error": classify_error(gg, cc),
        })
    # Whole-set error typing (vs gold) for each tool.
    full_err = {"ours": Counter(), "cancervar": Counter()}
    for gg, uu, cc in zip(g3, u3, c3):
        full_err["ours"][classify_error(gg, uu)] += 1
        full_err["cancervar"][classify_error(gg, cc)] += 1

    def metrics(pred3):
        return {
            "accuracy_3class": round(acc(pred3, g3), 3),
            "accuracy_3class_ci": boot_ci(pred3, g3, acc),
            "specificity_onc": (round(spec(pred3, g3), 3)
                                if spec(pred3, g3) is not None else None),
            "specificity_onc_ci": boot_ci(pred3, g3, spec),
            "sensitivity_onc": (round(sens(pred3, g3), 3)
                                if sens(pred3, g3) is not None else None),
            "sensitivity_onc_ci": boot_ci(pred3, g3, sens),
        }

    # 3-way context (rule arm vs OncoVI vs CancerVar) for the manuscript.
    three_way = {"note": "Different shared subsets per tool; not directly poolable."}
    if os.path.exists(ONCOVI_H2H):
        ov = json.load(open(ONCOVI_H2H))
        three_way.update({
            "oncovi_shared_n": ov.get("n_shared_variants"),
            "oncovi": {"accuracy_3class": ov["oncovi"]["accuracy_3class"],
                       "specificity_onc": ov["oncovi"]["specificity_onc"],
                       "sensitivity_onc": ov["oncovi"]["sensitivity_onc"]},
            "ours_on_oncovi_subset": {
                "accuracy_3class": ov["ours"]["accuracy_3class"],
                "specificity_onc": ov["ours"]["specificity_onc"],
                "sensitivity_onc": ov["ours"]["sensitivity_onc"]},
        })

    report = {
        "n_shared_variants": n,
        "comparator": "CancerVar (WGLab, Li et al. Sci. Adv. 2022)",
        "provenance": cv["provenance"],
        "semantic_caveat": (
            "CancerVar emits AMP/ASCO/CAP clinical-actionability tiers (Tier_I..IV), not "
            "VICC oncogenicity. We map Tier_I/II->ONC, Tier_III->VUS, Tier_IV->BEN to score "
            "against the VICC oncogenicity gold. This cross-axis mapping favours neither tool "
            "but means CancerVar is being asked an actionability question, scored on an "
            "oncogenicity gold; interpret accuracy gaps with that in mind. Our engine and "
            "OncoVI both answer the native VICC oncogenicity question."),
        "tier_to_3class_map": TIER_TO_3,
        "ours": metrics(u3),
        "cancervar": metrics(c3),
        "paired_mcnemar_3class": {"p_two_sided": round(p3, 3),
                                  "ours_only_correct": a3w,
                                  "cancervar_only_correct": c3w,
                                  "note": "exact, two-sided, paired on 3-class correctness"},
        "pred_dist_3class": {"gold": dict(Counter(g3)), "ours": dict(Counter(u3)),
                             "cancervar": dict(Counter(c3))},
        "cancervar_tier_dist": dict(Counter(r["cancervar_raw_tier"] for r in rows)),
        "error_breakdown_vs_gold": {"ours": dict(full_err["ours"]),
                                    "cancervar": dict(full_err["cancervar"])},
        "n_disagreements_3class": len(disagreements),
        "disagreements": disagreements,
        "three_way_context": three_way,
        "variants_compared": [r["variant"] for r in rows],
    }
    out_path = os.path.join(BENCH, "cancervar_headtohead.json")
    json.dump(report, open(out_path, "w"), indent=2)

    print(f"[+] CancerVar head-to-head on {n} shared Horak variants (vs same expert gold)")
    print(f"    {'':12s}{'acc3':>8s}{'spec':>8s}{'sens':>8s}")
    for name, m in (("ours", report["ours"]), ("CancerVar", report["cancervar"])):
        print(f"    {name:12s}{m['accuracy_3class']:>8}"
              f"{str(m['specificity_onc']):>8}{str(m['sensitivity_onc']):>8}")
    print(f"    paired McNemar (3-class): p={p3:.3f}  "
          f"(ours-only-correct {a3w}, CancerVar-only-correct {c3w})")
    print(f"    CancerVar tier dist: {report['cancervar_tier_dist']}")
    print(f"    error breakdown: ours={report['error_breakdown_vs_gold']['ours']} | "
          f"cancervar={report['error_breakdown_vs_gold']['cancervar']}")
    print(f"    n disagreements (3-class) = {len(disagreements)}")
    print(f"[+] wrote {out_path}")


if __name__ == "__main__":
    main()
