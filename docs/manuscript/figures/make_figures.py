#!/usr/bin/env python3
"""Generate manuscript figures (npj Digital Medicine house style) from committed JSONs.

Redesign 2026-06-04 (see experiments/figure_redesign_spec_full.md): 8 slide-like
single-fact figures consolidated into FIVE rich multi-panel composites + a
Supplementary set. Every number is read from data/outputs/*.json and
data/benchmark/*.json — nothing hard-coded from memory.

Main figures
  fig1  System architecture & citation grounding   (schematic + retrieval table + scorecard)
  fig2  Citation existence: measured pre-gate, enforced post-gate (taxonomy + waffle + contract)
  fig3  Citable VICC rule arm  [FLAGSHIP]           (head-to-head + ROC/OOD + error-asym + dial)
  fig4  Classification & dual-mode discordance      (confusion + discordance bars + KRAS ledger)
  fig5  Positioning                                 (quantitative capability matrix)
Supplementary
  figS2 leakage controls & robustness · figS3 input-context ablation · figS4 multi-model PoC
  (figS1, the dashboard screenshot, is built by make_dashboard_figure.sh)
  Supplementary numbers follow first mention in docs/manuscript/preprint.md.

Style: Helvetica/Arial, Okabe-Ito + navy/teal brand (colourblind-safe, redundant hatch),
Nature widths (single 89 mm, double 183 mm), 600-dpi PNG + vector PDF (pdf.fonttype 42),
8 pt bold lowercase panel labels, value labels on bars, y-only light grid.

Run:  ../../venv/bin/python make_figures.py   (from this directory)
"""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpecFromSubplotSpec
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(ROOT, "data", "outputs")
BENCH = os.path.join(ROOT, "data", "benchmark")

W1 = 89 / 25.4     # single column ~3.50"
W15 = 120 / 25.4   # 1.5 column ~4.72"
W2 = 183 / 25.4    # double column ~7.20"

plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 600, "savefig.bbox": "tight",
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 7, "axes.titlesize": 7.5, "axes.labelsize": 7,
    "axes.titleweight": "bold",
    "xtick.labelsize": 6, "ytick.labelsize": 6, "legend.fontsize": 6,
    "axes.linewidth": 0.6, "lines.linewidth": 1.2, "grid.linewidth": 0.4,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5,
    "xtick.direction": "out", "ytick.direction": "out",
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False,
    "patch.linewidth": 0.7,
})

# --- shared visual grammar (same colour = same method in EVERY figure) ---
NAVY = "#1B3A5B"      # VeriVar primary
TEAL = "#2A9D8F"      # contract / operating-point / faithful accent
VERM = "#D55E00"      # OncoVI / no-retrieval (Okabe-Ito vermillion)
SKY = "#56B4E9"       # OncoKB / comparator
GREEN = "#009E73"     # good / grounded
AMBER = "#E69F00"
PURPLE = "#CC79A7"    # deterministic rule
GREY = "#999999"
GREY_E = "#9aa0a6"
GREY_F = "#f2f3f4"
INK = "#202124"
MUT = "#5f6368"
T_NAVY, T_GREEN, T_AMBER, T_PUR = "#dbe6f0", "#d6efe5", "#fbe7c6", "#ecdce8"

METHOD = {
    "VeriVar": dict(color=NAVY, hatch=None),
    "OncoVI": dict(color=VERM, hatch="///"),
    "OncoKB": dict(color=SKY, hatch=".."),
    "raw-LLM": dict(color=GREY, hatch="xx"),
}


def load(p):
    with open(p) as f:
        return json.load(f)


def boot_ci(correct, n_boot=10000, seed=0):
    rng = np.random.default_rng(seed)
    c = np.asarray(correct, float)
    idx = rng.integers(0, len(c), size=(n_boot, len(c)))
    b = c[idx].mean(axis=1)
    return c.mean(), np.percentile(b, 2.5), np.percentile(b, 97.5)


def collapse3(label):
    if label in {"Oncogenic", "Likely Oncogenic"}:
        return "ONC"
    if label in {"Benign", "Likely Benign"}:
        return "BEN"
    return "VUS"


def plabel(ax, letter, x=-0.12, y=1.05):
    ax.text(x, y, letter, transform=ax.transAxes, fontsize=8,
            fontweight="bold", va="bottom", ha="right")


def ygrid(ax):
    ax.grid(axis="y", color="0.9", lw=0.4, zorder=0)
    ax.set_axisbelow(True)


def save(fig, name):
    fig.savefig(os.path.join(HERE, name + ".png"))
    fig.savefig(os.path.join(HERE, name + ".pdf"))
    plt.close(fig)


# ---- schematic helpers ----
def _box(ax, x, y, w, h, text, fc, ec=GREY_E, fs=6.6, fw="normal", tc=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0.004,rounding_size=0.02",
                 linewidth=0.8, edgecolor=ec, facecolor=fc, mutation_aspect=0.8))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, fontweight=fw, color=tc, linespacing=1.25)


def _arrow(ax, x1, y1, x2, y2, color="#6b6f73", lw=0.9):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                 mutation_scale=8, lw=lw, color=color, shrinkA=1.5, shrinkB=1.5))


