#!/usr/bin/env python3
"""Run every VICC rule-arm consumer for a set of named configurations.

Purpose:  the improvement round (pre-registration notes/audits/2026-09-24/
          개선라운드_사전명시_20260924.md) reports every configuration regardless of outcome.
          This driver runs, per configuration, the same consumer scripts used for the published
          configurations and writes their outputs to ``data/benchmark/vicc_configs/<config>/``:
            horak_vicc.json (+ vicc_roc.png)         scripts.run_horak_vicc
            horak_sensitivity_modes.json             scripts.run_horak_sensitivity_modes
            oncovi_headtohead.json                   scripts.run_oncovi_headtohead
            cancervar_headtohead.json                scripts.run_cancervar_headtohead
            hemaguide_headtohead.json                scripts.run_hemaguide_headtohead
            clinvar_onc_holdout(_rows).json          scripts.run_clinvar_onc_holdout
            horak_known_novel.json                   scripts.run_horak_known_novel
                                                     (--composition-from the top-level output:
                                                      the strata do not depend on the config)
            precision_recall_report.json             scripts.eval_precision_recall
          The top-level primary files in data/benchmark/ and docs/manuscript/ are NOT written.
          Where a configuration already had outputs, the previous Horak and ClinVar rows are
          compared with the new ones and recorded in ``_suite_log.json`` (reproduction check).
Prereq:   python -m scripts.fetch_vicc_v2_inputs (v2-family inputs); the top-level
          data/benchmark/horak_known_novel.json (evidence composition).
Run:      python -m scripts.run_vicc_config_suite [--configs a,b,...] [--jobs 4]
          (default: the three published configurations + the whole v2 family)
Output:   data/benchmark/vicc_configs/<config>/*.json, data/benchmark/vicc_configs/
          _suite_log.json. Then run python -m scripts.build_vicc_config_comparison.
"""
import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from src.classify.vicc_rules import CONFIGS, V2_FAMILY  # noqa: E402

BENCH = os.path.join(ROOT, "data", "benchmark")
CFG_DIR = os.path.join(BENCH, "vicc_configs")
COMPOSITION = os.path.join(BENCH, "horak_known_novel.json")
PUBLISHED = ("original", "os2_fixed", "sop_strict")


def _load(path: str) -> Optional[dict]:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _run(args: List[str]) -> Dict[str, object]:
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m"] + args, cwd=ROOT, capture_output=True, text=True,
                       env=dict(os.environ, MPLBACKEND="Agg"))
    return {"cmd": " ".join(args), "rc": p.returncode, "seconds": round(time.time() - t0, 1),
            "tail": (p.stdout + p.stderr)[-600:]}


def steps_for(cfg: str) -> List[List[str]]:
    d = os.path.relpath(os.path.join(CFG_DIR, cfg), ROOT)
    j = lambda name: os.path.join(d, name)  # noqa: E731
    return [
        ["scripts.run_horak_vicc", "--config", cfg, "--out", j("horak_vicc.json"),
         "--roc-png", j("vicc_roc.png")],
        ["scripts.run_horak_sensitivity_modes", "--config", cfg,
         "--out", j("horak_sensitivity_modes.json")],
        ["scripts.run_oncovi_headtohead", "--ours", j("horak_vicc.json"),
         "--out", j("oncovi_headtohead.json")],
        ["scripts.run_cancervar_headtohead", "--ours", j("horak_vicc.json"),
         "--out", j("cancervar_headtohead.json"), "--oncovi-h2h", j("oncovi_headtohead.json")],
        ["scripts.run_hemaguide_headtohead", "--ours", j("horak_vicc.json"),
         "--out", j("hemaguide_headtohead.json")],
        ["scripts.run_clinvar_onc_holdout", "--config", cfg,
         "--out", j("clinvar_onc_holdout.json"),
         "--out-rows", j("clinvar_onc_holdout_rows.json")],
        ["scripts.run_horak_known_novel", "--vicc", j("horak_vicc.json"),
         "--composition-from", os.path.relpath(COMPOSITION, ROOT),
         "--out", j("horak_known_novel.json")],
        ["scripts.eval_precision_recall", "--horak-vicc", j("horak_vicc.json"),
         "--clinvar-rows", j("clinvar_onc_holdout_rows.json"),
         "--out", j("precision_recall_report.json")],
    ]


def run_config(cfg: str) -> dict:
    d = os.path.join(CFG_DIR, cfg)
    os.makedirs(d, exist_ok=True)
    prev_h = _load(os.path.join(d, "horak_vicc.json"))
    prev_c = _load(os.path.join(d, "clinvar_onc_holdout_rows.json"))
    log: Dict[str, object] = {"config": cfg, "steps": []}
    for s in steps_for(cfg):
        r = _run(s)
        log["steps"].append(r)
        if r["rc"] != 0:
            log["failed"] = r["cmd"]
            return log
    new_h = _load(os.path.join(d, "horak_vicc.json"))
    new_c = _load(os.path.join(d, "clinvar_onc_holdout_rows.json"))
    rep: Dict[str, bool] = {}
    if prev_h is not None:
        rep["horak_rows_identical"] = prev_h["rows"] == new_h["rows"]
    if prev_c is not None:
        key = lambda rows: [(r["key"], r["pred"], r["points"], r["codes"]) for r in rows]  # noqa
        rep["clinvar_rows_identical"] = key(prev_c) == key(new_c)
    log["reproduction_vs_previous_outputs"] = rep or "no previous outputs"
    return log


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--configs", default=",".join(PUBLISHED + V2_FAMILY))
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    cfgs = [c.strip() for c in args.configs.split(",") if c.strip()]
    unknown = [c for c in cfgs if c not in CONFIGS]
    if unknown:
        raise SystemExit(f"unknown configs: {unknown}")
    if not os.path.exists(COMPOSITION):
        raise SystemExit(f"missing {COMPOSITION}; run scripts.run_horak_known_novel first")
    logs = {}
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(run_config, c): c for c in cfgs}
        for f in as_completed(futs):
            lg = f.result()
            logs[lg["config"]] = lg
            status = ("FAILED " + str(lg["failed"])) if "failed" in lg else "ok"
            print(f"  {lg['config']:26s} {status}  "
                  f"{lg.get('reproduction_vs_previous_outputs', '')}", flush=True)
    path = os.path.join(CFG_DIR, "_suite_log.json")
    old = _load(path) or {}
    old.update(logs)
    old["_last_run_utc"] = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(old, f, indent=1)
    os.replace(tmp, path)
    failed = [c for c, lg in logs.items() if "failed" in lg]
    print(f"[+] {len(logs) - len(failed)}/{len(logs)} configurations completed; log {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
