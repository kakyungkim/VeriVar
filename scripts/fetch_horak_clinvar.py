#!/usr/bin/env python3
"""Fetch ClinVar somatic-oncogenicity status for the Horak variants -> VICC OS1 evidence.

VICC **OS1** ("same amino-acid change as a previously established oncogenic variant") is the
criterion OncoVI fires via OncoKB and the single largest source of its sensitivity edge over
our abstention-first engine. We source the same signal from an INDEPENDENT, free, citable
database: a variant carries OS1 here iff ClinVar classifies that exact substitution as
Oncogenic / Likely oncogenic under its somatic Oncogenicity Classification.

IMPORTANT — disclosed circularity: OS1 uses one expert oncogenicity call to support another,
so on an oncogenicity benchmark it is only *partially* independent (the same caveat applies to
OncoVI's OncoKB-based OS1). It is therefore wired as an OPTIONAL lever, off by default, so the
headline engine stays maximally non-circular; this script + flag exist to quantify the
sensitivity that the guideline-sanctioned OS1 criterion can recover.

Writes data/benchmark/horak_clinvar_os1.json = {"GENE|AA1": {"oncogenic": bool, "vcv": id}}.

Usage:  python -m scripts.fetch_horak_clinvar
"""
import json
import os
import time
import urllib.parse
import urllib.request

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
EUT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_AA1TO3 = {"A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys", "Q": "Gln",
           "E": "Glu", "G": "Gly", "H": "His", "I": "Ile", "L": "Leu", "K": "Lys",
           "M": "Met", "F": "Phe", "P": "Pro", "S": "Ser", "T": "Thr", "W": "Trp",
           "Y": "Tyr", "V": "Val", "*": "Ter"}


def _get(url):
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as f:
                return json.load(f)
        except Exception:
            time.sleep(1)
    return {}


def aa3(aa1):
    import re
    m = re.match(r"([A-Z\*])(\d+)([A-Z\*])$", aa1.replace("p.", ""))
    if not m:
        return None
    r, a = _AA1TO3.get(m.group(1)), _AA1TO3.get(m.group(3))
    return f"p.{r}{m.group(2)}{a}" if r and a else None


def lookup(gene, aa1):
    """True iff ClinVar classifies this exact variant as (Likely) oncogenic."""
    hp = aa3(aa1)
    if not hp:
        return {"oncogenic": False, "vcv": None}
    term = urllib.parse.quote(f'{gene}[gene] AND {hp}')
    ids = _get(f"{EUT}/esearch.fcgi?db=clinvar&term={term}&retmax=20&retmode=json") \
        .get("esearchresult", {}).get("idlist", [])
    if not ids:
        return {"oncogenic": False, "vcv": None}
    res = _get(f"{EUT}/esummary.fcgi?db=clinvar&id={','.join(ids)}&retmode=json").get("result", {})
    for uid in res.get("uids", []):
        r = res.get(uid, {})
        onc = (r.get("oncogenicity_classification") or {}).get("description", "") or ""
        if "oncogenic" in onc.lower() and "non-" not in onc.lower():
            return {"oncogenic": True, "vcv": r.get("accession") or uid, "label": onc}
    return {"oncogenic": False, "vcv": None}


def main():
    bench = pd.read_csv(os.path.join(BENCH, "horak_benchmark.tsv"), sep="\t")
    out = {}
    n_onc = 0
    for _, row in bench.iterrows():
        gene = row["gene"]
        aa1 = str(row["aa"]).replace("p.", "")
        rec = lookup(gene, aa1)
        out[f"{gene}|{aa1}"] = rec
        n_onc += int(rec["oncogenic"])
        time.sleep(0.34)
    path = os.path.join(BENCH, "horak_clinvar_os1.json")
    json.dump(out, open(path, "w"), indent=2)
    print(f"[+] ClinVar OS1 lookup for {len(out)} Horak variants -> {n_onc} flagged oncogenic")
    print(f"    wrote {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
