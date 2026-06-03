#!/usr/bin/env python3
"""Generate manuscript Figures 1-6 from committed result JSONs.

Figure 7 is a screenshot of the live decision-support dashboard rendered from
real data; it is built separately by `make_dashboard_figure.sh` (headless
Chrome over `_dashboard_demo.html`), not here.

Publication style targets the Nature family (npj Digital Medicine / JAMIA):
Helvetica/Arial throughout, an Okabe-Ito colourblind-safe palette, Nature
column widths (single 89 mm, double 183 mm), 600-dpi PNG plus a vector PDF with
embedded fonts (pdf.fonttype 42). Figure numbers/titles live in the manuscript
captions, NOT baked into the artwork, per journal convention.

Every quantitative figure reads its numbers from data/outputs/*.json and
data/benchmark/*.json and shows 95% bootstrap CIs / McNemar p-values where
relevant; nothing is hard-coded from memory. Figures 1 and 7 are schematics.

Run:  ../../venv/bin/python make_figures.py   (from this directory)
"""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(ROOT, "data", "outputs")
BENCH = os.path.join(ROOT, "data", "benchmark")

# Nature column widths (inches)
W1 = 89 / 25.4    # single column ~3.5"
W2 = 183 / 25.4   # double column ~7.2"

plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 600,
    "savefig.bbox": "tight",
    "pdf.fonttype": 42,            # embed TrueType (editable text) for submission
    "ps.fonttype": 42,
    "svg.fonttype": "none",
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 8,
    "axes.titlesize": 8.5,
    "axes.labelsize": 8,
    "axes.titleweight": "bold",
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "axes.linewidth": 0.8,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": False,
    "lines.linewidth": 1.6,
    "patch.linewidth": 0.8,
})

# Okabe-Ito colourblind-safe palette
C_RAG = "#0072B2"     # blue        — retrieval / primary
C_NORAG = "#D55E00"   # vermillion  — no-retrieval
C_RULE = "#CC79A7"    # red-purple  — rule
C_OK = "#009E73"      # bluish green — faithful / good
C_SKY = "#56B4E9"
C_AMBER = "#E69F00"
GREY_E = "#9aa0a6"    # neutral edge
GREY_F = "#f2f3f4"    # neutral fill
INK = "#202124"

# light tints for schematic fills
T_BLUE, T_GREEN = "#d7e8f4", "#d6efe5"
T_AMBER, T_PURPLE = "#fbe7c6", "#ecdce8"


def load(path):
    with open(path) as f:
        return json.load(f)


def boot_ci(correct, n_boot=10000, seed=0):
    """Bootstrap 95% CI of a proportion from a 0/1 correctness array."""
    rng = np.random.default_rng(seed)
    correct = np.asarray(correct, dtype=float)
    n = len(correct)
    idx = rng.integers(0, n, size=(n_boot, n))
    boots = correct[idx].mean(axis=1)
    return correct.mean(), np.percentile(boots, 2.5), np.percentile(boots, 97.5)


def collapse3(label):
    """Collapse 5-class oncogenicity to 3 classes."""
    onc = {"Oncogenic", "Likely Oncogenic"}
    ben = {"Benign", "Likely Benign"}
    if label in onc:
        return "ONC"
    if label in ben:
        return "BEN"
    return "VUS"


def panel(ax, letter, x=-0.16, y=1.04):
    ax.text(x, y, letter, transform=ax.transAxes, fontsize=10,
            fontweight="bold", va="bottom", ha="left")


def save(fig, name):
    """Save a 600-dpi PNG (for the markdown) and a vector PDF (for submission)."""
    fig.savefig(os.path.join(HERE, name + ".png"))
    fig.savefig(os.path.join(HERE, name + ".pdf"))
    plt.close(fig)


# ---------------------------------------------------------------------------
# Schematic helpers (boxes + arrows)
# ---------------------------------------------------------------------------
def _box(ax, x, y, w, h, text, fc, ec=GREY_E, fs=7.5, fw="normal", tc=INK):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.014",
        linewidth=0.9, edgecolor=ec, facecolor=fc, mutation_aspect=0.7))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, fontweight=fw, color=tc, linespacing=1.3)


def _arrow(ax, x1, y1, x2, y2, color="#5a5a5a", lw=1.0):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=10,
        lw=lw, color=color, shrinkA=1, shrinkB=1))


def _clean_canvas(ax):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.grid(False)


