#!/usr/bin/env python3
"""Build the poster's vector charts from the committed result JSONs.

Target: the A0 portrait poster for the Chuncheon x KNU x K-BioX Global Bio
Innovation Summit 2026 (2026-11-14). Every number is read from
data/outputs/*.json and data/benchmark/*.json; nothing is hard-coded from the
manuscript prose. The poster's number-to-source table is NUMBERS.md and
tests/test_poster_numbers.py checks the rendered HTML against these same files.

Charts are written as SVG with text converted to paths, so the printed poster
does not depend on the print shop having Pretendard installed. Every figure is
one column wide (251 mm on the A0 sheet) and sized tall enough that its labels
read at 1 to 1.5 m.

Run:  ../../../venv/bin/python make_poster_figures.py   (from this directory)
"""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(ROOT, "data", "outputs")
BENCH = os.path.join(ROOT, "data", "benchmark")
FIGS = os.path.join(HERE, "figures")
os.makedirs(FIGS, exist_ok=True)

MM = 1 / 25.4
COL = 251 * MM          # one poster column, inches

# VeriVar brand (docs/branding/README.md) plus one summit accent
NAVY = "#1B2E5E"
TEAL = "#2EB8A6"
TEAL_DEEP = "#1E9485"
ORANGE = "#D55E00"
PLUM = "#9C4F86"
GREY = "#8FAEBB"
GREY_L = "#DCE4EA"
INK = "#16202E"
MUT = "#5B6470"

plt.rcParams.update({
    "svg.fonttype": "path",          # no font dependency at the print shop
    "svg.hashsalt": "verivar-poster",  # stable element ids, so rebuilds do not churn git
    "figure.dpi": 100, "savefig.bbox": "tight", "savefig.pad_inches": 0.05,
    "font.family": "sans-serif",
    "font.sans-serif": ["Pretendard", "Helvetica Neue", "Arial", "DejaVu Sans"],
    "font.size": 19, "axes.titlesize": 21, "axes.labelsize": 19,
    "axes.titleweight": "bold", "axes.titlelocation": "left",
    "xtick.labelsize": 18, "ytick.labelsize": 18, "legend.fontsize": 17,
    "axes.linewidth": 1.3, "lines.linewidth": 2.6, "grid.linewidth": 1.0,
    "xtick.major.width": 1.3, "ytick.major.width": 1.3,
    "xtick.major.size": 6, "ytick.major.size": 6,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False,
    "patch.linewidth": 1.4, "text.color": INK,
    "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
    "axes.edgecolor": "#55606E",
})


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def ygrid(ax):
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="#E4E9ED", linewidth=1.1)


def xgrid(ax):
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, color="#E4E9ED", linewidth=1.1)


def save(fig, name):
    out = os.path.join(FIGS, name + ".svg")
    fig.savefig(out, format="svg", transparent=True, metadata={"Date": None})
    plt.close(fig)
    print("  ", os.path.relpath(out, HERE))


def box(ax, x, y, w, h, text, fc, ec, fs=17, fw="normal", tc=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.02",
                                facecolor=fc, edgecolor=ec, linewidth=2.0))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, fontweight=fw, color=tc, linespacing=1.35)


def arrow(ax, x1, y1, x2, y2, color="#6B7480", lw=2.2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=18, color=color, lw=lw,
                                 shrinkA=1, shrinkB=1))


