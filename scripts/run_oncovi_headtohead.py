#!/usr/bin/env python3
"""Head-to-head: our citable VICC engine vs OncoVI, on identical Horak variants.

OncoVI (Carta et al., medRxiv 2024.10.10.24315072; github.com/MGCarta/oncovi) is the
strongest open ClinGen/CGC/VICC engine (reported 80% / sens 88% on a 93-variant guideline
set). To compare apples-to-apples we take OncoVI's OWN published per-variant predictions
(`exampleoutput/SOP_table_union_OncoVI_prediction.xlsx`), match them by gene + protein
change to the Horak gold (our `horak_benchmark.tsv`, with expert VICC labels), and score
BOTH tools against the same gold on the same variants. We also re-score our engine here so
the two predictions are strictly comparable.

This neutralises the "you only beat your own simplified rule" critique and sets an honest
SOTA bar. We report 3-class and 5-class accuracy, oncogenic-detection specificity, a paired
exact McNemar test, and note that BOTH engines are fully auditable (every call carries
citable VICC criterion codes) — the differentiator of our system is the added LLM
faithfulness layer (abstention + citation contract), not the rule arm alone.

Usage:  python -m scripts.run_oncovi_headtohead
"""
import json
import os
import re
import urllib.request
from collections import Counter

import pandas as pd

from src.eval.stats import bootstrap_ci, onc_vs_rest_exact_ci

ONCOVI_URL = ("https://raw.githubusercontent.com/MGCarta/oncovi/main/"
              "exampleoutput/SOP_table_union_OncoVI_prediction.xlsx")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
ONCOVI_PRED = os.path.join(BENCH, "oncovi", "SOP_table_union_OncoVI_prediction.xlsx")
OUR_PRED = os.path.join(BENCH, "horak_vicc.json")   # written by run_horak_vicc
GOLD = os.path.join(BENCH, "horak_benchmark.tsv")

_AA3 = {"Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q",
        "Glu": "E", "Gly": "G", "His": "H", "Ile": "I", "Leu": "L", "Lys": "K",
        "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W",
        "Tyr": "Y", "Val": "V", "Ter": "*"}


def to1(hgvsp):
    if not isinstance(hgvsp, str):
        return None
    m = re.search(r"p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})", hgvsp)
    if not m:
        return None
    r, a = _AA3.get(m.group(1)), _AA3.get(m.group(3))
    return f"{r}{m.group(2)}{a}" if r and a else None


def collapse(c):
    c = (c or "").strip()
    return "ONC" if c in ("Oncogenic", "Likely Oncogenic") else (
        "BEN" if c in ("Benign", "Likely Benign") else "VUS")


def mcnemar_exact(gold, a, b):
    """Two-sided exact McNemar p over paired correctness of predictors a,b vs gold."""
    from math import comb
    b_wins = sum(1 for g, x, y in zip(gold, a, b) if x != g and y == g)
    a_wins = sum(1 for g, x, y in zip(gold, a, b) if x == g and y != g)
    n = a_wins + b_wins
    if n == 0:
        return 1.0, a_wins, b_wins
    k = min(a_wins, b_wins)
    p = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n) * 2
    return min(1.0, p), a_wins, b_wins