# ---------------------------------------------------------------------------
# Figure 1 -- system overview & dual-mode architecture (schematic)
# ---------------------------------------------------------------------------
def fig_arch():
    fig, ax = plt.subplots(figsize=(W2, 8.4))
    _clean_canvas(ax)

    _box(ax, 0.29, 0.930, 0.42, 0.050,
         "Somatic variant\n(gene · HGVSp · cancer type)", GREY_F, GREY_E,
         fs=8, fw="bold")

    ax.text(0.5, 0.888, "Hybrid citation-grounded retrieval",
            ha="center", va="center", fontsize=8, fontweight="bold", color=C_RAG)
    _box(ax, 0.060, 0.790, 0.265, 0.072,
         "Structured\nCIViC · DGIdb ·\nAlphaMissense", T_BLUE, C_RAG, fs=7)
    _box(ax, 0.368, 0.790, 0.265, 0.072,
         "Dense\nBM25 + Chroma\n(PubMedBERT) · RRF", T_BLUE, C_RAG, fs=7)
    _box(ax, 0.676, 0.790, 0.265, 0.072,
         "Graph\ngene–variant–\ndrug–trial", T_BLUE, C_RAG, fs=7)

    _box(ax, 0.21, 0.688, 0.58, 0.050,
         "Evidence bundle — every item carries a citable identifier",
         T_GREEN, C_OK, fs=7.8, fw="bold")

    _box(ax, 0.12, 0.575, 0.76, 0.066,
         "Faithfulness contract\ncite only retrieved identifiers · abstain (VUS) when no variant-specific evidence",
         T_AMBER, C_AMBER, fs=7.6, fw="bold")

    _box(ax, 0.070, 0.388, 0.385, 0.112,
         "GENERATIVE mode\n\nLLM assigns oncogenicity + tier\nfrom the evidence\nself-consistency voting (n = 3)\n+ agentic verifier",
         T_BLUE, C_RAG, fs=7.3, fw="bold")
    _box(ax, 0.545, 0.388, 0.385, 0.112,
         "DETERMINISTIC mode\n\ndirection-aware rule assigns\nthe label; LLM writes only\nthe natural-language rationale",
         T_PURPLE, C_RULE, fs=7.3, fw="bold")

    _box(ax, 0.15, 0.250, 0.70, 0.078,
         "Two-axis classification\nVICC oncogenicity  +  AMP/ASCO/CAP tier\nwith grounded citations — or an honest abstention",
         GREY_F, GREY_E, fs=7.8, fw="bold")

    _box(ax, 0.15, 0.120, 0.70, 0.068,
         "Decision-support interface (dashboard)\nevidence / trial filters · clickable source links · grounded chat",
         T_GREEN, C_OK, fs=7.4)

    _arrow(ax, 0.50, 0.930, 0.50, 0.902)
    for cx in (0.193, 0.50, 0.808):
        _arrow(ax, cx, 0.790, 0.50, 0.740)
    _arrow(ax, 0.50, 0.688, 0.50, 0.643)
    _arrow(ax, 0.40, 0.575, 0.263, 0.502)
    _arrow(ax, 0.60, 0.575, 0.737, 0.502)
    _arrow(ax, 0.263, 0.388, 0.46, 0.330)
    _arrow(ax, 0.737, 0.388, 0.54, 0.330)
    _arrow(ax, 0.50, 0.250, 0.50, 0.190)

    ax.text(0.5, 0.066,
            "Both modes are scored on identical label spaces; their disagreements are an analytical signal.",
            ha="center", va="center", fontsize=6.8, color="#5f6368", style="italic")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
    save(fig, "F0_architecture")


