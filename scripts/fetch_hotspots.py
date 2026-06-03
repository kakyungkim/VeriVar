#!/usr/bin/env python3
"""Fetch cancerhotspots.org SNV hotspots → committed JSON for the VICC rule arm.

Builds data/knowledge/hotspots/cancerhotspots.json = {gene: {position: {altAA: count}}}
used by src.classify.vicc_rules for the OS3/OM3/OP3 hotspot criteria. This is an
INDEPENDENT statistical-hotspot source (MSK cancerhotspots v2); we never read the
Horak gold SOP codes, so the rule arm is not fit to the benchmark.

Usage:  python -m scripts.fetch_hotspots
"""
import json
import os
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "data", "knowledge", "hotspots")
URL = "https://www.cancerhotspots.org/files/hotspots_v2.xls"


def main():
    os.makedirs(OUT, exist_ok=True)
    xls = os.path.join(OUT, "hotspots_v2.xls")
    if not os.path.exists(xls):
        print(f"[*] downloading {URL}")
        urllib.request.urlretrieve(URL, xls)
    import pandas as pd
    df = pd.read_excel(xls, sheet_name="SNV-hotspots")
    hot = {}
    for _, r in df.iterrows():
        gene = str(r["Hugo_Symbol"])
        try:
            pos = int(r["Amino_Acid_Position"])
        except (ValueError, TypeError):
            continue
        d = hot.setdefault(gene, {}).setdefault(pos, {})
        for tok in str(r["Variant_Amino_Acid"]).split("|"):   # "Y:84|H:12"
            if ":" in tok:
                aa, _, c = tok.partition(":")
                try:
                    d[aa.strip()] = d.get(aa.strip(), 0) + int(c)
                except ValueError:
                    pass
    path = os.path.join(OUT, "cancerhotspots.json")
    json.dump(hot, open(path, "w"))
    prov = {"source": "cancerhotspots.org v2 (MSK)", "url": URL,
            "sheet": "SNV-hotspots", "n_genes": len(hot)}
    json.dump(prov, open(os.path.join(OUT, "provenance.json"), "w"), indent=2)
    print(f"[+] wrote {path}  ({len(hot)} genes)")


if __name__ == "__main__":
    main()