# =========================================================================== #
# 1. System schematic, one column wide: two parallel branches, top to bottom
# =========================================================================== #
def fig_design():
    fig, ax = plt.subplots(figsize=(COL, 6.4))
    ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)

    box(ax, 0.17, 0.905, 0.66, 0.080, "Somatic variant · gene · HGVSp · cancer type",
        "#FFFFFF", NAVY, fs=18, fw="bold")
    arrow(ax, 0.33, 0.905, 0.245, 0.855)
    arrow(ax, 0.67, 0.905, 0.755, 0.855)
    ax.text(0.245, 0.872, "LLM branch", fontsize=16, color=MUT, ha="center",
            va="bottom", style="italic")
    ax.text(0.755, 0.872, "rule branch", fontsize=16, color=MUT, ha="center",
            va="bottom", style="italic")
    ax.plot([0.50, 0.50], [0.02, 0.862], color=GREY_L, lw=1.8, ls=(0, (6, 5)))

    # --- LLM branch (left) ---
    box(ax, 0.015, 0.700, 0.465, 0.150,
        "Hybrid retrieval\nstructured KB\ndense BM25 + Chroma\ngene–variant–drug graph",
        "#EDF1F7", NAVY, fs=15)
    arrow(ax, 0.247, 0.700, 0.247, 0.650)
    box(ax, 0.015, 0.520, 0.465, 0.128,
        "Evidence bundle\nevery item carries\na citable identifier",
        "#E6F6F2", TEAL_DEEP, fs=15, fw="bold")
    arrow(ax, 0.247, 0.520, 0.247, 0.470)
    box(ax, 0.015, 0.315, 0.465, 0.152,
        "Faithfulness contract\ncite only retrieved\nidentifiers · abstain (VUS)\nwhen no evidence",
        "#FFF4E2", "#C8841A", fs=15, fw="bold")
    arrow(ax, 0.130, 0.315, 0.130, 0.252)
    arrow(ax, 0.365, 0.315, 0.365, 0.252)
    box(ax, 0.015, 0.120, 0.215, 0.130, "Generative\nLLM assigns\nthe label",
        "#EDF1F7", NAVY, fs=15)
    box(ax, 0.265, 0.120, 0.215, 0.130, "Deterministic\nrule assigns,\nLLM explains",
        "#F7EDF4", PLUM, fs=15)
    arrow(ax, 0.122, 0.120, 0.180, 0.082)
    arrow(ax, 0.372, 0.120, 0.315, 0.082)
    box(ax, 0.015, 0.005, 0.465, 0.075,
        "VICC oncogenicity (5-class)\n+ AMP/ASCO/CAP tier", "#F2F5F8", "#9AA6B4", fs=15, fw="bold")

    # --- rule branch (right) ---
    box(ax, 0.520, 0.700, 0.465, 0.150,
        "Rule-arm sources\ncancerhotspots · gnomAD\nMaveDB · UniProt\nCIViC functional · AlphaMissense",
        "#E6F6F2", TEAL_DEEP, fs=14)
    arrow(ax, 0.752, 0.700, 0.752, 0.650)
    box(ax, 0.520, 0.315, 0.465, 0.333,
        "VeriVar rule arm\n\nSOP-strict\nClinGen/CGC/VICC points\n\nno LLM call\nevery criterion citable",
        "#D9F0EA", TEAL_DEEP, fs=16, fw="bold")
    arrow(ax, 0.752, 0.315, 0.752, 0.252)
    box(ax, 0.520, 0.120, 0.465, 0.130,
        "VICC oncogenicity\n(5-class)\nno tier", "#F2F5F8", TEAL_DEEP, fs=15)
    save(fig, "p1_design")


