#!/usr/bin/env python3
"""The sensitivity dial: how far our VICC engine can be pushed toward OncoVI's recall.

Our default engine is abstention-first (Horak sens 0.697 / spec 0.973). OncoVI is recall-first
(sens 0.909 / spec 0.806). The gap is the two guideline criteria OncoVI feeds from OncoKB
curation and we deliberately withhold: OS1 (established-oncogenic) and residue-level hotspot OM3.
This script reports accuracy / sensitivity / specificity at four operating points so the
trade-off is explicit and the user can choose where to sit:

  1. conservative (default, maximally non-circular)
  2. + residue-level hotspot OM3 (the faithful Horak hotspot definition)
  3. + OS1 from ClinVar somatic-oncogenicity (guideline-sanctioned, partially circular)
  4. + both

Run `python -m scripts.fetch_horak_clinvar` first for mode 3/4. Usage:
    python -m scripts.run_horak_sensitivity_modes
"""
import argparse
import json
import os
from collections import defaultdict

import pandas as pd

from src.classify.vicc_inputs import V2InputProvider, load_civic_rows, load_dms_lof
from src.classify.vicc_rules import (CONFIGS, PRIMARY_CONFIG, VICCPointClassifier,
                                     civic_signal_from_rows, domain_feature_at,
                                     parse_protein_change)
from src.eval.stats import bootstrap_ci, boundary_ci

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")


def collapse(c):
    return "ONC" if c in ("Oncogenic", "Likely Oncogenic") else (
        "BEN" if c in ("Benign", "Likely Benign") else "VUS")