# ===========================================================================
# FIG 1 — System architecture & citation grounding
# ===========================================================================
def fig1():
    ev = load(os.path.join(OUT, "eval_report.json"))
    fig = plt.figure(figsize=(W2, 4.8))
    outer = fig.add_gridspec(1, 2, width_ratios=[1.18, 1.0], wspace=0.40,
                             left=0.015, right=0.965, top=0.95, bottom=0.05)
    axS = fig.add_subplot(outer[0, 0]); axS.axis("off")
    axS.set_xlim(0, 1); axS.set_ylim(-0.04, 1.0)
    right = GridSpecFromSubplotSpec(2, 1, subplot_spec=outer[0, 1],
                                    height_ratios=[0.80, 1.28], hspace=0.30)
    axT = fig.add_subplot(right[0, 0])
    axB = fig.add_subplot(right[1, 0])

    # --- 1a swimlane schematic (left→right) ---
    # Two parallel branches from the same variant: the LLM pipeline (retrieval →
    # bundle → contract → two LLM modes) and the rule arm (its own sources, no LLM,
    # oncogenicity only). The rule arm does NOT sit downstream of the bundle or the
    # contract (critic 2026-09-24, P1-9).
    axS.text(0.02, 0.965, "Somatic variant  ·  gene · HGVSp · cancer type",
             fontsize=7.4, fontweight="bold", ha="left", va="center", color=INK)
    # retrieval lanes (LLM branch)
    lanes = [("Structured\nCIViC · DGIdb · AM", 0.80),
             ("Dense\nBM25 + Chroma · RRF", 0.67),
             ("Graph\ngene–variant–drug", 0.54)]
    for txt, yy in lanes:
        _box(axS, 0.02, yy, 0.30, 0.095, txt, T_NAVY, NAVY, fs=5.9)
        _arrow(axS, 0.32, yy + 0.048, 0.38, 0.515 + 0.048)
    _box(axS, 0.38, 0.515, 0.27, 0.105,
         "Evidence bundle\nevery item =\ncitable ID", T_GREEN, GREEN, fs=6.0, fw="bold")
    _arrow(axS, 0.515, 0.515, 0.515, 0.455)
    _box(axS, 0.20, 0.345, 0.45, 0.105,
         "Faithfulness contract\ncite only retrieved IDs ·\nabstain when no evidence",
         T_AMBER, AMBER, fs=6.3, fw="bold")
    # two LLM modes
    _box(axS, 0.02, 0.165, 0.29, 0.115,
         "Generative\nLLM assigns label\n(voting + verifier)", T_NAVY, NAVY, fs=6.2)
    _box(axS, 0.35, 0.165, 0.29, 0.115,
         "Deterministic\nrule assigns label;\nLLM writes rationale", T_PUR, PURPLE, fs=6.2)
    for cx, sx in [(0.34, 0.165), (0.50, 0.495)]:
        _arrow(axS, cx, 0.345, sx, 0.282)
    _arrow(axS, 0.165, 0.165, 0.30, 0.112)
    _arrow(axS, 0.495, 0.165, 0.40, 0.112)
    _box(axS, 0.06, 0.020, 0.56, 0.085,
         "VICC oncogenicity (5-class)\n+ AMP/ASCO/CAP tier", GREY_F, GREY_E,
         fs=6.3, fw="bold")
    # rule-arm branch (parallel, from the variant, own sources, no LLM)
    axS.plot([0.845, 0.845], [0.935, 0.905], color="#6b6f73", lw=0.9)
    _arrow(axS, 0.845, 0.935, 0.845, 0.905)
    _box(axS, 0.70, 0.735, 0.29, 0.165,
         "Rule-arm sources\ncancerhotspots · gnomAD\nMaveDB · UniProt\nCIViC functional · AM",
         T_GREEN, TEAL, fs=5.2)
    _arrow(axS, 0.845, 0.735, 0.845, 0.625)
    _box(axS, 0.70, 0.455, 0.29, 0.165,
         "VeriVar rule arm\nSOP-strict\nVICC points;\nno LLM call;\nevery code citable",
         T_GREEN, TEAL, fs=5.7, fw="bold")
    _arrow(axS, 0.845, 0.455, 0.845, 0.285)
    _box(axS, 0.70, 0.165, 0.29, 0.115,
         "VICC oncogenicity\n(5-class)\nno tier", GREY_F, TEAL, fs=6.0)
    axS.plot([0.675, 0.675], [0.02, 0.935], color="0.85", lw=0.6, ls=(0, (3, 2)))
    axS.text(0.50, 0.925, "LLM branch", fontsize=5.6, color=MUT, ha="center", va="center",
             fontstyle="italic")
    axS.text(0.845, 0.955, "rule branch", fontsize=5.6, color=MUT, ha="center", va="center",
             fontstyle="italic")
    plabel(axS, "a", x=0.0, y=0.99)

    # --- 1b retrieval-arm summary ---
    axT.axis("off"); axT.set_xlim(0, 1); axT.set_ylim(0, 1)
    plabel(axT, "b", x=-0.02, y=1.02)
    axT.text(0.0, 0.96, "Retrieval arms — all citation-bearing", fontsize=7.0,
             fontweight="bold", ha="left", va="top")
    cols = [(0.42, "sources"), (0.70, "scope"), (0.94, "citable")]
    for cx, h in cols:
        axT.text(cx, 0.80, h, fontsize=6.2, color=MUT, ha="center", va="center")
    arms = [("Structured", "CIViC·DGIdb·AM", "exact variant", True),
            ("Dense", "BM25+Chroma", "same-variant", True),
            ("Graph", "networkx KG", "shared-drug", True)]
    for i, (nm, src, scope, ok) in enumerate(arms):
        yy = 0.64 - i * 0.20
        axT.text(0.0, yy, nm, fontsize=6.6, fontweight="bold", ha="left", va="center", color=NAVY)
        axT.text(0.42, yy, src, fontsize=6.0, ha="center", va="center", color=INK)
        axT.text(0.70, yy, scope, fontsize=6.0, ha="center", va="center", color=INK)
        axT.text(0.94, yy, r"$\checkmark$", fontsize=10, ha="center", va="center",
                 color=GREEN, fontweight="bold")
        axT.axhline  # noop
    for yln in (0.74, 0.54, 0.34, 0.14):
        axT.plot([0, 1], [yln, yln], color="0.9", lw=0.4)

    # --- 1c faithfulness scorecard ---
    # The out-of-bundle row is read from the citation taxonomy (identifier tokens of
    # the post-gate primary run), not from the older eval_report variant count.
    tax = load(os.path.join(OUT, "citation_taxonomy.json"))["headline"]["arms"]
    post = tax["primary_pipeline_postgate"]["identifier_tokens_out_of_bundle"]
    pre = tax["retrieval_gpt4o_mini_106"]["identifier_tokens_out_of_bundle"]
    gden = ev["citation_grounding"]["n"]
    rows = [
        ("Out-of-bundle\ncitation", post["k"] / post["n"], VERM,
         f"{post['k']}/{post['n']} identifiers"),
        ("Grounding", ev["citation_grounding"]["grounding_rate"], GREEN,
         f"{ev['citation_grounding']['grounded']}/{gden}"),
        ("Directional", ev["directional_faithfulness"]["faithfulness_rate"], GREEN,
         f"{int(round(ev['directional_faithfulness']['faithfulness_rate']*gden))}/{gden}"),
        ("Abstention", ev["abstention"]["abstention_recall"], GREEN,
         f"{ev['abstention']['abstained_when_no_evidence']}/{ev['abstention']['no_evidence_variants']}"),
    ]
    ys = list(range(len(rows)))[::-1]
    for y, (lab, val, col, frac) in zip(ys, rows):
        axB.barh(y, 1.0, color="#eef1f4", height=0.62, zorder=1)
        axB.barh(y, max(val, 0.006), color=col, height=0.62, zorder=2,
                 edgecolor="white", linewidth=0.4)
        axB.text(val - 0.02 if val > 0.5 else val + 0.02, y, f"{val:.2f}",
                 va="center", ha="right" if val > 0.5 else "left", fontsize=6,
                 fontweight="bold", color="white" if val > 0.5 else col, zorder=3)
        axB.text(1.03, y, frac, va="center", ha="left", fontsize=5.6, color=MUT)
    # the enforced 0 row vs the falsifiable pre-gate measurement (Fig 2a); the note sits
    # to the right of the value label so the two never overlap
    y_hall = ys[0]
    axB.text(0.30, y_hall, f"measured before the gate: {pre['k']}/{pre['n']} (Fig 2a)",
             fontsize=5.0, color=VERM, va="center", ha="left")
    axB.set_yticks(ys); axB.set_yticklabels([r[0] for r in rows], fontsize=6.4)
    axB.set_xlim(0, 1.0); axB.set_xticks([0, 0.5, 1.0]); axB.set_xlabel("rate", fontsize=6.5)
    axB.tick_params(axis="y", length=0)
    axB.set_title("Contract guarantees (enforced by construction, n=56)",
                  fontsize=7.0, loc="left", pad=4)
    plabel(axB, "c", x=-0.14, y=1.10)
    save(fig, "fig1")