# =========================================================================== #
# 2. Citation existence: the headline
# =========================================================================== #
def fig_faithfulness():
    tax = load(os.path.join(OUT, "citation_taxonomy.json"))
    arms = tax["headline"]["arms"]
    no = arms["no_retrieval_E_empty_bundle"]
    yes = arms["retrieval_gpt4o_mini_106"]
    nv = no["variant_any_fabricated_or_misattributed"]
    nf = no["variant_any_fabricated_identifier"]
    yv = yes["variant_any_fabricated_or_misattributed"]
    p = tax["paired_contrasts_variant_level"][
        "no_retrieval_E_empty_bundle_vs_retrieval_gpt4o_mini_106"][
        "any_fabricated_or_misattributed"]["mcnemar"]["p_value_exact"]

    fig, ax = plt.subplots(figsize=(COL, 5.0))
    fig.subplots_adjust(left=0.165, right=0.975, top=0.97, bottom=0.115)
    for x, d, col in ((0, nv, ORANGE), (1, yv, NAVY)):
        lo, hi = d["wilson_95"]
        ax.bar(x, d["rate"], color=col, width=0.54, edgecolor="white", linewidth=1.5)
        ax.errorbar(x, d["rate"], yerr=[[d["rate"] - lo], [hi - d["rate"]]],
                    fmt="none", ecolor=INK, capsize=9, lw=2.0)
        ax.text(x, hi + 0.045, f"{d['k']} / {d['n']}", ha="center", va="bottom",
                fontsize=30, fontweight="bold", color=col)
        ax.text(x, hi + 0.016, f"{d['rate']:.3f}   [{lo:.3f}–{hi:.3f}]", ha="center",
                va="bottom", fontsize=15, color=col)
    ax.bar(0, nf["rate"], color=ORANGE, width=0.54, hatch="///",
           edgecolor="white", linewidth=1.5)
    ax.text(0, nf["rate"] / 2, f"fabricated outright\n{nf['k']} / {nf['n']}", ha="center",
            va="center", fontsize=15, color="white", fontweight="bold", linespacing=1.3)
    ax.text(0.5, 0.49, f"paired exact McNemar\np = {p:.1e}", ha="center", va="center",
            fontsize=18, color=MUT, linespacing=1.35)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["no retrieval", "with retrieval"], fontsize=20)
    ax.set_ylim(0, 0.62); ax.set_yticks([0, 0.2, 0.4, 0.6])
    ax.set_ylabel("variants citing a fabricated\nor misattributed identifier", fontsize=17)
    ygrid(ax)
    save(fig, "p2_faithfulness")


# =========================================================================== #
# 3. Accuracy: no arm separates at n = 70
# =========================================================================== #
def fig_accuracy():
    st = load(os.path.join(OUT, "stats_report.json"))["horak_3class_accuracy_ci"]
    hv = load(os.path.join(BENCH, "horak_vicc.json"))
    hh = load(os.path.join(BENCH, "oncovi_headtohead.json"))
    rows = [
        ("Simplified rule", st["rule"], GREY),
        ("LLM, no retrieval", st["llm_norag"], ORANGE),
        ("LLM + retrieval", st["llm_rag"], TEAL_DEEP),
        ("VeriVar rule arm\n(SOP-strict)", hv["accuracy_3class_ci"], NAVY),
    ]
    fig, ax = plt.subplots(figsize=(COL, 4.4))
    fig.subplots_adjust(left=0.335, right=0.975, top=0.93, bottom=0.155)
    ys = np.arange(len(rows))[::-1]
    for y, (lab, d, col) in zip(ys, rows):
        ax.errorbar(d["point"], y, xerr=[[d["point"] - d["lo"]], [d["hi"] - d["point"]]],
                    fmt="o", ms=14, color=col, ecolor=col, capsize=9, lw=2.6,
                    mfc="white", mew=3.0)
        ax.text(d["point"], y + 0.22, f"{d['point']:.3f}", ha="center", va="bottom",
                fontsize=21, fontweight="bold", color=col)
    onc = hh["oncovi"]["accuracy_3class"]
    ax.axvline(onc, color=GREY, ls=(0, (6, 5)), lw=2.2)
    # the reference label sits above the line; at the foot of the axis it collided
    # with the bottom row's point estimate
    ax.text(onc, len(rows) - 0.42, f"OncoVI {onc:.3f}\n(69 shared)", ha="center",
            va="bottom", fontsize=16, color=MUT, linespacing=1.3)
    ax.set_yticks(ys); ax.set_yticklabels([r[0] for r in rows], fontsize=18)
    ax.set_ylim(-0.45, len(rows) + 0.30)
    ax.set_xlim(0.40, 0.90)
    ax.set_xlabel("three-class accuracy, Horak-70 (95% CI)", fontsize=17)
    ax.tick_params(axis="y", length=0)
    xgrid(ax); ax.spines["left"].set_visible(False)
    save(fig, "p3_accuracy")