def main():
    ap = argparse.ArgumentParser(description="Horak sensitivity dial")
    ap.add_argument("--os1", default=os.path.join(BENCH, "horak_clinvar_os1.json"),
                    help="OS1 lookup JSON (default: the committed ClinVar snapshot lookup)")
    ap.add_argument("--out", default=os.path.join(BENCH, "horak_sensitivity_modes.json"))
    ap.add_argument("--config", default=PRIMARY_CONFIG, choices=sorted(CONFIGS),
                    help="base engine configuration the dial is applied on (default sop_strict)")
    args = ap.parse_args()
    bench = pd.read_csv(os.path.join(BENCH, "horak_benchmark.tsv"), sep="\t")
    civ = pd.read_csv(os.path.join(BENCH, "horak_civic.tsv"), sep="\t")
    am = json.load(open(os.path.join(ROOT, "data/knowledge/alphamissense/vep_cache.json")))
    domains = json.load(open(os.path.join(ROOT, "data/knowledge/domains/uniprot_domains.json")))
    gnomad = json.load(open(os.path.join(BENCH, "horak_gnomad.json")))
    fdir = os.path.join(ROOT, "data/knowledge/functional")
    cfg = CONFIGS[args.config]
    dms = load_dms_lof(cfg.dms_inputs)          # v2 family: + pre-registered MaveDB sets
    dms_neu = json.load(open(os.path.join(fdir, "dms_neutral.json")))
    os1_path = args.os1
    os1 = json.load(open(os1_path)) if os.path.exists(os1_path) else {}
    os1 = {k: v for k, v in os1.items() if not k.startswith("_")}  # drop provenance

    civ_by = defaultdict(list)
    civ_rows = ([r for _, r in civ.iterrows()] if cfg.civic_inputs == "v1"
                else load_civic_rows("v2"))
    for r in civ_rows:
        civ_by[str(r["molecular_profile"]).split()[0]].append(r)
    v2in = V2InputProvider(cfg)

    def civic(gene, ref, pos, alt):
        # exact variant + SOP mapping (functional evidence only), shared with run_horak_vicc
        return civic_signal_from_rows(civ_by.get(gene, []), gene, ref, pos, alt)

    def am_path(row):
        e = am.get(f"{row['b37_chr']}:{row['b37_pos']}:{row['b37_ref']}>{row['b37_alt']}")
        return e.get("am_pathogenicity") if e else None

    def evaluate(residue_hotspot, use_os1):
        clf = VICCPointClassifier(residue_hotspot=residue_hotspot, config=args.config)
        g3, p3 = [], []
        for _, row in bench.iterrows():
            gene, aa, gold = row["gene"], row["aa"], row["oncogenicity"]
            pp = parse_protein_change(aa)
            civ_sig = civic(gene, pp[0], pp[1], pp[2]) if pp else None
            gkey = f"{row['b37_chr']} {row['b37_pos']} . {row['b37_ref']} {row['b37_alt']} . . ."
            vkey = f"{pp[0]}{pp[1]}{pp[2]}" if pp else ""
            ko = use_os1 and os1.get(f"{gene}|{aa.replace('p.', '')}", {}).get("oncogenic", False)
            res = clf.score(gene, aa, am_pathogenicity=am_path(row), civic=civ_sig,
                            in_domain=(domain_feature_at(domains, gene, pp[1],
                                                         clf.config.om1_scope) if pp else None),
                            gnomad_af=gnomad.get(gkey),
                            functional_lof=bool(pp and dms.get(gene, {}).get(vkey)),
                            functional_neutral=bool(pp and dms_neu.get(gene, {}).get(vkey)),
                            known_oncogenic=ko,
                            **v2in.kwargs(gene, aa, row["b38_chr"], row["b38_pos"],
                                          row["b38_ref"], row["b38_alt"]))
            g3.append(collapse(gold))
            p3.append(collapse(res.oncogenicity.value))
        n = len(g3)
        acc = sum(a == b for a, b in zip(g3, p3)) / n
        tp = sum(1 for a, b in zip(g3, p3) if a == "ONC" and b == "ONC")
        fn = sum(1 for a, b in zip(g3, p3) if a == "ONC" and b != "ONC")
        tn = sum(1 for a, b in zip(g3, p3) if a != "ONC" and b != "ONC")
        fp = sum(1 for a, b in zip(g3, p3) if a != "ONC" and b == "ONC")
        # Percentile bootstrap 95% CIs (src.eval.stats.bootstrap_ci, 5,000 draws, seed 0).
        correct = [float(a == b) for a, b in zip(g3, p3)]
        sens_o = [float(b == "ONC") for a, b in zip(g3, p3) if a == "ONC"]
        spec_o = [float(b != "ONC") for a, b in zip(g3, p3) if a != "ONC"]
        ci = {k: {"lo": c["lo"], "hi": c["hi"], "n": c["n"]} for k, c in
              (("accuracy_3class", bootstrap_ci(correct)), ("sensitivity", bootstrap_ci(sens_o)),
               ("specificity", bootstrap_ci(spec_o)))}
        return {"accuracy_3class": round(acc, 3), "sensitivity": round(tp / (tp + fn), 3),
                "specificity": round(tn / (tn + fp), 3), "ci95": ci,
                "confusion_onc_vs_rest": {"tp": tp, "fn": fn, "tn": tn, "fp": fp},
                # Wilson + Clopper-Pearson; do not collapse at 0 or 1 (peer review P1-3)
                "exact_ci95": {"sensitivity": boundary_ci(tp, tp + fn),
                               "specificity": boundary_ci(tn, tn + fp)}}

    base = "SOP-strict" if args.config == "sop_strict" else args.config
    modes = [
        (f"1. {base} (default)" if args.config == "sop_strict" else "1. conservative (default)",
         False, False),
        ("2. + residue-total hotspot tiering (non-SOP)" if args.config == "sop_strict"
         else "2. + residue-hotspot OM3", True, False),
        ("3. + OS1 (ClinVar)", False, True),
        ("4. + both", True, True),
    ]
    report = {}   # keys are mode labels only (make_figures reads them in order)
    print(f"[+] Sensitivity dial on Horak (n=70). OncoVI reference: sens 0.909 / spec 0.806 / acc 0.797")
    print(f"    {'mode':30s}{'acc3':>8s}{'sens':>8s}{'spec':>8s}")
    for label, rh, os1_on in modes:
        if os1_on and not os1:
            print(f"    {label:30s}  (skipped — run scripts.fetch_horak_clinvar first)")
            continue
        m = evaluate(rh, os1_on)
        report[label] = m
        print(f"    {label:30s}{m['accuracy_3class']:>8}{m['sensitivity']:>8}{m['specificity']:>8}")
    tmp = args.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(report, f, indent=2)
    os.replace(tmp, args.out)


if __name__ == "__main__":
    main()