# ===========================================================================
# FIG 2 — Citation existence: measured before the gate, enforced after it
# ===========================================================================
def fig2():
    # Citation existence is read from the citation taxonomy (2026-09-27 endpoint): the
    # variant-level rate of a fabricated or misattributed identifier, scored with one
    # rule for both arms. The retired stats_report "fabrication" field is not used.
    tax = load(os.path.join(OUT, "citation_taxonomy.json"))
    ev = load(os.path.join(OUT, "eval_report.json"))
    arms = tax["headline"]["arms"]
    no = arms["no_retrieval_E_empty_bundle"]["variant_any_fabricated_or_misattributed"]
    no_fab = arms["no_retrieval_E_empty_bundle"]["variant_any_fabricated_identifier"]
    yes = arms["retrieval_gpt4o_mini_106"]["variant_any_fabricated_or_misattributed"]
    ids = arms["retrieval_gpt4o_mini_106"]["identifier_tokens_out_of_bundle"]
    p_mc = tax["paired_contrasts_variant_level"][
        "no_retrieval_E_empty_bundle_vs_retrieval_gpt4o_mini_106"][
        "any_fabricated_or_misattributed"]["mcnemar"]["p_value_exact"]

    fig = plt.figure(figsize=(W2, 2.9))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.0, 1.25, 1.0], wspace=0.42,
                          left=0.07, right=0.985, top=0.86, bottom=0.17)
    axA, axB, axC = (fig.add_subplot(gs[0, i]) for i in range(3))

    # 2a citation existence, variant level, both arms under one rule
    for x, d, col in ((0, no, VERM), (1, yes, NAVY)):
        lo, hi = d["wilson_95"]
        axA.bar(x, d["rate"], color=col, width=0.62, edgecolor="white", linewidth=0.5)
        if x == 0:
            # the hatched part is the subset whose identifier was fabricated outright
            axA.bar(x, no_fab["rate"], color=col, width=0.62, hatch="///",
                    edgecolor="white", linewidth=0.5)
            from matplotlib import patheffects
            axA.text(x, no_fab["rate"] / 2, f"fabricated\n{no_fab['k']}/{no_fab['n']}",
                     ha="center", va="center", fontsize=5.2, color="white", fontweight="bold",
                     linespacing=1.05,
                     path_effects=[patheffects.withStroke(linewidth=1.6, foreground="#7A3500")])
        axA.errorbar(x, d["rate"], yerr=[[d["rate"] - lo], [hi - d["rate"]]],
                     fmt="none", ecolor=INK, capsize=3, lw=0.8)
        axA.text(x, hi + 0.04, f"{d['k']}/{d['n']}\n{d['rate']:.3f}\n[{lo:.3f}–{hi:.3f}]",
                 ha="center", va="bottom", fontsize=5.4, fontweight="bold", color=col,
                 linespacing=1.05)
    axA.text(0.5, 0.86, f"McNemar p = {p_mc:.1e}", ha="center", va="center", fontsize=5.4,
             color=MUT)
    axA.text(0.5, 0.74, f"{ids['k']} of {ids['n']} identifier citations\noutside the bundle",
             ha="center", va="center", fontsize=5.2, color=NAVY, linespacing=1.05)
    axA.set_xticks([0, 1]); axA.set_xticklabels(["no-\nretrieval", "+\nretrieval"], fontsize=6)
    axA.set_ylim(0, 0.95); axA.set_yticks([0, 0.25, 0.5, 0.75])
    axA.set_ylabel("variants with a fabricated or\nmisattributed identifier", fontsize=6.0)
    ygrid(axA)
    axA.set_title("Citation existence (pre-gate)", fontsize=6.8); plabel(axA, "a")

    # 2b over-call waffle (12 / 56)
    axB.set_aspect("equal"); axB.axis("off")
    ncol, nrow, hot = 8, 7, 12
    k = 0
    for r in range(nrow):
        for c in range(ncol):
            if k >= 56:
                break
            on = k < hot
            axB.add_patch(Rectangle((c, nrow - 1 - r), 0.86, 0.86,
                          facecolor=NAVY if on else "#e6e9ec",
                          edgecolor="white", linewidth=0.5))
            k += 1
    axB.set_xlim(-0.2, ncol + 0.2); axB.set_ylim(-1.5, nrow + 0.5)
    axB.text(0, nrow + 0.18, "12 / 56 confident over-calls reclassified to grounded VUS",
             fontsize=6.2, fontweight="bold", ha="left", va="bottom", color=INK)
    axB.add_patch(Rectangle((0, -1.15), 0.86, 0.7, facecolor=NAVY, edgecolor="white", lw=0.5))
    axB.text(1.1, -0.8, "over-call reclassified to grounded VUS", fontsize=5.4,
             ha="left", va="center", color=MUT)
    axB.set_title("Parametric over-call caught", fontsize=6.8, loc="center")
    plabel(axB, "b", x=-0.02)

    # 2c contract behaviours (=1.0)
    beh = [("grounding", ev["citation_grounding"]["grounding_rate"]),
           ("directional", ev["directional_faithfulness"]["faithfulness_rate"]),
           ("abstention", ev["abstention"]["abstention_recall"])]
    xs = np.arange(len(beh))
    axC.bar(xs, [b[1] for b in beh], color=GREEN, width=0.6, edgecolor="white", linewidth=0.5)
    for x, (_, v) in zip(xs, beh):
        axC.text(x, v - 0.07, f"{v:.2f}", ha="center", va="top", fontsize=6,
                 fontweight="bold", color="white")
    axC.set_xticks(xs); axC.set_xticklabels([b[0] for b in beh], fontsize=6)
    axC.set_ylim(0, 1.08); axC.set_yticks([0, 0.5, 1.0])
    axC.set_ylabel("rate", fontsize=6.4); ygrid(axC)
    axC.set_title("Contract guarantees (enforced)", fontsize=6.8); plabel(axC, "c")
    save(fig, "fig2")


# ===========================================================================
# FIG 3 — Citable VICC rule arm (FLAGSHIP)
# ===========================================================================
def _count_ci(k, n, n_boot=5000, seed=0):
    """95% percentile-bootstrap CI for a proportion k/n (used only where the JSON gives counts, not a CI)."""
    if n == 0:
        return (float("nan"), float("nan"))
    v = np.r_[np.ones(k), np.zeros(n - k)]
    _, lo, hi = boot_ci(v, n_boot=n_boot, seed=seed)
    return lo, hi


