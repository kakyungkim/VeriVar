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
import json
import os
from collections import defaultdict

import pandas as pd

from src.classify.vicc_rules import VICCPointClassifier, parse_protein_change

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
_BEN = {"unaltered function", "benign", "likely benign", "negative"}
_RANK = {"A": 3, "B": 2, "C": 1, "D": 0}
_RK = ("dna", "bind", "pocket", "kinase", "catalyt", "phosphatase", "set", "tensin")


def collapse(c):
    return "ONC" if c in ("Oncogenic", "Likely Oncogenic") else (
        "BEN" if c in ("Benign", "Likely Benign") else "VUS")


def main():
    bench = pd.read_csv(os.path.join(BENCH, "horak_benchmark.tsv"), sep="\t")
    civ = pd.read_csv(os.path.join(BENCH, "horak_civic.tsv"), sep="\t")
    am = json.load(open(os.path.join(ROOT, "data/knowledge/alphamissense/vep_cache.json")))
    domains = json.load(open(os.path.join(ROOT, "data/knowledge/domains/uniprot_domains.json")))
    gnomad = json.load(open(os.path.join(BENCH, "horak_gnomad.json")))
    fdir = os.path.join(ROOT, "data/knowledge/functional")
    dms = json.load(open(os.path.join(fdir, "dms_lof.json")))
    dms_neu = json.load(open(os.path.join(fdir, "dms_neutral.json")))
    os1_path = os.path.join(BENCH, "horak_clinvar_os1.json")
    os1 = json.load(open(os1_path)) if os.path.exists(os1_path) else {}

    civ_by = defaultdict(list)
    for _, r in civ.iterrows():
        civ_by[str(r["molecular_profile"]).split()[0]].append(r)

    def domain_at(gene, pos):
        for s, e, t, desc in domains.get(gene, []):
            if s <= pos <= e and (t in ("Domain", "Active site", "Binding site")
                                  or (t == "Region" and any(k in (desc or "").lower() for k in _RK))):
                return desc or t
        return None

    def civic(gene, ref, pos, alt):
        onco = ben = 0
        best = None
        exact = f"{gene} {ref}{pos}{alt}"
        for r in civ_by.get(gene, []):
            mp = str(r["molecular_profile"])
            if not (mp.startswith(exact) and (len(mp) == len(exact) or not mp[len(exact)].isalnum())):
                continue
            s = str(r["significance"]).lower()
            d = str(r["evidence_direction"]).lower()
            if s in _BEN:
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

    def evaluate(residue_hotspot, use_os1):
        clf = VICCPointClassifier(residue_hotspot=residue_hotspot)
        g3, p3 = [], []
        for _, row in bench.iterrows():
            gene, aa, gold = row["gene"], row["aa"], row["oncogenicity"]
            pp = parse_protein_change(aa)
            onco = ben = 0
            best = None
            if pp:
                onco, ben, best = civic(gene, pp[0], pp[1], pp[2])
            gkey = f"{row['b37_chr']} {row['b37_pos']} . {row['b37_ref']} {row['b37_alt']} . . ."
            vkey = f"{pp[0]}{pp[1]}{pp[2]}" if pp else ""
            ko = use_os1 and os1.get(f"{gene}|{aa.replace('p.', '')}", {}).get("oncogenic", False)
            res = clf.score(gene, aa, am_pathogenicity=am_path(row), civic_onco=onco,
                            civic_benign=ben, civic_best_level=best,
                            in_domain=domain_at(gene, pp[1]) if pp else None,
                            gnomad_af=gnomad.get(gkey),
                            functional_lof=bool(pp and dms.get(gene, {}).get(vkey)),
                            functional_neutral=bool(pp and dms_neu.get(gene, {}).get(vkey)),
                            known_oncogenic=ko)
            g3.append(collapse(gold))
            p3.append(collapse(res.oncogenicity.value))
        n = len(g3)
        acc = sum(a == b for a, b in zip(g3, p3)) / n
        tp = sum(1 for a, b in zip(g3, p3) if a == "ONC" and b == "ONC")
        fn = sum(1 for a, b in zip(g3, p3) if a == "ONC" and b != "ONC")
        tn = sum(1 for a, b in zip(g3, p3) if a != "ONC" and b != "ONC")
        fp = sum(1 for a, b in zip(g3, p3) if a != "ONC" and b == "ONC")
        return {"accuracy_3class": round(acc, 3), "sensitivity": round(tp / (tp + fn), 3),
                "specificity": round(tn / (tn + fp), 3)}

    modes = [
        ("1. conservative (default)", False, False),
        ("2. + residue-hotspot OM3", True, False),
        ("3. + OS1 (ClinVar)", False, True),
        ("4. + both", True, True),
    ]
    report = {}
    print(f"[+] Sensitivity dial on Horak (n=70). OncoVI reference: sens 0.909 / spec 0.806 / acc 0.797")
    print(f"    {'mode':30s}{'acc3':>8s}{'sens':>8s}{'spec':>8s}")
    for label, rh, os1_on in modes:
        if os1_on and not os1:
            print(f"    {label:30s}  (skipped — run scripts.fetch_horak_clinvar first)")
            continue
        m = evaluate(rh, os1_on)
        report[label] = m
        print(f"    {label:30s}{m['accuracy_3class']:>8}{m['sensitivity']:>8}{m['specificity']:>8}")
    json.dump(report, open(os.path.join(BENCH, "horak_sensitivity_modes.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