def main():
    # --ours/--out (added 2026-09-24): per-configuration runs of the VICC suite write to
    # data/benchmark/vicc_configs/<config>/ without touching the top-level primary files.
    import argparse
    global OUR_PRED
    _ap = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    _ap.add_argument("--ours", default=OUR_PRED)
    _ap.add_argument("--out", default=os.path.join(BENCH, "oncovi_headtohead.json"))
    _args = _ap.parse_args()
    OUR_PRED = _args.ours
    if not os.path.exists(ONCOVI_PRED):
        os.makedirs(os.path.dirname(ONCOVI_PRED), exist_ok=True)
        print(f"[*] downloading OncoVI predictions from {ONCOVI_URL}")
        urllib.request.urlretrieve(ONCOVI_URL, ONCOVI_PRED)
    gold_df = pd.read_csv(GOLD, sep="\t")
    gold_df["aa1"] = gold_df["aa"].str.replace("p.", "", regex=False)
    onco = pd.read_excel(ONCOVI_PRED)
    onco["aa1"] = onco["HGVSp"].map(to1)
    onco_key = {(r["SYMBOL"], r["aa1"]): r for _, r in onco.iterrows() if r["aa1"]}
    ours = {row["variant"].replace("p.", "").replace(" ", "|"): row
            for row in json.load(open(OUR_PRED))["rows"]}

    rows = []
    for _, g in gold_df.iterrows():
        k = (g["gene"], g["aa1"])
        ok = onco_key.get(k)
        ours_row = ours.get(f"{g['gene']}|{g['aa1']}")
        if ok is None or ours_row is None:
            continue
        rows.append({
            "variant": f"{g['gene']} {g['aa']}",
            "gold": str(g["oncogenicity"]).strip(),
            "oncovi": str(ok["Classification"]).strip(),
            "ours": ours_row["vicc"],
            "oncovi_codes": str(ok.get("Criteria", "")),
            "ours_codes": ours_row["codes"],
        })

    n = len(rows)
    g3 = [collapse(r["gold"]) for r in rows]
    o3 = [collapse(r["oncovi"]) for r in rows]
    u3 = [collapse(r["ours"]) for r in rows]
    g5 = [r["gold"] for r in rows]
    o5 = [r["oncovi"] for r in rows]
    u5 = [r["ours"] for r in rows]

    def acc(pred, gold):
        return round(sum(p == q for p, q in zip(pred, gold)) / len(gold), 3)

    def spec(pred3, gold3):
        tn = sum(1 for p, q in zip(pred3, gold3) if q != "ONC" and p != "ONC")
        fp = sum(1 for p, q in zip(pred3, gold3) if q != "ONC" and p == "ONC")
        return round(tn / (tn + fp), 3) if tn + fp else None

    def acc_ci(pred, gold):
        """95% percentile-bootstrap CI (seed 0, 5,000 resamples) on accuracy."""
        return bootstrap_ci([float(p == q) for p, q in zip(pred, gold)])

    def sens(pred3, gold3):
        tp = sum(1 for p, q in zip(pred3, gold3) if q == "ONC" and p == "ONC")
        fn = sum(1 for p, q in zip(pred3, gold3) if q == "ONC" and p != "ONC")
        return round(tp / (tp + fn), 3) if tp + fn else None

    p3, a3w, b3w = mcnemar_exact(g3, u3, o3)
    report = {
        "n_shared_variants": n,
        "note": "Identical Horak variants, both tools scored vs the same expert gold. "
                "OncoVI predictions from its published SOP_table_union output; ours from the "
                "citable VICC engine. Both arms are fully auditable (citable criterion codes).",
        "ours": {"accuracy_3class": acc(u3, g3), "accuracy_5class": acc(u5, g5),
                 "specificity_onc": spec(u3, g3), "sensitivity_onc": sens(u3, g3),
                 "accuracy_3class_ci": acc_ci(u3, g3),
                 "onc_exact_ci95": onc_vs_rest_exact_ci(u3, g3)},
        "oncovi": {"accuracy_3class": acc(o3, g3), "accuracy_5class": acc(o5, g5),
                   "specificity_onc": spec(o3, g3), "sensitivity_onc": sens(o3, g3),
                   "accuracy_3class_ci": acc_ci(o3, g3),
                   "onc_exact_ci95": onc_vs_rest_exact_ci(o3, g3)},
        "oncovi_published_full_93": {"accuracy": 0.80, "sensitivity_onc": 0.88,
                                     "note": "Carta et al. on all 93; here we share 69."},
        "paired_mcnemar_3class": {"p_two_sided": round(p3, 3),
                                  "ours_only_correct": a3w, "oncovi_only_correct": b3w},
        "pred_dist": {"gold": dict(Counter(g3)), "ours": dict(Counter(u3)),
                      "oncovi": dict(Counter(o3))},
        "disagreements": [r for r in rows if collapse(r["ours"]) != collapse(r["oncovi"])],
    }
    json.dump(report, open(_args.out, "w"), indent=1)

    print(f"[+] OncoVI head-to-head on {n} shared Horak variants (vs same expert gold)")
    print(f"    {'':14s}{'acc3':>8s}{'acc5':>8s}{'spec':>8s}{'sens':>8s}")
    for name, m in (("ours", report["ours"]), ("OncoVI", report["oncovi"])):
        print(f"    {name:14s}{m['accuracy_3class']:>8}{m['accuracy_5class']:>8}"
              f"{m['specificity_onc']:>8}{m['sensitivity_onc']:>8}")
    print(f"    paired McNemar (3-class): p={p3:.3f}  "
          f"(ours-only-correct {a3w}, OncoVI-only-correct {b3w})")
    print(f"    OncoVI published (all 93): acc 0.80, sens 0.88")
    print(f"    both arms auditable (citable VICC codes); n disagreements={len(report['disagreements'])}")


if __name__ == "__main__":
    main()