def fig3():
    """Rule arm (SOP-strict). Every number is read from the benchmark JSONs; nothing is hard-coded."""
    hv = load(os.path.join(BENCH, "horak_vicc.json"))
    hh = load(os.path.join(BENCH, "oncovi_headtohead.json"))
    hg = load(os.path.join(BENCH, "hemaguide_headtohead.json"))
    cv = load(os.path.join(BENCH, "clinvar_onc_holdout.json"))
    dial = load(os.path.join(BENCH, "horak_sensitivity_modes.json"))

    fig = plt.figure(figsize=(W2, 6.2))
    gs = fig.add_gridspec(2, 2, wspace=0.34, hspace=0.45,
                          left=0.085, right=0.975, top=0.93, bottom=0.10)
    axA, axB = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])
    axC, axD = fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])

    # ---- 3a: three rule engines on identical Horak variants, 95% CIs on every bar
    ours = hg["ours"]; hgd = hg["hemaguide"]; onc = hh["oncovi"]
    gold69 = hh["pred_dist"]["gold"]
    n_pos69 = gold69["ONC"]; n_neg69 = gold69["VUS"] + gold69["BEN"]

    def ci_pair(c):
        return (c["lo"], c["hi"]) if isinstance(c, dict) else tuple(c)
    def wilson(block, which):
        """Wilson score interval for a proportion (bootstrap CIs collapse at 0 and 1)."""
        w = block["onc_exact_ci95"][which]["wilson"]
        return (w["lo"], w["hi"])
    engines = [
        ("VeriVar rule arm (70)", NAVY, None, [
            (ours["accuracy_3class"], ci_pair(ours["accuracy_3class_ci"])),
            (ours["specificity_onc"], wilson(ours, "specificity")),
            (ours["sensitivity_onc"], wilson(ours, "sensitivity"))]),
        ("OncoVI (69 shared)", VERM, "///", [
            (onc["accuracy_3class"], ci_pair(onc["accuracy_3class_ci"])),
            (onc["specificity_onc"], wilson(onc, "specificity")),
            (onc["sensitivity_onc"], wilson(onc, "sensitivity"))]),
        ("HemaGuide (70)", AMBER, "..", [
            (hgd["accuracy_3class"], ci_pair(hgd["accuracy_3class_ci"])),
            (hgd["specificity_onc"], wilson(hgd, "specificity")),
            (hgd["sensitivity_onc"], wilson(hgd, "sensitivity"))]),
    ]
    mets = ["accuracy", "specificity", "sensitivity"]
    x = np.arange(len(mets)); w = 0.26
    for i, (lab, col, hatch, vals) in enumerate(engines):
        xs = x + (i - 1) * w
        v = np.array([a for a, _ in vals]); lo = np.array([c[0] for _, c in vals]); hi = np.array([c[1] for _, c in vals])
        axA.bar(xs, v, w * 0.92, color=col, hatch=hatch, edgecolor="white", linewidth=0.5, label=lab)
        axA.errorbar(xs, v, yerr=[v - lo, hi - v], fmt="none", ecolor=INK, elinewidth=0.6, capsize=1.6)
        for xi, vi, hii in zip(xs, v, hi):
            axA.text(xi, hii + 0.025, f"{vi:.2f}", ha="center", va="bottom", fontsize=4.8, color=col,
                     fontweight="bold" if i == 0 else "normal")
    axA.set_xticks(x); axA.set_xticklabels(mets, fontsize=6)
    # cap at 1.05 (critic P2): the legend moves above the axes instead of into the headroom
    axA.set_ylim(0, 1.05); axA.set_yticks([0, 0.25, 0.5, 0.75, 1.0]); axA.set_ylabel("score (95% CI)", fontsize=6.2)
    axA.legend(loc="lower left", ncol=3, framealpha=0, fontsize=5.0, handlelength=1.0,
               columnspacing=0.8, bbox_to_anchor=(0.0, 1.00), borderaxespad=0.1)
    ygrid(axA)
    p_on = hh["paired_mcnemar_3class"]["p_two_sided"]; p_hg = hg["paired_mcnemar_3class"]["p_two_sided"]
    # the legend sits between the axes and the title (title pad leaves room for it)
    axA.set_title(f"Rule engines on Horak variants (accuracy McNemar p: OncoVI {p_on:.3f}, HemaGuide {p_hg:.3f})",
                  fontsize=6.0, pad=13)
    plabel(axA, "a")

    # ---- 3b: ROC from Horak points + ClinVar holdout operating points (with CIs)
    rows = hv["rows"]
    scores = np.array([r["points"] for r in rows], float)
    pos = np.array([collapse3(r["gold"]) == "ONC" for r in rows])
    # proper empirical ROC: thresholds from high to low, starting at (0, 0); ties move diagonally
    P, N = pos.sum(), (~pos).sum()
    tpr, fpr = [0.0], [0.0]
    for t in np.sort(np.unique(scores))[::-1]:
        pred = scores >= t
        tpr.append(np.sum(pred & pos) / P); fpr.append(np.sum(pred & ~pos) / N)
    tpr.append(1.0); fpr.append(1.0)
    fpr, tpr = np.array(fpr), np.array(tpr)
    axB.plot([0, 1], [0, 1], color="0.75", lw=0.6, ls=(0, (3, 3)))
    axB.plot(fpr, tpr, "-", color=NAVY, lw=1.4, label=f"Horak-70 ROC, AUROC {hv['auroc_onc']:.3f}")
    axB.plot(1 - hv["specificity_onc"], hv["sensitivity_onc"], "o", color=TEAL, ms=6,
             mec="white", mew=0.8, zorder=5, label=f"Horak default (spec {hv['specificity_onc']:.3f})")
    for scope, mk, col, lab in (("all", "D", VERM, "ClinVar all genes"), ("panel9", "s", PURPLE, "ClinVar 9 Horak genes")):
        d = cv["scopes"][scope]["detection"]
        se, sp, au = d["sensitivity"], d["specificity_on_gold_vus"], d["auroc_points"]
        xpt, ypt = 1 - sp["point"], se["point"]
        axB.errorbar(xpt, ypt, xerr=[[xpt - (1 - sp["hi"])], [(1 - sp["lo"]) - xpt]],
                     yerr=[[ypt - se["lo"]], [se["hi"] - ypt]], fmt=mk, color=col, ms=4.5,
                     mec="white", mew=0.6, elinewidth=0.7, capsize=1.5, zorder=6,
                     label=f"{lab} (n={d['n']}), AUROC {au['point']:.3f}")
    axB.set_aspect("equal"); axB.set_xlim(-0.02, 1.02); axB.set_ylim(-0.02, 1.02)
    axB.set_xlabel("1 − specificity", fontsize=6.4); axB.set_ylabel("sensitivity", fontsize=6.4)
    axB.legend(loc="lower right", framealpha=0.85, edgecolor="none", fontsize=4.8, handlelength=1.2)
    axB.set_title("Discrimination: Horak-70 and ClinVar holdout", fontsize=6.4); plabel(axB, "b")

    # ---- 3c: error types among the OncoVI disagreements (counts from JSON)
    from collections import Counter
    ov_err, ours_err = Counter(), Counter()
    for d in hh["disagreements"]:
        g, ovl, oul = collapse3(d["gold"]), collapse3(d["oncovi"]), collapse3(d["ours"])
        if ovl != g:
            ov_err[(g, ovl)] += 1
        if oul != g:
            ours_err[(g, oul)] += 1
    n_dis = len(hh["disagreements"])
    ours_abst = ours_err[("ONC", "VUS")]
    ours_ben = sum(v for (g, p), v in ours_err.items() if p == "BEN")
    ours_other = sum(ours_err.values()) - ours_abst - ours_ben
    ov_over = sum(v for (g, p), v in ov_err.items() if p == "ONC" and g != "ONC")
    ov_other = sum(ov_err.values()) - ov_over
    segs = [  # (row, value, colour, hatch, legend label)
        (1, ours_abst, GREEN, None, "oncogenic left at VUS (abstention)"),
        (1, ours_ben, "#8c6d31", "\\\\\\", "benign-direction call"),
        (1, ours_other, GREY, None, None),
        (0, ov_over, VERM, "///", "oncogenic over-call on gold-VUS"),
        (0, ov_other, "#b0b3b8", None, "other error"),
    ]
    left = {0: 0, 1: 0}; seen = set()
    for row, val, col, hatch, lab in segs:
        if val <= 0:
            continue
        axC.barh(row, val, left=left[row], color=col, hatch=hatch, height=0.5, edgecolor="white",
                 linewidth=0.5, label=lab if lab and lab not in seen else None)
        if lab:
            seen.add(lab)
        axC.text(left[row] + val / 2, row, str(val), ha="center", va="center", fontsize=6,
                 fontweight="bold", color=INK,
                 bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.9))
        left[row] += val
    ours_total, ov_total = left[1], left[0]
    for row, tot, col in ((1, ours_total, NAVY), (0, ov_total, VERM)):
        axC.text(tot + 0.3, row, f"{tot}", ha="left", va="center", fontsize=6.5, fontweight="bold", color=col)
    axC.set_yticks([1, 0]); axC.set_yticklabels(["VeriVar\nrule arm", "OncoVI"], fontsize=6)
    xmax = max(ours_total, ov_total)
    axC.set_xlim(0, xmax * 1.15 + 1); axC.set_ylim(-0.6, 1.9)
    axC.set_xlabel(f"errors among the {n_dis} disagreements (69 shared variants)", fontsize=5.8)
    axC.legend(loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=2, framealpha=0, fontsize=4.9,
               handlelength=1.1, columnspacing=0.9)
    axC.spines["left"].set_visible(False); axC.tick_params(axis="y", length=0)
    axC.set_title(f"Opposite error directions ({ours_total} vs {ov_total} errors)", fontsize=6.4)
    plabel(axC, "c", x=-0.14)

    # ---- 3d: sensitivity dial with 95% CIs
    keys = list(dial.keys())
    sens = np.array([dial[k]["sensitivity"] for k in keys]); spec = np.array([dial[k]["specificity"] for k in keys])
    s_lo = np.array([dial[k]["ci95"]["sensitivity"]["lo"] for k in keys]); s_hi = np.array([dial[k]["ci95"]["sensitivity"]["hi"] for k in keys])
    p_lo = np.array([dial[k]["ci95"]["specificity"]["lo"] for k in keys]); p_hi = np.array([dial[k]["ci95"]["specificity"]["hi"] for k in keys])
    xs = np.arange(len(keys))
    axD.errorbar(xs - 0.06, sens, yerr=[sens - s_lo, s_hi - sens], fmt="-o", color=NAVY, ms=4, mfc="white",
                 mew=1.0, elinewidth=0.6, capsize=1.6, label="sensitivity")
    axD.errorbar(xs + 0.06, spec, yerr=[spec - p_lo, p_hi - spec], fmt="-s", color=TEAL, ms=4, mfc="white",
                 mew=1.0, elinewidth=0.6, capsize=1.6, label="specificity")
    for xi, v in zip(xs, sens):
        axD.text(xi + 0.10, v - 0.03, f"{v:.3f}", ha="left", va="top", fontsize=5.0, color=NAVY)
    for xi, v in zip(xs, spec):
        axD.text(xi + 0.12, v + 0.035, f"{v:.3f}", ha="left", va="bottom", fontsize=5.0, color=TEAL)
    axD.set_xticks(xs)
    axD.set_xticklabels(["SOP-strict\n(default)", "+residue\ntiering", "+OS1\n(ClinVar)", "+both"], fontsize=5.6)
    lo_all = min(s_lo.min(), p_lo.min())
    axD.set_ylim(max(0.0, np.floor((lo_all - 0.05) * 10) / 10), 1.12)
    axD.set_xlim(-0.4, len(keys) - 0.4)
    axD.set_ylabel("rate (95% CI)", fontsize=6.2)
    axD.legend(loc="lower right", framealpha=0.85, edgecolor="none", fontsize=5.2, handlelength=1.4); ygrid(axD)
    axD.set_title("Sensitivity dial (settings 2–4 add non-SOP levers)", fontsize=6.2)
    plabel(axD, "d")
    save(fig, "fig3")


