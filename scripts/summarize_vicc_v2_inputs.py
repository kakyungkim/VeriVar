#!/usr/bin/env python3
"""Input-coverage summary for the pre-registered sop_strict_v2 inputs (no classification).

Purpose:  report the coverage counts the pre-registration (sec. 4, "커버리지 보고") asks for,
          BEFORE any evaluation with the new configuration: per-predictor score availability,
          size of the utilised-line set per predictor configuration, transcript mismatches,
          variants with continental gnomAD AF > 1% / > 5%, AlphaMissense snapshot-vs-VEP
          agreement, CIViC rows added by the monthly release and benchmark variants whose
          exact-match CIViC functional lines change, and MaveDB DMS LoF coverage.
          The engine is never called and no gold label is read.
Prereq:   python -m scripts.fetch_vicc_v2_inputs (snapshots under data/knowledge/ and
          data/benchmark/vicc_v2/).
Run:      python -m scripts.summarize_vicc_v2_inputs
Output:   data/benchmark/vicc_v2/input_coverage.json (and a console summary).
"""
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.classify.vicc_inputs import (CIVIC_V1, PREDICTOR_FIELDS, civic_release_paths,  # noqa: E402
                                      clinvar_variants, horak_variants, load_civic_rows,
                                      load_dms_lof, load_vep_v2, variant_inputs, _read_tsv)
from src.classify.vicc_rules import (CONFIGS, civic_signal_from_rows,  # noqa: E402
                                     parse_protein_change)

OUT = os.path.join(ROOT, "data", "benchmark", "vicc_v2", "input_coverage.json")
PANEL9 = {"BRAF", "EZH2", "FLT3", "IDH1", "KRAS", "PIK3CA", "PTEN", "RB1", "TP53"}
AM_HORAK = os.path.join(ROOT, "data", "knowledge", "alphamissense", "vep_cache.json")
HORAK_TSV = os.path.join(ROOT, "data", "benchmark", "horak_benchmark.tsv")
CLINVAR_TSV = os.path.join(ROOT, "data", "benchmark", "clinvar_onc",
                           "clinvar_oncogenicity_missense_grch38.tsv")


def existing_am() -> dict:
    """AlphaMissense values the engine already uses (keyed like vicc_inputs.v2_key)."""
    am = json.load(open(AM_HORAK))
    out = {}
    for r in _read_tsv(HORAK_TSV):
        e = am.get(f"{r['b37_chr']}:{r['b37_pos']}:{r['b37_ref']}>{r['b37_alt']}")
        out[("horak", r["gene"], r["aa"])] = e.get("am_pathogenicity") if e else None
    for r in _read_tsv(CLINVAR_TSV):
        v = r.get("am_pathogenicity")
        out[("clinvar", r["gene"], r["aa"])] = float(v) if v not in ("", None) else None
    return out


def civic_by_gene(rows):
    g = defaultdict(list)
    for r in rows:
        g[str(r["molecular_profile"]).split()[0]].append(r)
    return g


