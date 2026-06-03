#!/usr/bin/env python3
"""Evaluate the VICC point engine (src.classify.vicc_rules) on the Horak 2022 gold set.

Wires INDEPENDENT signals — cancerhotspots, AlphaMissense, CIViC (residue-level) — into
VICCPointClassifier and compares its oncogenicity call to the Horak gold label. The gold
`points`/`sop_codes` columns are never read. Reports 5-class / collapsed 3-class accuracy
against the simplified-rule (0.557) and LLM+retrieval (0.600) baselines.

Usage:  python -m scripts.run_horak_vicc
"""
import json
import os
from collections import Counter, defaultdict

import pandas as pd

from src.classify.vicc_rules import VICCPointClassifier, parse_protein_change

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
AM = os.path.join(ROOT, "data", "knowledge", "alphamissense", "vep_cache.json")
_BEN_SIG = {"unaltered function", "benign", "likely benign", "negative"}
_RANK = {"A": 3, "B": 2, "C": 1, "D": 0}


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
    bench = pd.read_csv(os.path.join(BENCH, "horak_benchmark.tsv"), sep="\t")
    civ = pd.read_csv(os.path.join(BENCH, "horak_civic.tsv"), sep="\t")
    am = json.load(open(AM))
    dom_path = os.path.join(ROOT, "data", "knowledge", "domains", "uniprot_domains.json")
    domains = json.load(open(dom_path)) if os.path.exists(dom_path) else {}
    gnomad_path = os.path.join(BENCH, "horak_gnomad.json")
    gnomad = json.load(open(gnomad_path)) if os.path.exists(gnomad_path) else {}
    fdir = os.path.join(ROOT, "data", "knowledge", "functional")
    dms = json.load(open(os.path.join(fdir, "dms_lof.json"))) if os.path.exists(os.path.join(fdir, "dms_lof.json")) else {}
    dms_neu = json.load(open(os.path.join(fdir, "dms_neutral.json"))) if os.path.exists(os.path.join(fdir, "dms_neutral.json")) else {}

    _REGION_KEYS = ("dna", "bind", "pocket", "kinase", "catalyt", "phosphatase", "set", "tensin")

    def domain_at(gene, pos):
        for s, e, t, desc in domains.get(gene, []):
            if s <= pos <= e:
                if t in ("Domain", "Active site", "Binding site"):
                    return desc or t
                if t == "Region" and any(k in (desc or "").lower() for k in _REGION_KEYS):
                    return desc
        return None

    civ_by_gene = defaultdict(list)
    for _, r in civ.iterrows():
        civ_by_gene[str(r["molecular_profile"]).split()[0]].append(r)

    def civic_signal(gene, ref, pos, alt):
        # Exact-variant matching (residue-CIViC precision): credit CIViC evidence only
        # when it is for THIS exact substitution, not merely the same residue. This
        # removes neighbour-inheritance (e.g. PIK3CA H1047Q wrongly crediting H1047R's
        # evidence, EZH2 A682V crediting A682T) and makes every citation faithful.
        onco = ben = 0
        best = None
        exact = f"{gene} {ref}{pos}{alt}"
        for r in civ_by_gene.get(gene, []):
            mp = str(r["molecular_profile"])
            # equal to the exact variant, or that variant followed by a separator
            # (e.g. a co-occurring profile "GENE V600E AND ...") — but NOT a different
            # substitution at the same residue.
            if not (mp.startswith(exact) and (len(mp) == len(exact)
                                              or not mp[len(exact)].isalnum())):
                continue
            d = str(r["evidence_direction"]).lower()
            s = str(r["significance"]).lower()
            # Count as benign-for-oncogenicity ONLY on an explicit functional-benign
            # significance — NOT a bare "Does Not Support" (which usually refers to a
            # drug response, not the variant's oncogenicity).
            if s in _BEN_SIG:
                ben += 1
            elif d == "supports":
                onco += 1
                lv = str(r["evidence_level"])
                if best is None or _RANK.get(lv, -1) > _RANK.get(best, -1):
                    best = lv
        return onco, ben, best

    def am_path(row):
        e = am.get(f"{row['b37_chr']}:{row['b37_pos']}:{row['b37_ref']}>{row['b37_alt']}")
        return e.get("am_pathogenicity") if e else None

    clf = VICCPointClassifier()
    gold, pred, rows = [], [], []
    for _, row in bench.iterrows():
        gene, aa, g = row["gene"], row["aa"], row["oncogenicity"]
        pp = parse_protein_change(aa)
        onco = ben = 0
        best = None
        if pp:
            onco, ben, best = civic_signal(gene, pp[0], pp[1], pp[2])
        in_dom = domain_at(gene, pp[1]) if pp else None
        gkey = f"{row['b37_chr']} {row['b37_pos']} . {row['b37_ref']} {row['b37_alt']} . . ."
        gaf = gnomad.get(gkey)
        vkey = f"{pp[0]}{pp[1]}{pp[2]}" if pp else ""
        flof = bool(pp and dms.get(gene, {}).get(vkey, False))
        fneu = bool(pp and dms_neu.get(gene, {}).get(vkey, False))
        res = clf.score(gene, aa, am_pathogenicity=am_path(row),
                        civic_onco=onco, civic_benign=ben, civic_best_level=best,
                        in_domain=in_dom, gnomad_af=gaf, functional_lof=flof,
                        functional_neutral=fneu)
        gold.append(g)
        pred.append(res.oncogenicity.value)
        rows.append({"variant": f"{gene} {aa}", "gold": g, "vicc": res.oncogenicity.value,
                     "points": res.points, "codes": [c.code for c in res.criteria]})

    n = len(gold)
    acc5 = round(sum(p == g for p, g in zip(pred, gold)) / n, 3)
    acc3 = round(sum(collapse(p) == collapse(g) for p, g in zip(pred, gold)) / n, 3)
    report = {"n": n, "accuracy_5class": acc5, "accuracy_3class": acc3,
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
        png = os.path.join(ROOT, "docs", "manuscript", "figures", "vicc_roc.png")
        fig.savefig(png, dpi=300)
        report["roc_figure"] = "docs/manuscript/figures/vicc_roc.png"
    except Exception as e:
        print(f"    (ROC figure skipped: {e})")

    json.dump(report, open(os.path.join(BENCH, "horak_vicc.json"), "w"), indent=2)
    print(f"[+] VICC point engine on Horak (n={n}): acc5={acc5}  acc3={acc3}")
    print(f"    AUROC(ONC)={report['auroc_onc']}  sensitivity={sens}  specificity={spec}")
    print(f"    baselines: simplified-rule 0.557 | LLM+retrieval 0.600 | OncoVI 0.80")
    print(f"    pred {report['pred_dist_3class']}  gold {report['gold_dist_3class']}")


if __name__ == "__main__":
    main()