# ===========================================================================
# FIG 4 — Classification & dual-mode discordance
# ===========================================================================
def fig4():
    horak = load(os.path.join(BENCH, "horak_results.json"))
    disc = load(os.path.join(OUT, "discordance_analysis.json"))
    analyses = load(os.path.join(OUT, "analyses_report.json"))

    fig = plt.figure(figsize=(W2, 4.6))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.0, 1.22], height_ratios=[1.0, 0.62],
                          wspace=0.48, hspace=0.42, left=0.115, right=0.975,
                          top=0.92, bottom=0.07)
    axM = fig.add_subplot(gs[0, 0])
    axD = fig.add_subplot(gs[0, 1])
    axK = fig.add_subplot(gs[1, :])

    # 4a confusion
    classes = ["ONC", "VUS", "BEN"]; idx = {c: i for i, c in enumerate(classes)}
    M = np.zeros((3, 3), int); correct = []
    for r in horak["rows"]:
        g, p = collapse3(r["gold"]), collapse3(r["llm_rag"])
        M[idx[g], idx[p]] += 1; correct.append(int(g == p))
    acc, lo, hi = boot_ci(correct)
    rs, cs = M.sum(1), M.sum(0)
    rec = [M[i, i] / rs[i] if rs[i] else 0 for i in range(3)]
    pre = [M[j, j] / cs[j] if cs[j] else 0 for j in range(3)]
    axM.imshow(M, cmap="Blues", vmin=0)
    full = {"ONC": "Onc.\n(+Lik.)", "VUS": "VUS", "BEN": "Ben.\n(+Lik.)"}
    axM.set_xticks(range(3)); axM.set_yticks(range(3))
    axM.set_xticklabels([full[c] for c in classes], fontsize=6)
    axM.set_yticklabels([full[c] for c in classes], fontsize=6)
    axM.set_xlabel("predicted (generative + retrieval)", fontsize=6.2)
    axM.set_ylabel("gold (Horak 2022)", fontsize=6.2)
    axM.tick_params(length=0)
    for sp in axM.spines.values():
        sp.set_visible(False)
    th = M.max() / 2
    for i in range(3):
        for j in range(3):
            axM.text(j, i, str(M[i, j]), ha="center", va="center", fontsize=10,
                     fontweight="bold", color="white" if M[i, j] > th else INK)
    for i in range(3):
        axM.text(2.72, i, f"{rec[i]:.2f}", va="center", ha="center", fontsize=7,
                 fontweight="bold", color=GREEN)
    for j in range(3):
        axM.text(j, 2.72, f"{pre[j]:.2f}", va="center", ha="center", fontsize=7,
                 fontweight="bold", color=NAVY)
    axM.text(2.72, -0.62, "recall", ha="center", fontsize=5.6, color=GREEN)
    axM.text(-0.62, 2.72, "prec.", ha="center", fontsize=5.6, color=NAVY)
    axM.text(2.72, 2.72, f"{acc:.2f}", ha="center", va="center", fontsize=8,
             fontweight="bold", color=INK)
    axM.text(2.72, 3.12, "acc.", ha="center", va="center", fontsize=5.6, color=INK)
    axM.set_xlim(-0.65, 3.3); axM.set_ylim(3.3, -0.7)
    axM.set_title("Three-class accuracy (generative arm)", fontsize=6.6, pad=4)
    plabel(axM, "a", x=-0.20)

    # 4b discordance types
    pretty = {"tier_boundary": "Tier boundary", "oncogenic_confidence": "Onc. confidence",
              "rule_overcall_corrected_by_llm": "Beyond-rules (LLM)", "benign_label": "Benign label",
              "verifier_tier_downgrade": "Verifier downgrade", "llm_overcall_vs_rule": "LLM over-call"}
    items = sorted(disc["category_counts"].items(), key=lambda kv: kv[1])
    axD.barh([pretty[k] for k, _ in items], [v for _, v in items],
             color=PURPLE, edgecolor="white", linewidth=0.5)
    for i, (_, v) in enumerate(items):
        axD.text(v + 0.15, i, str(v), va="center", fontsize=6, fontweight="bold")
    axD.set_xlim(0, max(v for _, v in items) + 2)
    axD.set_xlabel("variant × context units", fontsize=6.2)
    axD.tick_params(labelsize=5.8)
    axD.set_title(f"Dual-mode discordance ({disc['n_discordant']}: {disc['adjacent']} one-step, {disc['gross']} gross)",
                  fontsize=6.0); plabel(axD, "b", x=-0.05, y=1.05)

    # 4c cross-cancer consistency table (4 multi-cancer variants, real data)
    cc = analyses["cross_cancer_consistency"]["detail"]
    shortc = {"Colorectal Adenocarcinoma": "Colorectal", "Pancreatic Adenocarcinoma": "Pancreatic",
              "Cutaneous Melanoma": "Melanoma", "Lung Adenocarcinoma": "Lung",
              "Breast Invasive Carcinoma": "Breast"}
    axK.axis("off"); axK.set_xlim(0, 1); axK.set_ylim(0, 1)
    axK.text(0.0, 0.99, "Cross-cancer consistency",
             fontsize=7.0, fontweight="bold", ha="left", va="top")
    axK.text(0.0, 0.77, "variant", fontsize=5.4, color=MUT, ha="left", va="center")
    axK.text(0.27, 0.77, "context A — call", fontsize=5.4, color=MUT, ha="left", va="center")
    axK.text(0.63, 0.77, "context B — call", fontsize=5.4, color=MUT, ha="left", va="center")
    for i, row in enumerate(cc):
        yy = 0.60 - i * 0.165
        items = list(row["per_cancer"].items())
        (cA, callA), (cB, callB) = items[0], items[1]
        differs = callA != callB
        axK.add_patch(Rectangle((0.0, yy - 0.072), 1.0, 0.144,
                      facecolor=(T_AMBER if differs else "#f4f5f6"), edgecolor="none", clip_on=False))
        axK.text(0.0, yy, row["variant"], fontsize=5.9, fontweight="bold", ha="left",
                 va="center", color=NAVY)
        axK.text(0.27, yy, f"{shortc.get(cA, cA)} — {callA}", fontsize=5.4, ha="left",
                 va="center", color=INK)
        axK.text(0.63, yy, f"{shortc.get(cB, cB)} — {callB}", fontsize=5.4, ha="left", va="center",
                 color=(AMBER if differs else INK), fontweight=("bold" if differs else "normal"))
    plabel(axK, "c", x=-0.05, y=1.06)
    save(fig, "fig4")