# =========================================================================== #
# 4. Rule-arm error asymmetry, and where the two LLM modes disagree
# =========================================================================== #
def fig_rule_and_discordance():
    hv = load(os.path.join(BENCH, "horak_vicc.json"))
    disc = load(os.path.join(OUT, "discordance_analysis.json"))
    spec = hv["specificity_onc_exact_ci"]["wilson"]
    sens = hv["sensitivity_onc_exact_ci"]["wilson"]

    fig, (axA, axB) = plt.subplots(2, 1, figsize=(COL, 6.6),
                                   gridspec_kw={"height_ratios": [1.0, 1.15]})
    fig.subplots_adjust(left=0.265, right=0.975, top=0.925, bottom=0.085, hspace=0.52)

    ys = [1, 0]
    for y, d, lab, col in ((1, spec, "specificity\n(oncogenic vs rest)", TEAL_DEEP),
                           (0, sens, "sensitivity", ORANGE)):
        ax_lo, ax_hi = d["lo"], d["hi"]
        axA.barh(y, d["point"], color=col, height=0.52, edgecolor="white", linewidth=1.5)
        axA.errorbar(d["point"], y, xerr=[[d["point"] - ax_lo], [ax_hi - d["point"]]],
                     fmt="none", ecolor=INK, capsize=9, lw=2.0)
        axA.text(0.02, y, f"{d['k']} / {d['n']}", va="center", ha="left", fontsize=17,
                 color="white", fontweight="bold")
        axA.text(ax_hi + 0.03, y, f"{d['point']:.3f}", va="center", ha="left",
                 fontsize=24, fontweight="bold", color=col)
    axA.set_yticks(ys)
    axA.set_yticklabels(["specificity\n(oncogenic vs rest)", "sensitivity"], fontsize=18)
    axA.set_xlim(0, 1.25); axA.set_xticks([0, 0.5, 1.0])
    axA.tick_params(axis="y", length=0)
    xgrid(axA); axA.spines["left"].set_visible(False)
    axA.set_title("Rule arm: no oncogenic over-call,\nat the price of recall", fontsize=19)

    items = sorted(disc["category_counts"].items(), key=lambda kv: kv[1], reverse=True)
    pretty = {"tier_boundary": "tier boundary",
              "oncogenic_confidence": "oncogenicity confidence",
              "rule_overcall_corrected_by_llm": "beyond rules (LLM)",
              "verifier_tier_downgrade": "verifier downgrade",
              "benign_label": "benign label",
              "llm_overcall_vs_rule": "LLM over-call"}
    labs = [pretty.get(k, str(k).replace("_", " ")) for k, _ in items]
    vals = [v for _, v in items]
    ys = np.arange(len(vals))[::-1]
    axB.barh(ys, vals, color=PLUM, height=0.64, edgecolor="white", linewidth=1.2)
    for y, v in zip(ys, vals):
        axB.text(v + 0.3, y, str(v), va="center", fontsize=18, fontweight="bold", color=INK)
    axB.set_yticks(ys); axB.set_yticklabels(labs, fontsize=17)
    axB.set_xlim(0, max(vals) * 1.18)
    axB.tick_params(axis="y", length=0)
    axB.set_xlabel("variant × context units", fontsize=17)
    xgrid(axB); axB.spines["left"].set_visible(False)
    axB.set_title(f"Where the two LLM modes disagree\n({disc['n_discordant']} of {disc['n_total']}; "
                  f"{disc['adjacent']} one step apart)", fontsize=19)
    save(fig, "p4_rule_discordance")


