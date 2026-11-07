#!/usr/bin/env python3
"""Evaluate the VICC point engine (src.classify.vicc_rules) on the Horak 2022 gold set.

Wires INDEPENDENT signals — cancerhotspots, AlphaMissense, CIViC (residue-level) — into
VICCPointClassifier and compares its oncogenicity call to the Horak gold label. The gold
`points`/`sop_codes` columns are never read. Reports 5-class / collapsed 3-class accuracy
against the simplified-rule (0.557) and LLM+retrieval (0.600) baselines.

Usage:  python -m scripts.run_horak_vicc
"""
import argparse
import json
import os
from collections import Counter, defaultdict

import pandas as pd

from src.classify.vicc_rules import (CONFIGS, PRIMARY_CONFIG, VICCPointClassifier,
                                     civic_signal_from_rows, domain_feature_at,
                                     parse_protein_change)
from src.classify.vicc_inputs import V2InputProvider, load_civic_rows, load_dms_lof
from src.eval.stats import bootstrap_ci, boundary_ci

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
AM = os.path.join(ROOT, "data", "knowledge", "alphamissense", "vep_cache.json")


def collapse(c):
    return "ONC" if c in ("Oncogenic", "Likely Oncogenic") else (
        "BEN" if c in ("Benign", "Likely Benign") else "VUS")


def auroc(y, s):
    """AUROC via the Mann-Whitney rank formula (no sklearn). Ties get mid-ranks."""
    order = sorted(range(len(s)), key=lambda i: s[i])
    ranks = [0.0] * len(s)
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and s[order[j]] == s[order[i]]:
            j += 1
        avg = (i + j - 1) / 2.0 + 1
        for k in range(i, j):
            ranks[order[k]] = avg
        i = j
    npos = sum(y)
    nneg = len(y) - npos
    if npos == 0 or nneg == 0:
        return 0.0
    sum_pos = sum(r for r, yi in zip(ranks, y) if yi == 1)
    return (sum_pos - npos * (npos + 1) / 2.0) / (npos * nneg)


def roc_curve(y, s):
    pts = [(0.0, 0.0)]
    npos = sum(y) or 1
    nneg = (len(y) - sum(y)) or 1
    for thr in sorted(set(s), reverse=True):
        tp = sum(1 for yi, si in zip(y, s) if yi == 1 and si >= thr)
        fp = sum(1 for yi, si in zip(y, s) if yi == 0 and si >= thr)
        pts.append((fp / nneg, tp / npos))
    pts.append((1.0, 1.0))
    return pts


