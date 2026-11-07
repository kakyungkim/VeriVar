#!/usr/bin/env python3
"""Side-by-side numbers for the three VICC rule-arm configurations.

Reads the per-configuration outputs in ``data/benchmark/vicc_configs/<config>/`` (written
by the consumer scripts; ``sop_strict`` is the primary and is also the set of files at the
top of ``data/benchmark/``) and writes ``data/benchmark/vicc_config_comparison.json`` with
Horak-70 headline metrics, the Table 2 dial, the OncoVI / CancerVar / HemaGuide head-to-
heads, the ClinVar oncogenicity holdout (panel9, all genes), the known/novel strata, the
per-gene table (Supplementary S1) and the per-class table (Supplementary S2).

Configurations (see ``src.classify.vicc_rules.CONFIGS``):
  sop_strict  primary: Horak 2022 SOP implemented to the letter where open data allow
  os2_fixed   sensitivity: original engine with only the CIViC -> OS2 mapping fixed
  original    sensitivity: engine as published before 2026-09-24
  sop_strict_v2 family (added 2026-09-24, pre-registered in notes/audits/2026-09-24/
  개선라운드_사전명시_20260924.md): candidate sop_strict_v2, sensitivity configurations and
  per-change ablations. For every non-reference configuration the block ``vs_sop_strict``
  gives exact McNemar tests against sop_strict on Horak three-class correctness and on the
  ClinVar ONC-vs-VUS binary call (panel9, all), plus Wilson / Clopper-Pearson intervals.
  The primary configuration is NOT changed by this script.

Offline, no LLM. Usage:  python -m scripts.build_vicc_config_comparison
"""
import json
import os
from collections import defaultdict

from scripts.eval_precision_recall import ORDER, prf, quadratic_weighted_kappa
from src.classify.vicc_rules import CONFIGS, V2_FAMILY
from src.eval.stats import boundary_ci, mcnemar

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
CFG_DIR = os.path.join(BENCH, "vicc_configs")
ORDER_CFG = ["original", "os2_fixed", "sop_strict"] + list(V2_FAMILY)
REFERENCE = "sop_strict"
PANEL9 = {"BRAF", "EZH2", "FLT3", "IDH1", "KRAS", "PIK3CA", "PTEN", "RB1", "TP53"}
ABLATION_ADD = [("a", "abl_strict_plus_a"), ("a0", "abl_strict_plus_a0"),
                ("b", "abl_strict_plus_b"), ("c1", "abl_strict_plus_c1"),
                ("c2", "abl_strict_plus_c2")]
ABLATION_DROP = [("a", "abl_v2_minus_a"), ("b", "abl_v2_minus_b"),
                 ("c1", "abl_v2_minus_c1"), ("c2", "abl_v2_minus_c2")]
OUT = os.path.join(BENCH, "vicc_config_comparison.json")


def collapse(c: str) -> str:
    return "ONC" if c in ("Oncogenic", "Likely Oncogenic") else (
        "BEN" if c in ("Benign", "Likely Benign") else "VUS")


def load(cfg: str, name: str):
    p = os.path.join(CFG_DIR, cfg, name + ".json")
    return json.load(open(p)) if os.path.exists(p) else None


def horak_block(hv: dict) -> dict:
    rows = hv["rows"]
    by_gene = defaultdict(list)
    for r in rows:
        by_gene[r["variant"].split()[0]].append(collapse(r["vicc"]) == collapse(r["gold"]))
    pairs = [(r["gold"], r["vicc"]) for r in rows]
    per_class = prf(pairs, ORDER)
    return {
        "accuracy_3class": hv["accuracy_3class"], "accuracy_3class_ci": hv["accuracy_3class_ci"],
        "accuracy_5class": hv["accuracy_5class"], "sensitivity_onc": hv["sensitivity_onc"],
        "specificity_onc": hv["specificity_onc"], "auroc_onc": hv["auroc_onc"],
        "pred_dist_3class": hv["pred_dist_3class"],
        "per_gene_accuracy_3class_S1": {g: {"n": len(v), "accuracy": round(sum(v) / len(v), 2)}
                                        for g, v in sorted(by_gene.items())},
        "per_class_S2": {c: {k: (round(x, 3) if isinstance(x, float) else x)
                             for k, x in v.items()} for c, v in per_class.items()},
        "macro_f1_S2": round(sum(v["f1"] for v in per_class.values()) / len(per_class), 3),
        "quadratic_kappa_S2": round(quadratic_weighted_kappa(pairs, ORDER), 3),
        "codes_fired": dict(sorted(_count_codes(rows).items())),
        "sensitivity_onc_exact_ci": hv.get("sensitivity_onc_exact_ci"),
        "specificity_onc_exact_ci": hv.get("specificity_onc_exact_ci"),
        "confusion_3class": _confusion3(rows),
        "benign_direction_errors": [r["variant"] for r in rows
                                    if collapse(r["vicc"]) == "BEN"
                                    and collapse(r["gold"]) != "BEN"],
        "oncogenic_overcalls": [r["variant"] for r in rows
                                if collapse(r["vicc"]) == "ONC"
                                and collapse(r["gold"]) != "ONC"],
    }