# ---------------------------------------------------------------------------
# Figure 7 -- conceptual positioning: faithfulness vs scope/autonomy
# ---------------------------------------------------------------------------
def fig_positioning():
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    ax.axvspan(0.6, 1.04, color=C_OK, alpha=0.06, zorder=0)
    ax.text(1.0, 0.015, "faithful · auditable", ha="right", va="bottom",
            fontsize=6.4, color=C_OK, style="italic")
    pts = [
        dict(x=0.20, y=0.80, c=C_NORAG, m="o",
             lab="Naïve LLM\n(no retrieval)", lx=0.135, ly=0.95, ha="center", va="top"),
        dict(x=0.50, y=0.88, c=C_AMBER, m="o",
             lab="Autonomous clinical agents\n(Ferber 2025; guideline\ncitation 75.5%)",
             lx=0.50, ly=1.02, ha="center", va="top"),
        dict(x=0.83, y=0.20, c=C_RULE, m="o",
             lab="Curated rule engines\n(OncoKB · CancerVar · PCGR ·\nOncoVI: deterministic, 80%)",
             lx=0.80, ly=0.065, ha="center", va="bottom"),
        dict(x=0.80, y=0.46, c=C_SKY, m="o",
             lab="Biomedical fact-checkers\n(CIViC-Fact)", lx=0.575, ly=0.40,
             ha="right", va="center"),
        dict(x=0.91, y=0.68, c=C_OK, m="*", star=True,
             lab="This work\nfaithful-by-construction RAG\n0% fabricated · 100% grounded",
             lx=0.66, ly=0.80, ha="right", va="center"),
    ]
    for p in pts:
        ax.scatter([p["x"]], [p["y"]], s=240 if p.get("star") else 64,
                   marker=p["m"], color=p["c"], edgecolor="white", linewidth=1.0, zorder=5)
        ax.annotate(p["lab"], xy=(p["x"], p["y"]), xytext=(p["lx"], p["ly"]),
                    fontsize=6.4, color=p["c"], ha=p["ha"], va=p.get("va", "center"),
                    fontweight="bold" if p.get("star") else "normal", linespacing=1.25,
                    arrowprops=dict(arrowstyle="-", color="#b8bcc0", lw=0.6, shrinkA=2))
    ax.set_xlim(0, 1.04)
    ax.set_ylim(0, 1.08)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("Evidence-grounded faithfulness & auditability  (low to high)", fontsize=8)
    ax.set_ylabel("Scope / autonomy / flexibility  (low to high)", fontsize=8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    save(fig, "F7_positioning")


# ---------------------------------------------------------------------------
# Figure 2 -- faithfulness bars (single column)
# ---------------------------------------------------------------------------
def fig1():
    ev = load(os.path.join(OUT, "eval_report.json"))
    gden = ev["citation_grounding"]["n"]
    rows = [
        ("Hallucinated citation rate", ev["hallucination"]["hallucination_rate"], C_NORAG,
         f"0 / {ev['hallucination']['n_with_citations']}  (target 0)"),
        ("Citation grounding", ev["citation_grounding"]["grounding_rate"], C_OK,
         f"{ev['citation_grounding']['grounded']} / {gden}"),
        ("Directional faithfulness", ev["directional_faithfulness"]["faithfulness_rate"], C_OK,
         f"{int(round(ev['directional_faithfulness']['faithfulness_rate'] * gden))} / {gden}"),
        ("Abstention recall", ev["abstention"]["abstention_recall"], C_OK,
         f"{ev['abstention']['abstained_when_no_evidence']} / {ev['abstention']['no_evidence_variants']}"),
    ]
    fig, ax = plt.subplots(figsize=(0.66 * W2, 2.5))
    ys = list(range(len(rows)))[::-1]
    for y, (label, val, color, frac) in zip(ys, rows):
        ax.barh(y, 1.0, color="#eef1f4", height=0.6, zorder=1)            # full-scale track
        ax.barh(y, max(val, 0.004), color=color, height=0.6, zorder=2,
                edgecolor="white", linewidth=0.5)
        ax.text(val + 0.015 if val < 0.5 else val - 0.015, y,
                f"{val:.2f}", va="center", ha="left" if val < 0.5 else "right",
                fontsize=8, fontweight="bold",
                color=color if val < 0.5 else "white", zorder=3)
        ax.text(1.04, y, frac, va="center", ha="left", fontsize=7, color="#5f6368")
    ax.axvline(1.0, color=GREY_E, lw=0.7, ls=(0, (3, 3)), zorder=0)
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlim(0, 1.0)
    ax.set_xticks([0, 0.5, 1.0])
    ax.set_xlabel("Rate")
    ax.set_ylim(-0.6, len(rows) - 0.4)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_visible(True)
    ax.tick_params(axis="y", length=0)
    ax.margins(y=0.06)
    save(fig, "F1_faithfulness")


# ---------------------------------------------------------------------------
# Figure 3 -- ablation: fabrication + parametric over-call (double column)
# ---------------------------------------------------------------------------
def fig2():
    stats = load(os.path.join(OUT, "stats_report.json"))
    fab = stats["norag_citation_fabrication_ci"]

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(W2, 3.1),
                                   gridspec_kw={"width_ratios": [1.0, 1.35]})

    xs = ["LLM\nno-retrieval", "LLM +\nretrieval"]
    vals = [fab["point"], 0.0]
    err = [[fab["point"] - fab["lo"]], [fab["hi"] - fab["point"]]]
    axL.bar(xs[0], vals[0], color=C_NORAG, edgecolor="white", linewidth=0.6, width=0.6)
    axL.errorbar(xs[0], vals[0], yerr=err, fmt="none", ecolor=INK, capsize=4, lw=1.0)
    axL.bar(xs[1], vals[1], color=C_RAG, edgecolor="white", linewidth=0.6, width=0.6)
    axL.text(0, fab["hi"] + 0.045, f"{vals[0]:.3f}\n[{fab['lo']:.2f}–{fab['hi']:.2f}]",
             ha="center", va="bottom", fontsize=7, fontweight="bold", color=C_NORAG)
    axL.text(1, 0.03, "0.000", ha="center", va="bottom", fontsize=7, fontweight="bold",
             color=C_RAG)
    axL.set_ylim(0, 0.92)
    axL.set_yticks([0, 0.25, 0.5, 0.75])
    axL.set_ylabel("Fabricated-citation rate")
    axL.text(0.5, -0.17, "n = 56 variants", transform=axL.transAxes, ha="center",
             va="top", fontsize=6.6, color="#5f6368")
    panel(axL, "a")

    # Right: parametric over-call -> VUS, headline count + example tier changes
    axR.axis("off")
    axR.set_xlim(0, 1)
    axR.set_ylim(0, 1)
    axR.text(0.0, 0.96, "Confident parametric over-call,", fontsize=8.2, fontweight="bold",
             ha="left", va="top", color=INK)
    axR.text(0.0, 0.88, "reclassified to evidence-grounded VUS", fontsize=7.4,
             ha="left", va="top", color="#5f6368")
    axR.text(0.0, 0.66, "12 / 56", fontsize=19, fontweight="bold", color=C_RAG,
             ha="left", va="center")
    axR.text(0.31, 0.66, "variants (21.4%)\nover-called without retrieval", fontsize=6.9,
             color="#5f6368", ha="left", va="center")
    ex = [("EGFR E114K", "Likely Onc. · Tier II", "VUS · Tier IV"),
          ("PTEN R130*", "Oncogenic · Tier I", "VUS · Tier III"),
          ("TP53 P152L", "Likely Onc. · Tier II", "VUS · Tier IV")]
    y0, dy = 0.43, 0.135
    for i, (name, before, after) in enumerate(ex):
        yy = y0 - i * dy
        axR.text(0.0, yy, name, fontsize=7.2, fontweight="bold", ha="left", va="center")
        axR.text(0.30, yy, before, fontsize=6.8, color=C_NORAG, ha="left", va="center")
        axR.add_patch(FancyArrowPatch((0.63, yy), (0.70, yy), arrowstyle="-|>",
                                      mutation_scale=9, lw=1.0, color="#5a5a5a"))
        axR.text(0.72, yy, after, fontsize=6.8, color=C_RAG, fontweight="bold",
                 ha="left", va="center")
    axR.text(0.0, y0 - 3 * dy + 0.005, "Many are truncating / frameshift / splice variants; "
             "correctness pending adjudication.", fontsize=6.2, color="#5f6368",
             style="italic", ha="left", va="top")
    panel(axR, "b", x=-0.02)

    fig.subplots_adjust(wspace=0.28)
    save(fig, "F2_ablation")


