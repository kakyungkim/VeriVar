#!/usr/bin/env python3
"""Scratch-render the manuscript figures from one VICC configuration's outputs.

Purpose:  preview how the committed figures would look if a candidate configuration became
          the primary, WITHOUT touching the committed figures or the top-level data files.
          The script builds a read-only overlay of data/benchmark/ in which the per-
          configuration outputs (data/benchmark/vicc_configs/<config>/) replace the top-level
          rule-arm files, points docs/manuscript/figures/make_figures.py at that overlay and at
          a separate output folder, renders every main and supplementary figure, and reports
          which figures differ from the committed PNGs (pixel comparison).
Prereq:   python -m scripts.run_vicc_config_suite (per-configuration outputs).
Run:      python -m scripts.scratch_render_vicc_figures --config sop_strict_v2 [--config ...]
Output:   data/benchmark/vicc_configs/<config>/figures_scratch/{fig*.png,pdf, render_report.json}
          (the overlay folder _render_bench/ is removed afterwards).
"""
import argparse
import importlib.util
import json
import os
import shutil
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
CFG_DIR = os.path.join(BENCH, "vicc_configs")
FIG_DIR = os.path.join(ROOT, "docs", "manuscript", "figures")
RULE_ARM_FILES = ("horak_vicc.json", "horak_sensitivity_modes.json", "oncovi_headtohead.json",
                  "cancervar_headtohead.json", "hemaguide_headtohead.json",
                  "clinvar_onc_holdout.json", "clinvar_onc_holdout_rows.json",
                  "horak_known_novel.json")
FIGS = ("fig1", "fig2", "fig3", "fig4", "fig5", "figS1_robustness", "figS2_multimodel")


def _png_equal(a: str, b: str) -> object:
    if not (os.path.exists(a) and os.path.exists(b)):
        return "missing"
    import matplotlib.image as mpimg
    x, y = mpimg.imread(a), mpimg.imread(b)
    if x.shape != y.shape:
        return f"size differs {x.shape[:2]} vs {y.shape[:2]}"
    return bool(np.array_equal(x, y))


def render(cfg: str) -> dict:
    src = os.path.join(CFG_DIR, cfg)
    if not os.path.exists(os.path.join(src, "horak_vicc.json")):
        raise SystemExit(f"no outputs for {cfg}; run scripts.run_vicc_config_suite")
    overlay = os.path.join(src, "_render_bench")
    out = os.path.join(src, "figures_scratch")
    shutil.rmtree(overlay, ignore_errors=True)
    os.makedirs(overlay)
    os.makedirs(out, exist_ok=True)
    for name in os.listdir(BENCH):
        p = os.path.join(BENCH, name)
        if os.path.isfile(p):
            os.symlink(p, os.path.join(overlay, name))
    for name in RULE_ARM_FILES:
        q = os.path.join(src, name)
        if os.path.exists(q):
            os.remove(os.path.join(overlay, name))
            os.symlink(q, os.path.join(overlay, name))
    spec = importlib.util.spec_from_file_location("make_figures_scratch",
                                                  os.path.join(FIG_DIR, "make_figures.py"))
    mf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mf)
    mf.BENCH = overlay          # module globals are read at call time
    mf.HERE = out
    report = {"config": cfg, "figures": {}}
    try:
        for f in FIGS:
            try:
                getattr(mf, f)()
                report["figures"][f] = {"rendered": True, "identical_to_committed_png":
                                        _png_equal(os.path.join(out, f + ".png"),
                                                   os.path.join(FIG_DIR, f + ".png"))}
            except Exception as e:  # noqa: BLE001 - report and continue
                report["figures"][f] = {"rendered": False, "error": repr(e)[:300]}
    finally:
        shutil.rmtree(overlay, ignore_errors=True)
    roc = os.path.join(src, "vicc_roc.png")
    report["vicc_roc_identical_to_committed"] = _png_equal(
        roc, os.path.join(FIG_DIR, "diagnostic", "vicc_roc.png"))
    with open(os.path.join(out, "render_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", action="append", required=True)
    args = ap.parse_args()
    sys.path.insert(0, ROOT)
    for c in args.config:
        r = render(c)
        print(f"[{c}]")
        for f, v in r["figures"].items():
            print(f"    {f:18s} {v}")
        print(f"    vicc_roc identical: {r['vicc_roc_identical_to_committed']}")


if __name__ == "__main__":
    main()