# =========================================================================== #
# 5. Where the contract does not hold: input-notation perturbation
# =========================================================================== #
def fig_robustness():
    rep = load(os.path.join(OUT, "context_ablation.json"))
    s = rep["summary"]
    base_civic = sum(v["baseline"]["n_clinical_evidence"] for v in rep["variants"])
    al = [v["arms"]["alias"] for v in rep["variants"] if v["arms"].get("alias", {}).get("applicable")]
    pert_civic = sum(a["n_clinical_evidence"] for a in al)
    base_am = sum(v["baseline"]["n_evidence"] - v["baseline"]["n_clinical_evidence"]
                  for v in rep["variants"])
    pert_am = sum(a["n_evidence"] - a["n_clinical_evidence"] for a in al)
    arm = s["arms"]["alias"]
    safe = arm.get("safe_downgrades_after_clinical_loss", 0)
    drv = arm.get("driver_calls_after_clinical_loss", 0)

    fig, (axA, axB) = plt.subplots(2, 1, figsize=(COL, 6.0),
                                   gridspec_kw={"height_ratios": [1.45, 1.0]})
    fig.subplots_adjust(left=0.185, right=0.975, top=0.925, bottom=0.095, hspace=0.62)

    w = 0.30
    axA.bar([0 - w / 2, 1 - w / 2], [base_civic, base_am], width=w, color=NAVY,
            edgecolor="white", linewidth=1.3, label="symbol as written")
    axA.bar([0 + w / 2, 1 + w / 2], [pert_civic, pert_am], width=w, color=ORANGE,
            edgecolor="white", linewidth=1.3, label="HGNC alias symbol")
    for x, v in [(0 - w / 2, base_civic), (1 - w / 2, base_am),
                 (0 + w / 2, pert_civic), (1 + w / 2, pert_am)]:
        axA.text(x, v + base_civic * 0.03, str(v), ha="center", fontsize=19,
                 fontweight="bold", color=INK)
    axA.set_xticks([0, 1])
    axA.set_xticklabels(["CIViC\n(text-keyed)", "AlphaMissense\n(coordinate-keyed)"], fontsize=17)
    axA.set_ylim(0, base_civic * 1.22)
    axA.set_ylabel("curated evidence items", fontsize=17)
    axA.legend(fontsize=16, framealpha=0, loc="upper right")
    ygrid(axA)
    axA.set_title("One alias symbol empties\nthe curated evidence", fontsize=19)

    total = safe + drv
    axB.barh([0], [drv], color=ORANGE, height=0.5, hatch="///", edgecolor="white",
             linewidth=1.3, label="still called a driver")
    axB.barh([0], [safe], left=[drv], color=TEAL_DEEP, height=0.5, edgecolor="white",
             linewidth=1.3, label="abstained / non-driver")
    axB.text(drv / 2, 0, str(drv), ha="center", va="center", fontsize=34,
             fontweight="bold", color="white")
    axB.text(drv + safe / 2, 0, str(safe), ha="center", va="center", fontsize=20,
             fontweight="bold", color="white")
    axB.set_xlim(0, total * 1.02); axB.set_ylim(-1.05, 0.65)
    axB.set_yticks([]); axB.set_xticks([])
    axB.legend(fontsize=16, framealpha=0, loc="lower center",
               bbox_to_anchor=(0.5, -0.06), ncol=2, columnspacing=1.4)
    for sp in ("left", "bottom"):
        axB.spines[sp].set_visible(False)
    axB.tick_params(length=0)
    axB.set_title(f"...and {drv} of the {total} variants that lost\neverything were still called drivers",
                  fontsize=19)
    save(fig, "p5_robustness")


if __name__ == "__main__":
    print("writing poster figures to", os.path.relpath(FIGS, HERE))
    fig_design()
    fig_faithfulness()
    fig_accuracy()
    fig_rule_and_discordance()
    fig_robustness()
    print("done")