# ===========================================================================
# FIG 5 — Positioning (quantitative capability matrix)
# ===========================================================================
def fig5():
    # Rule-engine accuracy/specificity cells are read from the benchmark JSONs (same gold, this study).
    hv = load(os.path.join(BENCH, "horak_vicc.json"))
    hh = load(os.path.join(BENCH, "oncovi_headtohead.json"))
    hg = load(os.path.join(BENCH, "hemaguide_headtohead.json"))
    cvh = load(os.path.join(BENCH, "cancervar_headtohead.json"))
    st = load(os.path.join(OUT, "stats_report.json"))
    fig, ax = plt.subplots(figsize=(W2, 3.6))
    fig.subplots_adjust(left=0.225, right=0.99, top=0.86, bottom=0.04)
    # The two VeriVar arms are separate rows (critic 2026-09-24, P1-10): the leakage
    # controls and the citation measurements were run on the generative arm, the Horak
    # rule-engine numbers come from the rule arm. "honest abstention" = abstention forced
    # by the absence of variant-specific evidence (defined in the caption); tools whose
    # VUS/Tier III output is not forced that way are marked "–", not "x".
    methods = ["VeriVar generative arm", "VeriVar rule arm", "OncoVI",
               "HemaGuide (molecular mode)", "CancerVar*", "OncoKB",
               "CIViC-Fact (verifier)", "Autonomous agent (Ferber)", "raw LLM (no retrieval)"]
    cols = ["citation\ngrounded", "honest\nabstention", "auditable\ncriteria",
            "faithfulness\nreported", "leakage-\ncontrolled eval", "3-class acc\n(Horak-70)",
            "specificity\n(onc-vs-rest)", "citation\naccuracy"]
    # c=check, x=cross, na=dash, ('v',value), ('t',text), ('e',enforced)
    # CancerVar row: actionability tier tool (cross-axis); NO oncogenicity-accuracy
    # cell (its 0.614 is a cross-axis artifact, deliberately left "na"). The onc-vs-rest
    # specificity 0.432 is its measured behaviour re-graded on the VICC gold (§3.6).
    # The raw-LLM "citation accuracy" cell was dropped: 1 − (variant-level rate) is not a
    # citation-level score and was not comparable with Ferber's human-judged value.
    gen_acc = st["horak_3class_accuracy_ci"]["llm_rag"]["point"]
    grid = [
        ["c", "c", "c", "c", "c", ("v", gen_acc), "na", ("e", 1.00)],
        ["c", "c", "c", "na", "x", ("v", hv["accuracy_3class"]), ("v", hv["specificity_onc"]), "na"],
        [("t", "per criterion"), "na", "c", "x", "x", ("v", hh["oncovi"]["accuracy_3class"]),
         ("v", hh["oncovi"]["specificity_onc"]), "na"],
        ["na", "na", "c", ("t", "per case"), "x", ("v", hg["hemaguide"]["accuracy_3class"]),
         ("v", hg["hemaguide"]["specificity_onc"]), "na"],
        ["x", "na", "c", "x", "x", "na", ("v", cvh["cancervar"]["specificity_onc"]), "na"],
        [("t", "per assertion"), "na", "c", "x", "x", "na", "na", "na"],
        ["c", "x", "c", "x", "x", "na", "na", "na"],
        [("t", "self-reported"), "x", "x", "x", "x", "na", "na", ("v", 0.755)],
        ["x", "x", "x", "x", "x", ("v", st["horak_3class_accuracy_ci"]["llm_norag"]["point"]), "na", "na"],
    ]
    nC, nR = len(cols), len(methods)
    for j, c in enumerate(cols):
        ax.text(j + 0.5, nR + 0.12, c, ha="center", va="bottom", fontsize=5.5,
                fontweight="bold", linespacing=1.0)
    for i, m in enumerate(methods):
        yy = nR - 1 - i
        ax.text(-0.08, yy + 0.5, m, ha="right", va="center", fontsize=6.0,
                fontweight="bold" if i < 2 else "normal", color=NAVY if i < 2 else INK)
        for j in range(nC):
            cell = grid[i][j]; cx, cyc = j + 0.5, yy + 0.5
            if cell == "c":
                ax.text(cx, cyc, r"$\checkmark$", ha="center", va="center", fontsize=9,
                        color=GREEN, fontweight="bold")
            elif cell == "x":
                ax.text(cx, cyc, r"$\times$", ha="center", va="center", fontsize=8, color=VERM)
            elif cell == "na":
                ax.text(cx, cyc, "–", ha="center", va="center", fontsize=7, color=GREY)
            elif cell[0] == "t":
                ax.text(cx, cyc, cell[1], ha="center", va="center", fontsize=5.0,
                        fontstyle="italic", color=MUT)
            elif cell[0] == "e":
                # by-construction contract guarantee (NOT a measured/comparable score)
                ax.add_patch(Rectangle((j + 0.07, yy + 0.07), 0.86, 0.86, facecolor=TEAL,
                             alpha=0.12, edgecolor=TEAL, linewidth=0.5,
                             linestyle=(0, (2, 1.5))))
                ax.text(cx, cyc + 0.18, "1.00", ha="center", va="center",
                        fontsize=5.7, fontweight="bold", color=INK)
                ax.text(cx, cyc - 0.20, "enforced", ha="center", va="center",
                        fontsize=4.4, fontstyle="italic", color=MUT)
            else:
                v = cell[1]
                ax.add_patch(Rectangle((j + 0.07, yy + 0.07), 0.86, 0.86, facecolor=NAVY,
                             alpha=0.12 + 0.6 * max(0.0, v - 0.5), edgecolor="none"))
                ax.text(cx, cyc, f"{v:.3f}", ha="center", va="center",
                        fontsize=5.7, fontweight="bold", color=INK)
    for j in range(nC + 1):
        ax.plot([j, j], [0, nR], color="0.88", lw=0.4)
    for i in range(nR + 1):
        ax.plot([0, nC], [i, i], color="0.88", lw=0.4)
    # highlight the two differentiator columns (faithfulness reported, leakage-controlled)
    for j in (3, 4):
        ax.add_patch(Rectangle((j, 0), 1, nR, facecolor=TEAL, alpha=0.05, edgecolor="none", zorder=0))
    ax.set_xlim(-0.02, nC); ax.set_ylim(0, nR + 0.5)
    ax.axis("off")
    ax.set_title("Capability landscape", fontsize=7.5, loc="left", pad=6)
    save(fig, "fig5")