def _confusion3(rows):
    c = defaultdict(int)
    for r in rows:
        c[f"{collapse(r['gold'])}->{collapse(r['vicc'])}"] += 1
    return dict(sorted(c.items()))


def vs_reference(cfg: str, hv: dict, rows_c) -> dict:
    """Exact McNemar vs sop_strict (Horak 3-class correctness; ClinVar binary call)."""
    ref_h = load(REFERENCE, "horak_vicc")
    ref_c = load(REFERENCE, "clinvar_onc_holdout_rows")
    out = {}
    if ref_h:
        ref = {r["variant"]: collapse(r["vicc"]) == collapse(r["gold"]) for r in ref_h["rows"]}
        new = {r["variant"]: collapse(r["vicc"]) == collapse(r["gold"]) for r in hv["rows"]}
        ks = sorted(ref)
        m = mcnemar([new[k] for k in ks], [ref[k] for k in ks])
        m["note"] = "a = this configuration, b = sop_strict"
        out["horak_3class"] = m
        out["horak_changed_calls"] = [
            {"variant": r["variant"], "gold": r["gold"], "sop_strict": o["vicc"], cfg: r["vicc"],
             "codes": r["codes"], "sop_strict_codes": o["codes"]}
            for r, o in zip(hv["rows"], ref_h["rows"]) if r["vicc"] != o["vicc"]]
    if ref_c and rows_c:
        ref = {r["key"]: r for r in ref_c if r["gold"] in ("ONC", "VUS")}
        new = {r["key"]: r for r in rows_c if r["gold"] in ("ONC", "VUS")}
        for scope, keep in (("panel9", lambda r: r["gene"] in PANEL9), ("all", lambda r: True)):
            ks = sorted(k for k in ref if keep(ref[k]))
            ok = lambda r: (r["points"] >= 6) == (r["gold"] == "ONC")  # noqa: E731
            m = mcnemar([ok(new[k]) for k in ks], [ok(ref[k]) for k in ks])
            m["n"] = len(ks)
            m["changed_binary_calls"] = sum((new[k]["points"] >= 6) != (ref[k]["points"] >= 6)
                                            for k in ks)
            out[f"clinvar_{scope}_binary"] = m
    return out


def _count_codes(rows):
    c = defaultdict(int)
    for r in rows:
        for code in r["codes"]:
            c[code] += 1
    return c


def h2h_block(d: dict, other: str) -> dict:
    ours = d["ours"]
    out = {"n_shared": d.get("n_shared_variants"),
           "ours_accuracy_3class": ours["accuracy_3class"],
           "ours_accuracy_3class_ci": ours.get("accuracy_3class_ci"),
           "ours_sensitivity_onc": ours["sensitivity_onc"],
           "ours_specificity_onc": ours["specificity_onc"],
           f"{other}_accuracy_3class": d[other]["accuracy_3class"],
           "mcnemar": d["paired_mcnemar_3class"]}
    if "error_breakdown_vs_gold" in ours:
        out["ours_error_breakdown"] = ours["error_breakdown_vs_gold"]
    elif "error_breakdown_vs_gold" in d:
        out["ours_error_breakdown"] = d["error_breakdown_vs_gold"].get("ours")
    return out