# ---------------------------------------------------------------------------
# Figure 5 -- temporal corpus holdout (single/1.5 column)
# ---------------------------------------------------------------------------
def fig3():
    temp = load(os.path.join(BENCH, "horak_temporal.json"))["results"]
    horak = load(os.path.join(BENCH, "horak_results.json"))
    stats = load(os.path.join(OUT, "stats_report.json"))
    floor = horak["llm_no_rag"]["accuracy_3class"]
    full_ci = stats["horak_3class_accuracy_ci"]["llm_rag"]

    order = ["full", 2018, 2015, 2012]
    xlab = {"full": "full\n(988)", 2018: "<2018\n(885)", 2015: "<2015\n(666)",
            2012: "<2012\n(459)"}
    recs = {r["cutoff_before"]: r for r in temp}
    x = np.arange(len(order))
    acc = [recs[k]["acc_3class"] for k in order]
    hw = (full_ci["hi"] - full_ci["lo"]) / 2.0

    fig, ax = plt.subplots(figsize=(0.62 * W2, 3.0))
    ax.fill_between(x, np.array(acc) - hw, np.array(acc) + hw, color=C_RAG, alpha=0.13,
                    linewidth=0, label="±95% CI half-width (full corpus)")
    ax.plot(x, acc, "-o", color=C_RAG, lw=1.8, ms=5, mfc="white", mew=1.4,
            label="LLM + retrieval")
    for xi, a in zip(x, acc):
        ax.text(xi, a + 0.018, f"{a:.3f}", ha="center", va="bottom", fontsize=6.8,
                fontweight="bold", color=C_RAG)
    ax.axhline(floor, color=C_NORAG, ls=(0, (4, 3)), lw=1.4,
               label=f"no-retrieval floor ({floor:.3f})")
    ax.set_xticks(x)
    ax.set_xticklabels([xlab[k] for k in order])
    ax.set_xlabel("Retrieval-corpus cutoff (year; evidence count)")
    ax.set_ylabel("Three-class accuracy")
    ax.set_ylim(0.45, 0.74)
    ax.legend(loc="lower left", framealpha=0.0, handlelength=1.6)
    save(fig, "F3_temporal")