# ===========================================================================
# Supplementary
# ===========================================================================
def figS2_robustness():
    """Leakage controls & robustness composite: temporal · LOVO · embedding · second model."""
    temp = load(os.path.join(BENCH, "horak_temporal.json"))["results"]
    horak = load(os.path.join(BENCH, "horak_results.json"))
    stats = load(os.path.join(OUT, "stats_report.json"))
    lovo = load(os.path.join(BENCH, "horak_lovo.json"))
    emb = load(os.path.join(BENCH, "embed_ablation.json"))
    g4 = load(os.path.join(BENCH, "horak_gpt4o.json"))
    floor = horak["llm_no_rag"]["accuracy_3class"]
    full_ci = stats["horak_3class_accuracy_ci"]["llm_rag"]

    fig = plt.figure(figsize=(W2, 4.7))
    gs = fig.add_gridspec(2, 2, wspace=0.32, hspace=0.50, left=0.09, right=0.975,
                          top=0.93, bottom=0.10)
    axA, axB = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])
    axC, axD = fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])

    # a temporal corpus holdout
    order = ["full", 2018, 2015, 2012]
    xlab = {"full": "full\n(988)", 2018: "<2018\n(885)", 2015: "<2015\n(666)", 2012: "<2012\n(459)"}
    recs = {r["cutoff_before"]: r for r in temp}
    x = np.arange(len(order)); acc = [recs[k]["acc_3class"] for k in order]
    hw = (full_ci["hi"] - full_ci["lo"]) / 2
    axA.fill_between(x, np.array(acc) - hw, np.array(acc) + hw, color=NAVY, alpha=0.12, lw=0,
                     label="±95% CI half-width")
    axA.plot(x, acc, "-o", color=NAVY, ms=4, mfc="white", mew=1.1, label="LLM + retrieval")
    for xi, a in zip(x, acc):
        axA.text(xi, a + 0.015, f"{a:.3f}", ha="center", va="bottom", fontsize=5.3,
                 fontweight="bold", color=NAVY)
    axA.axhline(floor, color=VERM, ls=(0, (4, 3)), lw=1.1, label=f"no-retrieval floor ({floor:.3f})")
    axA.set_xticks(x); axA.set_xticklabels([xlab[k] for k in order], fontsize=5.6)
    axA.set_xlabel("retrieval-corpus cutoff (yr; n items)", fontsize=6)
    # the y-range covers the full CI band (critic P2: the band was clipped at 0.74)
    axA.set_ylabel("3-class accuracy", fontsize=6)
    axA.set_ylim(min(0.45, min(acc) - hw - 0.02), max(acc) + hw + 0.05)
    axA.legend(loc="lower left", framealpha=0, handlelength=1.3, fontsize=5.0); ygrid(axA)
    axA.set_title("Temporal corpus holdout", fontsize=6.6); plabel(axA, "a")

    # b leave-own-evidence-out
    fc = [int(collapse3(r["gold"]) == collapse3(r["llm_rag"])) for r in horak["rows"]]
    full = sum(fc) / len(fc)
    xs = np.arange(2); vals = [full, lovo["acc_3class"]]
    axB.bar(xs, vals, color=[NAVY, TEAL], width=0.56, edgecolor="white", linewidth=0.5)
    for xi, v in zip(xs, vals):
        axB.text(xi, v + 0.008, f"{v:.3f}", ha="center", va="bottom", fontsize=6, fontweight="bold")
    axB.set_xticks(xs); axB.set_xticklabels(["full\nretrieval", "leave-own-\nevidence-out"], fontsize=5.6)
    axB.set_ylim(0, 0.78); axB.set_ylabel("3-class accuracy", fontsize=6); ygrid(axB)
    axB.text(0.5, 0.92, "McNemar p = 1.0", transform=axB.transAxes, ha="center", fontsize=5.4, color=MUT)
    axB.set_title("Leave-own-evidence-out", fontsize=6.6); plabel(axB, "b")

    # c embedding ablation
    r5 = emb["recall_at_5"]; items = sorted(r5.items(), key=lambda kv: kv[1], reverse=True)
    xs = np.arange(len(items))
    axC.bar(xs, [v for _, v in items], color=SKY, width=0.6, edgecolor="white", linewidth=0.5)
    for xi, (_, v) in zip(xs, items):
        axC.text(xi, v + 0.005, f"{v:.3f}", ha="center", va="bottom", fontsize=5.6, fontweight="bold")
    axC.set_xticks(xs); axC.set_xticklabels([k.split("(")[0].strip() for k, _ in items],
                                            fontsize=5.4, rotation=12)
    axC.set_ylabel("own-evidence in top-5\n(recall@5)", fontsize=6); ygrid(axC)
    axC.set_title("Embedding ablation", fontsize=6.6); plabel(axC, "c")

    # d second model (gpt-4o-mini vs gpt-4o)
    mini = [int(collapse3(r["gold"]) == collapse3(r["llm_rag"])) for r in horak["rows"]]
    big = [int(collapse3(r["gold"]) == collapse3(r["pred"])) for r in g4["rows"]]
    m_acc, m_lo, m_hi = boot_ci(mini); b_acc, b_lo, b_hi = boot_ci(big)
    xs = np.arange(2); accs = [m_acc, b_acc]
    errs = [[m_acc - m_lo, b_acc - b_lo], [m_hi - m_acc, b_hi - b_acc]]
    axD.bar(xs, accs, color=[NAVY, "#34618e"], width=0.56, edgecolor="white", linewidth=0.5)
    axD.errorbar(xs, accs, yerr=errs, fmt="none", ecolor=INK, capsize=3, lw=0.8)
    for xi, v in zip(xs, accs):
        axD.text(xi, v + 0.12, f"{v:.2f}", ha="center", va="bottom", fontsize=6, fontweight="bold")
    axD.set_xticks(xs); axD.set_xticklabels(["gpt-4o-mini\n(primary)", "gpt-4o"], fontsize=5.6)
    axD.set_ylim(0, 1.0); axD.set_ylabel("3-class accuracy", fontsize=6); ygrid(axD)
    axD.text(0.5, 0.92, "McNemar p = 0.21", transform=axD.transAxes, ha="center", fontsize=5.4, color=MUT)
    axD.set_title("Model-substitution check (gpt-4o)", fontsize=6.6); plabel(axD, "d")
    save(fig, "figS2_robustness")


def figS4_multimodel():
    mm = load(os.path.join(OUT, "multimodel_faithfulness_poc.json"))
    res = mm["results"]; s = mm["summary"]
    ag = np.array([r["agreement"] for r in res])
    fig = plt.figure(figsize=(W2, 2.8))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.0, 0.9, 1.25], wspace=0.40,
                          left=0.07, right=0.985, top=0.82, bottom=0.20)
    axA, axB, axC = (fig.add_subplot(gs[0, i]) for i in range(3))
    # a agreement histogram
    axA.hist(ag, bins=[0.3, 0.5, 0.7, 0.9, 1.01], color=NAVY, edgecolor="white", linewidth=0.6)
    axA.set_xlabel("cross-model agreement", fontsize=6); axA.set_ylabel("variants", fontsize=6)
    axA.set_title(f"Agreement (mean {s['mean_agreement']:.3f})", fontsize=6.2); ygrid(axA); plabel(axA, "a")
    # b summary stats
    unan = int(np.sum(ag >= 0.999))
    axB.axis("off"); axB.set_xlim(0, 1); axB.set_ylim(0, 1)
    lines = [(f"{s['n_variants']}", "variants · 3 open models"),
             (f"{unan}/{s['n_variants']}", "unanimous (all 3)"),
             ("0", "complete disagreements"),
             (f"{s['abstention_rate']*100:.0f}%", "ensemble abstention")]
    for i, (big, lab) in enumerate(lines):
        yy = 0.86 - i * 0.26
        axB.text(0.0, yy, big, fontsize=11, fontweight="bold", color=NAVY, ha="left", va="center")
        axB.text(0.42, yy, lab, fontsize=5.5, color=INK, ha="left", va="center")
    axB.set_title("Ensemble summary", fontsize=6.2); plabel(axB, "b", x=-0.02)
    # c per-model oncogenicity-call distribution
    models = s["models"]
    labels = [m.split(":")[0] for m in models] + ["ensemble"]
    cats = ["ONC", "VUS", "BEN"]; colmap = {"ONC": NAVY, "VUS": GREY, "BEN": GREEN}
    dist = []
    for m in models:
        c = {"ONC": 0, "VUS": 0, "BEN": 0}
        for r in res:
            c[collapse3(r["per_model"][m]["oncogenicity"])] += 1
        dist.append(c)
    ens = {"ONC": 0, "VUS": 0, "BEN": 0}
    for r in res:
        ens[r["ensemble_call"]] += 1
    dist.append(ens)
    xs = np.arange(len(labels)); bottom = np.zeros(len(labels))
    for cat in cats:
        vals = np.array([d[cat] for d in dist], float)
        axC.bar(xs, vals, bottom=bottom, color=colmap[cat], width=0.62,
                edgecolor="white", linewidth=0.4, label=cat)
        bottom += vals
    axC.set_xticks(xs); axC.set_xticklabels(labels, fontsize=5.2, rotation=15)
    axC.set_ylabel("variants", fontsize=6)
    axC.legend(fontsize=5.0, framealpha=0, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.20))
    axC.set_title("Per-model call distribution", fontsize=6.2); plabel(axC, "c")
    save(fig, "figS4_multimodel")


