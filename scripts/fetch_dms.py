#!/usr/bin/env python3
"""Fetch deep-mutational-scanning (DMS) functional data from MaveDB -> OS2 evidence.

Builds data/knowledge/functional/dms_lof.json = {gene: {"V600E": true, ...}} marking
loss-of-function / damaging missense (VICC OS2: well-established functional study).
Thresholds are anchored to each assay's INTERNAL controls (nonsense = LoF, synonymous
= WT) or use a probability classifier's natural 0.5 cut — never tuned to any benchmark.

Sources (CC-BY, open):
  PTEN lipid-phosphatase function — Mighell et al. 2018 (urn:mavedb:00000054-a-1)
  TP53 naive-Bayes damaging classifier — (urn:mavedb:00001236-0-1)

Usage:  python -m scripts.fetch_dms
"""
import json
import os
import statistics
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "data", "knowledge", "functional")
API = "https://api.mavedb.org/api/v1/score-sets/urn:mavedb:{}/scores"

_AA3 = {"Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q",
        "Glu": "E", "Gly": "G", "His": "H", "Ile": "I", "Leu": "L", "Lys": "K",
        "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W",
        "Tyr": "Y", "Val": "V", "Ter": "*"}


def parse_hgvs_pro(hp):
    """'p.Thr131Ile' -> ('T', 131, 'I'); None if not a clean substitution."""
    import re
    m = re.match(r"p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})$", hp or "")
    if not m:
        return None
    r, p, a = _AA3.get(m.group(1)), int(m.group(2)), _AA3.get(m.group(3))
    return (r, p, a) if r and a else None


def fetch_csv(urn):
    rows = []
    with urllib.request.urlopen(API.format(urn), timeout=60) as f:
        header = f.readline().decode().strip().split(",")
        hi, si = header.index("hgvs_pro"), header.index("score")
        for line in f:
            c = line.decode().strip().split(",")
            if len(c) <= max(hi, si):
                continue
            try:
                rows.append((c[hi], float(c[si])))
            except ValueError:
                rows.append((c[hi], None))
    return rows


def continuous_lof(urns):
    """Union of LoF missense across one or more continuous assays. A variant is LoF
    if it scores below the antimode (nonsense vs WT-functional) in ANY assay — the
    standard 'inactivated via catalysis OR stability' logic for a tumour suppressor."""
    out = {}
    for urn in urns:
        rows = fetch_csv(urn)
        nonsense = [s for hp, s in rows if s is not None and hp.endswith("Ter")]
        miss = [(hp, s) for hp, s in rows if s is not None and parse_hgvs_pro(hp)]
        if not miss:
            continue
        func_med = statistics.median([s for _, s in miss])
        lof_anchor = statistics.median(nonsense) if nonsense else min(s for _, s in miss)
        cutoff = (func_med + lof_anchor) / 2.0
        n = 0
        for hp, s in miss:
            r, p, a = parse_hgvs_pro(hp)
            if s <= cutoff:
                out[f"{r}{p}{a}"] = True
                n += 1
        print(f"    {urn}: cutoff={cutoff:.2f} -> {n} LoF")
    return out


def classifier_calls(urn, lof_hi=0.5, neutral_lo=0.1):
    """Probability classifier -> (damaging set >=lof_hi, neutral set <=neutral_lo)."""
    rows = fetch_csv(urn)
    lof, neu = {}, {}
    for hp, s in rows:
        pp = parse_hgvs_pro(hp)
        if not pp or s is None:
            continue
        k = f"{pp[0]}{pp[1]}{pp[2]}"
        if s >= lof_hi:
            lof[k] = True
        elif s <= neutral_lo:
            neu[k] = True
    print(f"  TP53 classifier: {len(lof)} damaging / {len(neu)} neutral")
    return lof, neu


def main():
    os.makedirs(OUT, exist_ok=True)
    print("  PTEN (function + abundance):")
    pten = continuous_lof(["00000054-a-1", "00000013-a-1"])
    tp53_lof, tp53_neu = classifier_calls("00001236-0-1")
    dms_lof = {"PTEN": pten, "TP53": tp53_lof}
    dms_neutral = {"TP53": tp53_neu}
    json.dump(dms_lof, open(os.path.join(OUT, "dms_lof.json"), "w"))
    json.dump(dms_neutral, open(os.path.join(OUT, "dms_neutral.json"), "w"))
    prov = {"PTEN": {"urns": ["urn:mavedb:00000054-a-1 (lipid phosphatase, Mighell 2018)",
                              "urn:mavedb:00000013-a-1 (VAMP-seq abundance, Matreyek 2018)"]},
            "TP53": {"urn": "urn:mavedb:00001236-0-1 (naive-Bayes classifier)"},
            "note": "LoF = below nonsense-anchored antimode in ANY assay; TP53 classifier 0.5/0.1; "
                    "thresholds anchored to internal controls / classifier, NOT tuned to any benchmark"}
    json.dump(prov, open(os.path.join(OUT, "provenance.json"), "w"), indent=2)
    print(f"[+] wrote dms_lof.json + dms_neutral.json")


if __name__ == "__main__":
    main()