def _headline(res: dict) -> dict:
    h = res["horak"]
    out = {"horak_acc3": h["accuracy_3class"], "horak_sens": h["sensitivity_onc"],
           "horak_spec": h["specificity_onc"], "horak_auroc": h["auroc_onc"],
           "horak_benign_errors": len(h["benign_direction_errors"]),
           "horak_onc_overcalls": len(h["oncogenic_overcalls"])}
    for s in ("panel9", "all"):
        c = res.get("clinvar_holdout", {}).get(s)
        if c:
            out[f"clinvar_{s}_sens"] = c["sensitivity"]["point"]
            out[f"clinvar_{s}_spec"] = c["specificity_on_gold_vus"]["point"]
            out[f"clinvar_{s}_auroc"] = c["auroc_points"]["point"]
    return out


def ablation_table(results: dict) -> dict:
    """Per-change ablation: add-one from sop_strict, leave-one-out from sop_strict_v2."""
    out = {"reference_sop_strict": _headline(results[REFERENCE]) if REFERENCE in results else None,
           "reference_sop_strict_v2": (_headline(results["sop_strict_v2"])
                                       if "sop_strict_v2" in results else None),
           "add_one_from_sop_strict": {}, "leave_one_out_from_sop_strict_v2": {}}
    for ch, cfg in ABLATION_ADD:
        if cfg in results:
            out["add_one_from_sop_strict"][ch] = dict(config=cfg, **_headline(results[cfg]))
    for ch, cfg in ABLATION_DROP:
        if cfg in results:
            out["leave_one_out_from_sop_strict_v2"][ch] = dict(config=cfg,
                                                               **_headline(results[cfg]))
    return out


def main() -> None:
    report = {"note": "Primary = sop_strict (unchanged; the user chooses after the improvement "
                      "round). os2_fixed and original are sensitivity analyses; the "
                      "sop_strict_v2 family is the pre-registered improvement round.",
              "configs": {k: CONFIGS[k].description for k in ORDER_CFG}, "results": {}}
    for cfg in ORDER_CFG:
        hv = load(cfg, "horak_vicc")
        if hv is None:
            continue
        res = {"horak": horak_block(hv)}
        dial = load(cfg, "horak_sensitivity_modes")
        if dial:
            res["dial_table2"] = {k: {m: v[m] for m in ("accuracy_3class", "sensitivity",
                                                        "specificity")}
                                  for k, v in dial.items() if not k.startswith("_")}
        for name, other in (("oncovi_headtohead", "oncovi"),
                            ("cancervar_headtohead", "cancervar"),
                            ("hemaguide_headtohead", "hemaguide")):
            d = load(cfg, name)
            if d:
                res[name] = h2h_block(d, other)
        ho = load(cfg, "clinvar_onc_holdout")
        if ho:
            res["clinvar_holdout"] = {
                s: {k: ho["scopes"][s]["detection"].get(k) for k in
                    ("n", "sensitivity", "specificity_on_gold_vus", "auroc_points", "tp", "fn",
                     "tn", "fp", "ppv", "sensitivity_exact_ci",
                     "specificity_on_gold_vus_exact_ci", "ppv_exact_ci")}
                for s in ("panel9", "all")}
        if cfg != REFERENCE:
            res["vs_sop_strict"] = vs_reference(cfg, hv, load(cfg, "clinvar_onc_holdout_rows"))
        kn = load(cfg, "horak_known_novel")
        if kn:
            res["known_novel"] = {
                s: {"n": kn["strata"][s]["n"],
                    "accuracy_3class": kn["strata"][s]["arms"]["vicc"]["accuracy_3class"],
                    "sensitivity_onc":
                        kn["strata"][s]["arms"]["vicc"]["oncogenic_vs_rest"]["sensitivity_onc"],
                    "specificity_onc":
                        kn["strata"][s]["arms"]["vicc"]["oncogenic_vs_rest"]["specificity_onc"]}
                for s in ("known", "novel", "all")}
        report["results"][cfg] = res
    report["ablation"] = ablation_table(report["results"])
    tmp = OUT + ".tmp"
    json.dump(report, open(tmp, "w"), indent=1)
    os.replace(tmp, OUT)
    print(f"[+] wrote {os.path.relpath(OUT, ROOT)}")
    for cfg, res in report["results"].items():
        h = res["horak"]
        print(f"    {cfg:26s} acc3 {h['accuracy_3class']}  sens {h['sensitivity_onc']}  "
              f"spec {h['specificity_onc']}  AUROC {h['auroc_onc']}")


if __name__ == "__main__":
    main()