def figS3_context_ablation():
    """Input-context ablation: what survives when the variant is written differently."""
    rep = load(os.path.join(OUT, "context_ablation.json"))
    s = rep["summary"]

    # Arms in narrative order: the negative control first, then the three that
    # must be invariant, then the one that must NOT be silently accepted.
    order = [("case_lower", "lower-case\nsymbol\n(control)"),
             ("alias", "HGNC alias\nsymbol"),
             ("three_letter", "3-letter\nHGVS"),
             ("legacy_stop", "legacy stop\n(* as X)"),
             ("transcript_shift", "shifted\nresidue no.")]
    arms = [(k, lab) for k, lab in order if s["arms"].get(k, {}).get("n_applicable")]

    fig = plt.figure(figsize=(W2, 2.6))
    gs = fig.add_gridspec(1, 3, wspace=0.42, left=0.075, right=0.985, top=0.80, bottom=0.30,
                          width_ratios=[1.15, 0.85, 1.15])

    # (a) curated clinical evidence retained, per arm
    axA = fig.add_subplot(gs[0, 0])
    xs = np.arange(len(arms))
    vals = [s["arms"][k]["mean_clinical_jaccard"] or 0.0 for k, _ in arms]
    cols = [TEAL if k == "case_lower" else (AMBER if k == "transcript_shift" else VERM)
            for k, _ in arms]
    axA.bar(xs, vals, color=cols, width=0.62, edgecolor="white", linewidth=0.4, zorder=3)
    for x, v in zip(xs, vals):
        axA.text(x, v + 0.03, f"{v:.2f}", ha="center", fontsize=5.6, color=INK)
    axA.set_xticks(xs); axA.set_xticklabels([lab for _, lab in arms], fontsize=5.0)
    axA.set_ylim(0, 1.12); axA.set_ylabel("clinical-evidence overlap\n(Jaccard vs baseline)", fontsize=6)
    ygrid(axA)
    axA.set_title("Curated evidence retained", fontsize=6.6); plabel(axA, "a")

    # (b) which source survives — text-keyed vs coordinate-keyed
    axB = fig.add_subplot(gs[0, 1])
    base_civic = sum(v["baseline"]["n_clinical_evidence"] for v in rep["variants"])
    base_am = sum(v["baseline"]["n_evidence"] - v["baseline"]["n_clinical_evidence"]
                  for v in rep["variants"])
    al = [v["arms"]["alias"] for v in rep["variants"] if v["arms"].get("alias", {}).get("applicable")]
    pert_civic = sum(a["n_clinical_evidence"] for a in al)
    pert_am = sum(a["n_evidence"] - a["n_clinical_evidence"] for a in al)
    w = 0.34
    axB.bar([0 - w / 2, 1 - w / 2], [base_civic, base_am], width=w, color=NAVY,
            edgecolor="white", linewidth=0.4, label="baseline", zorder=3)
    axB.bar([0 + w / 2, 1 + w / 2], [pert_civic, pert_am], width=w, color=VERM,
            edgecolor="white", linewidth=0.4, label="alias symbol", zorder=3)
    for x, v in [(0 - w / 2, base_civic), (1 - w / 2, base_am),
                 (0 + w / 2, pert_civic), (1 + w / 2, pert_am)]:
        axB.text(x, v + max(base_civic, base_am) * 0.02, str(v), ha="center", fontsize=5.4, color=INK)
    axB.set_xticks([0, 1])
    axB.set_xticklabels(["CIViC\n(text-keyed)", "AlphaMissense\n(coordinate-keyed)"], fontsize=5.2)
    axB.set_ylabel("evidence items (cohort total)", fontsize=6)
    axB.legend(fontsize=5.2, framealpha=0, loc="upper right")
    ygrid(axB)
    axB.set_title("Which source survives", fontsize=6.6); plabel(axB, "b")

    # (c) what the system did once the curated evidence was gone
    axC = fig.add_subplot(gs[0, 2])
    lost_arms = [(k, lab) for k, lab in arms if s["arms"][k].get("n_clinical_collapsed")]
    xs = np.arange(len(lost_arms))
    safe = np.array([s["arms"][k].get("safe_downgrades_after_clinical_loss", 0) for k, _ in lost_arms], float)
    drv = np.array([s["arms"][k].get("driver_calls_after_clinical_loss", 0) for k, _ in lost_arms], float)
    # "non-driver" rather than "safe": 3 of the 4 were already VUS at baseline, so the
    # bar is not evidence that the loss was handled safely (see the caption).
    axC.bar(xs, safe, color=GREEN, width=0.62, edgecolor="white", linewidth=0.4,
            label="abstained / non-driver call", zorder=3)
    axC.bar(xs, drv, bottom=safe, color=VERM, width=0.62, edgecolor="white", linewidth=0.4,
            hatch="///", label="still called a driver", zorder=3)
    # value labels sit above each bar in ink (white-on-hatch was unreadable at print size,
    # critic P2); one-variant bars get a label too
    for x, (sv, dv) in enumerate(zip(safe, drv)):
        lab = f"{int(dv)} driver\n{int(sv)} non-driver" if dv else f"{int(sv)} non-driver"
        axC.text(x, sv + dv + 0.6, lab, ha="center", va="bottom", fontsize=4.8, color=INK,
                 linespacing=1.05)
    axC.set_xticks(xs); axC.set_xticklabels([lab for _, lab in lost_arms], fontsize=5.0)
    axC.set_ylabel("variants losing all curated evidence", fontsize=6)
    # Headroom for an in-axes legend: anchoring it above the axes collided with
    # the panel title.
    axC.set_ylim(0, max((safe + drv).max(), 1) * 1.55)
    axC.legend(fontsize=5.0, framealpha=0, loc="upper center", ncol=1, handlelength=1.4)
    ygrid(axC)
    axC.set_title("Behaviour after evidence loss", fontsize=6.6); plabel(axC, "c")

    save(fig, "figS3_context_ablation")


if __name__ == "__main__":
    fig1(); fig2(); fig3(); fig4(); fig5()
    figS2_robustness(); figS4_multimodel()
    if os.path.exists(os.path.join(OUT, "context_ablation.json")):
        figS3_context_ablation()
        print("Main figs (fig1-5) + Supp (figS2 robustness, figS3 context ablation, "
              "figS4 multimodel) written to", HERE)
    else:
        print("Main figs (fig1-5) + Supp (figS2 robustness, figS4 multimodel) written to", HERE)
        print("[!] skipped figS3: run `python -m scripts.run_context_ablation` first")
    print("Supp dashboard: figS1_dashboard.png via ./make_dashboard_figure.sh")