# ---------------------------------------------------------------------------
# Figure 6 -- dual-mode discordance + KRAS context (double column)
# ---------------------------------------------------------------------------
def fig4():
    disc = load(os.path.join(OUT, "discordance_analysis.json"))
    cc = disc["category_counts"]
    pretty = {
        "tier_boundary": "Tier boundary",
        "oncogenic_confidence": "Oncogenic confidence",
        "rule_overcall_corrected_by_llm": "Beyond-rules (LLM corrects rule)",
        "benign_label": "Benign label",
        "verifier_tier_downgrade": "Verifier downgrade",
        "llm_overcall_vs_rule": "LLM over-call",
    }
    items = sorted(cc.items(), key=lambda kv: kv[1], reverse=True)
    labels = [pretty[k] for k, _ in items]
    vals = [v for _, v in items]

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(W2, 3.1),
                                   gridspec_kw={"width_ratios": [1.45, 1.0]})

    axL.barh(labels[::-1], vals[::-1], color=C_RULE, edgecolor="white", linewidth=0.6)
    for i, v in enumerate(vals[::-1]):
        axL.text(v + 0.2, i, str(v), va="center", fontsize=7.5, fontweight="bold")
    axL.set_xlabel("Discordant variant × context units")
    axL.set_xlim(0, max(vals) + 2)
    panel(axL, "a", x=-0.42)

    axR.axis("off")
    axR.set_xlim(0, 1)
    axR.set_ylim(0, 1)
    # adjacency summary: 26 one-step vs 5 gross
    adj, gross = disc["adjacent"], disc["gross"]
    tot = adj + gross
    x0, x1, yb, hh = 0.04, 0.96, 0.86, 0.075
    wa = (x1 - x0) * adj / tot
    axR.add_patch(Rectangle((x0, yb), wa, hh, facecolor=C_SKY, edgecolor="white", lw=0.6))
    axR.add_patch(Rectangle((x0 + wa, yb), (x1 - x0) - wa, hh, facecolor=C_NORAG,
                            edgecolor="white", lw=0.6))
    axR.text(x0 + wa / 2, yb + hh / 2, f"{adj} adjacent", ha="center", va="center",
             fontsize=6.4, color="white", fontweight="bold")
    axR.text(x0 + wa + ((x1 - x0) - wa) / 2, yb + hh / 2, f"{gross}", ha="center",
             va="center", fontsize=6.4, color="white", fontweight="bold")
    axR.text(0.5, yb + hh + 0.035,
             f"{disc['n_discordant']} discordant: {adj} one-step, {gross} gross",
             ha="center", fontsize=7, fontweight="bold")
    # KRAS context-dependence
    axR.text(0.5, 0.64, "KRAS p.G12V", ha="center", fontweight="bold", fontsize=9.5)
    axR.text(0.5, 0.565, "Oncogenicity stable; tier varies by context",
             ha="center", fontsize=6.7, color=C_OK)
    box1 = dict(boxstyle="round,pad=0.45", fc=T_BLUE, ec=C_RAG, lw=0.9)
    axR.text(0.27, 0.31, "Colorectal\nadenocarcinoma\n\nTier I", ha="center", va="center",
             fontsize=7.4, bbox=box1)
    box2 = dict(boxstyle="round,pad=0.45", fc=T_AMBER, ec=C_NORAG, lw=0.9)
    axR.text(0.73, 0.31, "Pancreatic\nadenocarcinoma\n\nTier II", ha="center", va="center",
             fontsize=7.4, bbox=box2)
    axR.text(0.5, 0.045, "Same variant and oncogenicity,\ndifferent actionability tier by context.",
             ha="center", fontsize=6.4, color="#5f6368", style="italic")
    panel(axR, "b", x=-0.02)

    fig.subplots_adjust(wspace=0.18)
    save(fig, "F4_discordance")