def main():
    ap = argparse.ArgumentParser(description="VICC point engine on Horak-70")
    ap.add_argument("--roc-png", default=os.path.join(ROOT, "docs", "manuscript", "figures",
                                                      "diagnostic", "vicc_roc.png"),
                    help="where to write the ROC figure (default: committed figures dir)")
    ap.add_argument("--config", default=PRIMARY_CONFIG, choices=sorted(CONFIGS),
                    help="engine configuration (default: sop_strict, the primary result)")
    ap.add_argument("--out", default=os.path.join(BENCH, "horak_vicc.json"))
    args = ap.parse_args()
    bench = pd.read_csv(os.path.join(BENCH, "horak_benchmark.tsv"), sep="\t")
    civ = pd.read_csv(os.path.join(BENCH, "horak_civic.tsv"), sep="\t")
    am = json.load(open(AM))
    dom_path = os.path.join(ROOT, "data", "knowledge", "domains", "uniprot_domains.json")
    domains = json.load(open(dom_path)) if os.path.exists(dom_path) else {}
    gnomad_path = os.path.join(BENCH, "horak_gnomad.json")
    gnomad = json.load(open(gnomad_path)) if os.path.exists(gnomad_path) else {}
    fdir = os.path.join(ROOT, "data", "knowledge", "functional")
    cfg = CONFIGS[args.config]
    # v2-family configurations read the pre-registered inputs (CIViC release, MaveDB additions,
    # VEP v2 predictors / continental AF); the three published configurations are unchanged.
    dms = load_dms_lof(cfg.dms_inputs)
    dms_neu = json.load(open(os.path.join(fdir, "dms_neutral.json"))) if os.path.exists(os.path.join(fdir, "dms_neutral.json")) else {}

    civ_by_gene = defaultdict(list)
    civ_rows = ([r.to_dict() for _, r in civ.iterrows()] if cfg.civic_inputs == "v1"
                else load_civic_rows("v2"))
    for r in civ_rows:
        civ_by_gene[str(r["molecular_profile"]).split()[0]].append(r)
    v2in = V2InputProvider(cfg)

    def civic_signal(gene, ref, pos, alt):
        # Exact-variant matching (never a neighbouring substitution at the residue) and the
        # SOP mapping: only CIViC FUNCTIONAL evidence can grant OS2/SBS2; predictive,
        # prognostic, diagnostic and predisposing items are ignored (see vicc_rules).
        return civic_signal_from_rows(civ_by_gene.get(gene, []), gene, ref, pos, alt)

    def am_path(row):
        e = am.get(f"{row['b37_chr']}:{row['b37_pos']}:{row['b37_ref']}>{row['b37_alt']}")
        return e.get("am_pathogenicity") if e else None

    clf = VICCPointClassifier(config=args.config)

    def domain_at(gene, pos):
        return domain_feature_at(domains, gene, pos, clf.config.om1_scope)

    gold, pred, rows = [], [], []
    for _, row in bench.iterrows():
        gene, aa, g = row["gene"], row["aa"], row["oncogenicity"]
        pp = parse_protein_change(aa)
        civic = civic_signal(gene, pp[0], pp[1], pp[2]) if pp else None
        in_dom = domain_at(gene, pp[1]) if pp else None
        gkey = f"{row['b37_chr']} {row['b37_pos']} . {row['b37_ref']} {row['b37_alt']} . . ."
        gaf = gnomad.get(gkey)
        vkey = f"{pp[0]}{pp[1]}{pp[2]}" if pp else ""
        flof = bool(pp and dms.get(gene, {}).get(vkey, False))
        fneu = bool(pp and dms_neu.get(gene, {}).get(vkey, False))
        res = clf.score(gene, aa, am_pathogenicity=am_path(row),
                        civic=civic, in_domain=in_dom, gnomad_af=gaf, functional_lof=flof,
                        functional_neutral=fneu,
                        **v2in.kwargs(gene, aa, row["b38_chr"], row["b38_pos"],
                                      row["b38_ref"], row["b38_alt"]))
        gold.append(g)
        pred.append(res.oncogenicity.value)
        rows.append({"variant": f"{gene} {aa}", "gold": g, "vicc": res.oncogenicity.value,
                     "points": res.points, "codes": [c.code for c in res.criteria],
                     "civic_functional_eids": (civic.onco_eids + civic.benign_eids) if civic else [],
                     "civic_ignored": civic.ignored if civic else {}})

    n = len(gold)
    acc5 = round(sum(p == g for p, g in zip(pred, gold)) / n, 3)
    acc3 = round(sum(collapse(p) == collapse(g) for p, g in zip(pred, gold)) / n, 3)
    report = {"config": args.config, "config_description": CONFIGS[args.config].description,
              "n": n, "accuracy_5class": acc5, "accuracy_3class": acc3,
              "baselines": {"simplified_rule_3class": 0.557, "llm_retrieval_3class": 0.600,
                            "oncovi_3class": 0.80},
              "pred_dist_3class": dict(Counter(collapse(p) for p in pred)),
              "gold_dist_3class": dict(Counter(collapse(g) for g in gold)),
              "rows": rows}
    # ROC / AUROC / sensitivity / specificity — binary ONC vs rest, score = VICC points.
    y = [1 if collapse(r["gold"]) == "ONC" else 0 for r in rows]
    sc = [r["points"] for r in rows]
    au = auroc(y, sc)
    tp = sum(1 for yi, si in zip(y, sc) if yi == 1 and si >= 6)
    fn = sum(1 for yi, si in zip(y, sc) if yi == 1 and si < 6)
    tn = sum(1 for yi, si in zip(y, sc) if yi == 0 and si < 6)
    fp = sum(1 for yi, si in zip(y, sc) if yi == 0 and si >= 6)
    sens = round(tp / (tp + fn), 3) if tp + fn else 0.0
    spec = round(tn / (tn + fp), 3) if tn + fp else 0.0
    report.update({"auroc_onc": round(au, 3), "sensitivity_onc": sens,
                   "specificity_onc": spec, "operating_threshold": "points >= 6"})
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        pts = roc_curve(y, sc)
        fig, ax = plt.subplots(figsize=(3.6, 3.4))
        ax.plot([p[0] for p in pts], [p[1] for p in pts], "-o", color="#0072B2", ms=3, lw=1.8)
        ax.plot([0, 1], [0, 1], ls=(0, (3, 3)), color="#9aa0a6", lw=1)
        ax.scatter([1 - spec], [sens], color="#D55E00", zorder=5, s=30,
                   label=f"points≥6 (sens {sens}, spec {spec})")
        ax.set_xlabel("1 − specificity (FPR)")
        ax.set_ylabel("Sensitivity (TPR)")
        ax.set_title(f"VICC rule arm ROC — AUROC {au:.3f}\n(Oncogenic vs rest, Horak n={n})",
                     fontsize=9)
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)
        ax.legend(fontsize=6.5, loc="lower right", frameon=False)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()
        fig.savefig(args.roc_png, dpi=300)
        report["roc_figure"] = os.path.relpath(os.path.abspath(args.roc_png), ROOT)
    except Exception as e:
        print(f"    (ROC figure skipped: {e})")
    # 95% percentile-bootstrap CI on 3-class accuracy (seed 0, 5,000 resamples), the
    # interval the manuscript quotes. Written last to keep the historical key order.
    report["accuracy_3class_ci"] = bootstrap_ci(
        [float(collapse(p) == collapse(g)) for p, g in zip(pred, gold)])
    # Exact-style intervals (Wilson + Clopper-Pearson) for proportions that can sit at 0 or 1,
    # where the percentile bootstrap collapses to a zero-width interval (peer review P1-3).
    report["sensitivity_onc_exact_ci"] = boundary_ci(tp, tp + fn)
    report["specificity_onc_exact_ci"] = boundary_ci(tn, tn + fp)

    json.dump(report, open(args.out, "w"), indent=2)
    print(f"[+] VICC point engine [{args.config}] on Horak (n={n}): acc5={acc5}  acc3={acc3}")
    print(f"    AUROC(ONC)={report['auroc_onc']}  sensitivity={sens}  specificity={spec}")
    print(f"    baselines: simplified-rule 0.557 | LLM+retrieval 0.600 | OncoVI 0.80")
    print(f"    pred {report['pred_dist_3class']}  gold {report['gold_dist_3class']}")


if __name__ == "__main__":
    main()