def summarise(name, variants, vep, dms_v1, dms_v2, am_old, civ_v1, civ_v2):
    ins = [variant_inputs(v, vep, dms_v2) for v in variants]
    s = {"n": len(ins), "vep_returned": sum(e["vep_returned"] for e in ins),
         "aa_mismatch": [f"{e['gene']} {e['aa']}" for e in ins if not e["aa_match"]],
         "revel_multi_distinct": sum(e["revel_n_distinct"] > 1 for e in ins)}
    for f in PREDICTOR_FIELDS:
        s[f"has_{f}"] = sum(e["predictors"][f] is not None for e in ins)
    ams = [am_old.get((v["benchmark"], v["gene"], v["aa"])) for v in variants]
    s["has_alphamissense_snapshot"] = sum(a is not None for a in ams)
    diffs = [abs(a - e["am_vep"]) for a, e in zip(ams, ins)
             if a is not None and e["am_vep"] is not None]
    s["am_snapshot_vs_vep"] = {"n_both": len(diffs),
                               "n_abs_diff_gt_0.001": sum(d > 0.001 for d in diffs),
                               "max_abs_diff": round(max(diffs), 4) if diffs else None}
    # utilised-line set size per predictor configuration
    usets = {}
    for cfg in ("sop_strict_v2", "sop_strict_v2_5pred", "sop_strict_v2_revel"):
        preds = CONFIGS[cfg].comp_predictors
        sizes = Counter()
        for a, e in zip(ams, ins):
            sc = dict(e["predictors"], alphamissense=a)
            sizes[sum(sc.get(p) is not None for p in preds)] += 1
        usets[cfg] = {"predictors": list(preds),
                      "utilised_lines_hist": {str(k): v for k, v in sorted(sizes.items())}}
    s["utilised_lines"] = usets
    s["pop_af_max5_gt_0.01"] = sorted(f"{e['gene']} {e['aa']} ({e['pop_af_max5']:.4f}, "
                                      f"{e['pop_af_max5_source']})"
                                      for e in ins if (e["pop_af_max5"] or 0) > 0.01)
    s["pop_af_max5_gt_0.05_n"] = sum((e["pop_af_max5"] or 0) > 0.05 for e in ins)
    # DMS coverage (v1 vs v2)
    def dms_hit(d, v):
        pp = parse_protein_change(v["aa"])
        return bool(pp and (d.get(v["gene"]) or {}).get(f"{pp[0]}{pp[1]}{pp[2]}"))
    s["dms_lof_v1"] = sum(dms_hit(dms_v1, v) for v in variants)
    s["dms_lof_v2"] = sum(dms_hit(dms_v2, v) for v in variants)
    s["dms_lof_new_in_v2"] = sorted(f"{v['gene']} {v['aa']}" for v in variants
                                    if dms_hit(dms_v2, v) and not dms_hit(dms_v1, v))
    # CIViC exact-match functional lines (v1 vs v2)
    changed, n_v1, n_v2 = [], 0, 0
    for v in variants:
        pp = parse_protein_change(v["aa"])
        if not pp:
            continue
        a = civic_signal_from_rows(civ_v1.get(v["gene"], []), v["gene"], *pp)
        b = civic_signal_from_rows(civ_v2.get(v["gene"], []), v["gene"], *pp)
        fa = (a.onco_citations, a.benign_citations)
        fb = (b.onco_citations, b.benign_citations)
        n_v1 += fa != (0, 0)
        n_v2 += fb != (0, 0)
        if fa != fb:
            changed.append(f"{v['gene']} {v['aa']} onco/benign citations {fa} -> {fb}")
    s["civic_functional_any_v1"] = n_v1
    s["civic_functional_any_v2"] = n_v2
    s["civic_functional_changed"] = changed
    return s


def main() -> None:
    vep = load_vep_v2()
    if not vep:
        raise SystemExit("no VEP v2 snapshot; run scripts.fetch_vicc_v2_inputs first")
    dms_v1, dms_v2 = load_dms_lof("v1"), load_dms_lof("v2")
    am_old = existing_am()
    rows_v1 = load_civic_rows("v1")
    rows_v2 = load_civic_rows("v2")
    civ_v1, civ_v2 = civic_by_gene(rows_v1), civic_by_gene(rows_v2)
    hv, cv = horak_variants(), clinvar_variants()
    report = {
        "note": "input coverage only; the engine is not run and no gold label is read",
        "civic": {"v1_rows": len(rows_v1), "v2_rows": len(rows_v2),
                  "added_by_release": len(rows_v2) - len(rows_v1),
                  "release_file": [os.path.relpath(p, ROOT) for p in civic_release_paths()[-1:]],
                  "v1_files": [os.path.relpath(p, ROOT) for p in CIVIC_V1],
                  "v1_genes": len(civ_v1), "v2_genes": len(civ_v2),
                  "added_functional_rows": sum(
                      1 for r in rows_v2[len(rows_v1):]
                      if str(r.get("evidence_type", "")).lower() == "functional")},
        "dms_v2_genes": {g: len(v) for g, v in sorted(dms_v2.items())},
        "horak": summarise("horak", hv, vep, dms_v1, dms_v2, am_old, civ_v1, civ_v2),
        "clinvar_snapshot_panel9": summarise("clinvar_panel9",
                                             [v for v in cv if v["gene"] in PANEL9], vep,
                                             dms_v1, dms_v2, am_old, civ_v1, civ_v2),
        "clinvar_snapshot_all": summarise("clinvar_all", cv, vep, dms_v1, dms_v2, am_old,
                                          civ_v1, civ_v2),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(report, f, indent=2)
    os.replace(tmp, OUT)
    print(json.dumps({k: v for k, v in report.items()}, indent=1)[:6000])
    print(f"[+] wrote {OUT}")


if __name__ == "__main__":
    main()