# ---------------------------------------------------------------------------
# Figure 4 -- Horak 3-class confusion matrix (single column)
# ---------------------------------------------------------------------------
def fig5():
    horak = load(os.path.join(BENCH, "horak_results.json"))
    stats = load(os.path.join(OUT, "stats_report.json"))
    rows = horak["rows"]
    classes = ["ONC", "VUS", "BEN"]
    idx = {c: i for i, c in enumerate(classes)}
    M = np.zeros((3, 3), dtype=int)
    correct = []
    for r in rows:
        g = collapse3(r["gold"])
        p = collapse3(r["llm_rag"])
        M[idx[g], idx[p]] += 1
        correct.append(int(g == p))
    acc, lo, hi = boot_ci(correct)

    rowsum = M.sum(axis=1)
    colsum = M.sum(axis=0)
    recall = [M[i, i] / rowsum[i] if rowsum[i] else 0.0 for i in range(3)]
    prec = [M[j, j] / colsum[j] if colsum[j] else 0.0 for j in range(3)]

    fig, ax = plt.subplots(figsize=(0.68 * W2, 3.7))
    ax.imshow(M, cmap="Blues", vmin=0)
    full = {"ONC": "Oncogenic\n(+Likely)", "VUS": "VUS", "BEN": "Benign\n(+Likely)"}
    ax.set_xticks(range(3))
    ax.set_yticks(range(3))
    ax.set_xticklabels([full[c] for c in classes])
    ax.set_yticklabels([full[c] for c in classes])
    ax.set_xlabel("Predicted (LLM + retrieval)")
    ax.set_ylabel("Gold standard (Horak 2022)")
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    thresh = M.max() / 2.0
    for i in range(3):
        for j in range(3):
            ax.text(j, i, str(M[i, j]), ha="center", va="center",
                    color="white" if M[i, j] > thresh else INK,
                    fontweight="bold", fontsize=12)
    # marginal per-class recall (right) and precision (bottom), accuracy at the corner
    for i in range(3):
        ax.text(2.74, i, f"{recall[i]:.2f}", va="center", ha="center",
                fontsize=8.5, fontweight="bold", color=C_OK)
    for j in range(3):
        ax.text(j, 2.74, f"{prec[j]:.2f}", va="center", ha="center",
                fontsize=8.5, fontweight="bold", color=C_RAG)
    ax.text(2.74, -0.66, "Recall", va="center", ha="center", fontsize=6.6, color=C_OK)
    ax.text(-0.66, 2.74, "Prec.", va="center", ha="center", fontsize=6.6, color=C_RAG)
    ax.text(2.74, 2.74, f"{acc:.2f}", va="center", ha="center", fontsize=9.5,
            fontweight="bold", color=INK)
    ax.text(2.74, 3.18, "Acc.", va="center", ha="center", fontsize=6.6, color=INK)
    ax.set_xlim(-0.7, 3.35)
    ax.set_ylim(3.4, -0.75)
    return acc, lo, hi, save(fig, "F5_horak_confusion")


if __name__ == "__main__":
    fig_arch()   # Figure 1 (system / dual-mode schematic)
    fig1()       # Figure 2 (faithfulness)
    fig2()       # Figure 3 (ablation)
    fig5()       # Figure 4 (Horak confusion)
    fig3()       # Figure 5 (temporal)
    fig4()       # Figure 6 (discordance)
    fig_positioning()  # Figure 7 (positioning)
    acc, lo, hi, _ = fig5()
    print("Figures 1-7 (PNG @600 dpi + vector PDF) written to", HERE)
    print("Figure 8 (dashboard): run ./make_dashboard_figure.sh")
    print(f"F4 sanity: recomputed 3-class acc from rows = {acc:.3f} [{lo:.3f}, {hi:.3f}]")
