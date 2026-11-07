#!/usr/bin/env python3
"""Which computational line blocks or grants OP1/SBP1 when moving from sop_strict to v2.

Purpose:  explain the per-variant OP1/SBP1 changes of the pre-registered change (a)
          (all utilised lines must agree, ClinGen supporting thresholds) by listing, for every
          Horak-70 and ClinVar-holdout variant whose OP1 or SBP1 status differs between the
          sop_strict and sop_strict_v2 outputs, each line's score and direction. Also counts,
          among variants that lost OP1, how often each predictor was the non-agreeing line.
          Descriptive only; thresholds and configurations are not changed by this script.
Prereq:   python -m scripts.run_vicc_config_suite (outputs in data/benchmark/vicc_configs/)
          and the v2 snapshots (scripts.fetch_vicc_v2_inputs).
Run:      python -m scripts.diagnose_vicc_v2_lines
Output:   data/benchmark/vicc_v2/op1_sbp1_diagnosis.json
"""
import json
import os
import sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from src.classify.vicc_inputs import (clinvar_variants, horak_variants,  # noqa: E402
                                      load_vep_v2, variant_inputs)
from src.classify.vicc_rules import CONFIGS, PREDICTOR_THRESHOLDS  # noqa: E402

CFG = os.path.join(ROOT, "data", "benchmark", "vicc_configs")
OUT = os.path.join(ROOT, "data", "benchmark", "vicc_v2", "op1_sbp1_diagnosis.json")
AM_HORAK = os.path.join(ROOT, "data", "knowledge", "alphamissense", "vep_cache.json")
PANEL9 = {"BRAF", "EZH2", "FLT3", "IDH1", "KRAS", "PIK3CA", "PTEN", "RB1", "TP53"}


def _rows(cfg: str, name: str):
    return json.load(open(os.path.join(CFG, cfg, name)))


def main() -> None:
    vep = load_vep_v2()
    table = PREDICTOR_THRESHOLDS[CONFIGS["sop_strict_v2"].comp_thresholds]
    preds = CONFIGS["sop_strict_v2"].comp_predictors
    am_h = json.load(open(AM_HORAK))
    import csv
    hb = list(csv.DictReader(open(os.path.join(ROOT, "data", "benchmark",
                                               "horak_benchmark.tsv")), delimiter="\t"))
    am_by = {f"{r['gene']} {r['aa']}": (am_h.get(f"{r['b37_chr']}:{r['b37_pos']}:"
                                                 f"{r['b37_ref']}>{r['b37_alt']}") or {})
             .get("am_pathogenicity") for r in hb}
    cv_rows = list(csv.DictReader(open(os.path.join(
        ROOT, "data", "benchmark", "clinvar_onc", "clinvar_oncogenicity_missense_grch38.tsv")),
        delimiter="\t"))
    for r in cv_rows:
        v = r.get("am_pathogenicity")
        am_by.setdefault(f"{r['gene']} {r['aa']}", float(v) if v not in ("", None) else None)
    coords = {f"{v['gene']} {v['aa']}": v for v in horak_variants() + clinvar_variants()}

    def lines(variant: str) -> dict:
        v = coords[variant]
        e = variant_inputs(v, vep)
        sc = dict(e["predictors"], alphamissense=am_by.get(variant))
        return {p: {"score": sc.get(p),
                    "direction": ((table[p].direction(float(sc[p])) or "indeterminate")
                                  if sc.get(p) is not None else "not utilised")}
                for p in preds}

    report = {"thresholds": {p: {"onco": table[p].onco, "benign": table[p].benign}
                             for p in preds}}
    for name, fname, idkey, goldkey in (
            ("horak", "horak_vicc.json", "variant", "gold"),
            ("clinvar", "clinvar_onc_holdout_rows.json", None, "gold")):
        a = _rows("sop_strict", fname)
        b = _rows("sop_strict_v2", fname)
        a = a["rows"] if isinstance(a, dict) else a
        b = b["rows"] if isinstance(b, dict) else b
        vid = (lambda r: r["variant"]) if idkey else (lambda r: f"{r['gene']} {r['aa']}")
        changes, blockers = [], Counter()
        for ra, rb in zip(a, b):
            assert vid(ra) == vid(rb)
            ca, cb = set(ra["codes"]), set(rb["codes"])
            d = {c: (c in ca, c in cb) for c in ("OP1", "SBP1") if (c in ca) != (c in cb)}
            if not d:
                continue
            ln = lines(vid(ra))
            rec = {"variant": vid(ra), "gold": ra[goldkey],
                   "scope": "panel9" if vid(ra).split()[0] in PANEL9 else "other",
                   "changes": {c: f"{'on' if x else 'off'}->{'on' if y else 'off'}"
                               for c, (x, y) in d.items()},
                   "lines": ln}
            changes.append(rec)
            if d.get("OP1") == (True, False):
                for p, x in ln.items():
                    if x["direction"] != "onco":
                        blockers[f"{p}:{x['direction']}"] += 1
        gold_onc = (lambda g: g in ("Oncogenic", "Likely Oncogenic")) if name == "horak" \
            else (lambda g: g == "ONC")
        lost = [c for c in changes if c["changes"].get("OP1") == "on->off"]
        report[name] = {
            "n_changed": len(changes),
            "op1_lost": len(lost), "op1_lost_gold_onc": sum(gold_onc(c["gold"]) for c in lost),
            "op1_gained": sum(c["changes"].get("OP1") == "off->on" for c in changes),
            "sbp1_lost": sum(c["changes"].get("SBP1") == "on->off" for c in changes),
            "sbp1_gained": sum(c["changes"].get("SBP1") == "off->on" for c in changes),
            "op1_lost_non_agreeing_line_counts": dict(blockers.most_common()),
            "variants": changes}
        print(f"[{name}] changed {len(changes)}  OP1 lost {len(lost)} "
              f"(gold ONC {report[name]['op1_lost_gold_onc']})  OP1 gained "
              f"{report[name]['op1_gained']}  SBP1 lost {report[name]['sbp1_lost']}  "
              f"gained {report[name]['sbp1_gained']}")
        print(f"    non-agreeing line among OP1 losses: {dict(blockers.most_common())}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(report, f, indent=1)
    os.replace(tmp, OUT)
    print(f"[+] wrote {OUT}")


if __name__ == "__main__":
    main()
