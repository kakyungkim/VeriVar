#!/usr/bin/env python3
"""ClinVar somatic-oncogenicity status for the Horak variants -> VICC OS1 evidence.

VICC **OS1** ("same amino-acid change as a previously established oncogenic variant") is the
criterion OncoVI fires via OncoKB and the single largest source of its sensitivity edge over
our abstention-first engine. We source the same signal from an INDEPENDENT, free, citable
database: a variant carries OS1 here iff ClinVar classifies that EXACT substitution (same gene,
same protein change) as Oncogenic / Likely oncogenic under its somatic Oncogenicity
Classification. Uncertain / benign / conflicting oncogenicity labels never grant OS1.

IMPORTANT — disclosed circularity: OS1 uses one expert oncogenicity call to support another,
so on an oncogenicity benchmark it is only *partially* independent (the same caveat applies to
OncoVI's OncoKB-based OS1). It is therefore wired as an OPTIONAL lever, off by default, so the
headline engine stays maximally non-circular; this script + flag exist to quantify the
sensitivity that the guideline-sanctioned OS1 criterion can recover.

Sources (2026-09-24 fix):
  * default (offline): the committed ClinVar FTP snapshot
    ``data/benchmark/clinvar_onc/clinvar_oncogenicity_missense_grch38.tsv`` (built by
    ``scripts/fetch_clinvar_oncogenicity.py`` from ``variant_summary.txt.gz``; aggregate
    ``Oncogenicity`` column, criteria-provided review status, GRCh38 missense SNVs).
  * ``--online``: NCBI E-utilities (esearch + esummary). The original implementation took the
    first esummary record with an oncogenic label WITHOUT checking that the record's protein
    change equalled the query, so PIK3CA p.H1047Q inherited VCV000013652 (p.H1047R,
    Oncogenic); ClinVar lists H1047Q (VCV003765059) as Uncertain significance. Both paths now
    require an exact gene + protein-change match (one/three-letter HGVS normalised).

Writes data/benchmark/horak_clinvar_os1.json =
    {"GENE|AA1": {"oncogenic": bool, "vcv": id|None, "label": str|None}, "_provenance": {...}}

Usage:  python -m scripts.fetch_horak_clinvar            # offline, from the FTP snapshot
        python -m scripts.fetch_horak_clinvar --online   # E-utilities (network)
"""
import argparse
import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Iterable, Optional

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
SNAPSHOT = os.path.join(BENCH, "clinvar_onc", "clinvar_oncogenicity_missense_grch38.tsv")
EUT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_AA1TO3 = {"A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys", "Q": "Gln",
           "E": "Glu", "G": "Gly", "H": "His", "I": "Ile", "L": "Leu", "K": "Lys",
           "M": "Met", "F": "Phe", "P": "Pro", "S": "Ser", "T": "Thr", "W": "Trp",
           "Y": "Tyr", "V": "Val", "*": "Ter"}
_AA3TO1 = {v.upper(): k for k, v in _AA1TO3.items()}
_AA3TO1["X"] = "*"
_P3 = re.compile(r"^([A-Za-z]{3})(\d+)([A-Za-z]{3})$")
_P1 = re.compile(r"^([A-Z\*])(\d+)([A-Z\*])$")
_P3_IN_TEXT = re.compile(r"\(p\.([A-Z][a-z]{2}\d+[A-Z][a-z]{2})\)")


def _get(url):
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as f:
                return json.load(f)
        except Exception:
            time.sleep(1)
    return {}


def norm_protein(hgvs: Optional[str]) -> Optional[str]:
    """Normalise a missense protein change to one-letter form without the ``p.`` prefix.

    Accepts ``p.H1047Q``, ``H1047Q``, ``p.His1047Gln``, ``His1047Gln`` (case-insensitive for
    three-letter codes) and returns ``H1047Q``; returns None for anything unparseable.
    """
    if not hgvs:
        return None
    s = str(hgvs).strip().strip("()")
    if s.startswith("p."):
        s = s[2:]
    s = s.strip("()")
    m = _P1.match(s)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    m = _P3.match(s)
    if m:
        r, a = _AA3TO1.get(m.group(1).upper()), _AA3TO1.get(m.group(3).upper())
        if r and a:
            return f"{r}{m.group(2)}{a}"
    return None


def aa3(aa1):
    """'H1047Q' / 'p.H1047Q' -> 'p.His1047Gln' (None if unparseable)."""
    n = norm_protein(aa1)
    m = _P1.match(n or "")
    if not m:
        return None
    return f"p.{_AA1TO3[m.group(1)]}{m.group(2)}{_AA1TO3[m.group(3)]}"


def is_positive(label: Optional[str]) -> bool:
    """Only Oncogenic / Likely oncogenic grant OS1 (not VUS, benign, conflicting)."""
    return (label or "").strip().lower() in {"oncogenic", "likely oncogenic"}


def fmt_vcv(vid) -> Optional[str]:
    """ClinVar variation id -> 'VCV000013652'."""
    try:
        return f"VCV{int(vid):09d}"
    except (TypeError, ValueError):
        return str(vid) if vid else None


def match_records(gene: str, aa1: str, records: Iterable[dict]) -> dict:
    """Pick the OS1 status for (gene, aa1) from candidate records with an exact match.

    Each record is ``{"gene": str, "protein": str (any HGVS form), "label": str, "vcv": ...}``.
    Records whose gene or normalised protein change differ from the query are ignored — this
    is the guard whose absence let PIK3CA H1047Q inherit H1047R's label.
    """
    q = norm_protein(aa1)
    hits = [r for r in records
            if q and r.get("gene") == gene and norm_protein(r.get("protein")) == q]
    if not hits:
        return {"oncogenic": False, "vcv": None, "label": None}
    pos = [r for r in hits if is_positive(r.get("label"))]
    best = pos[0] if pos else hits[0]
    return {"oncogenic": bool(pos), "vcv": fmt_vcv(best.get("vcv")), "label": best.get("label")}


def snapshot_records(path: str = SNAPSHOT) -> list:
    """Candidate records from the committed ClinVar FTP oncogenicity snapshot."""
    t = pd.read_csv(path, sep="\t", dtype=str)
    return [{"gene": r.gene, "protein": r.aa, "label": r.oncogenicity, "vcv": r.variation_id}
            for r in t.itertuples()]


def esummary_records(gene: str, aa1: str) -> list:
    """Candidate records from E-utilities, with the protein change taken from each record."""
    hp = aa3(aa1)
    if not hp:
        return []
    term = urllib.parse.quote(f'{gene}[gene] AND {hp}')
    ids = _get(f"{EUT}/esearch.fcgi?db=clinvar&term={term}&retmax=20&retmode=json") \
        .get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    res = _get(f"{EUT}/esummary.fcgi?db=clinvar&id={','.join(ids)}&retmode=json").get("result", {})
    out = []
    for uid in res.get("uids", []):
        r = res.get(uid, {})
        genes = {g.get("symbol") for g in (r.get("genes") or [])}
        if gene not in genes:
            continue
        m = _P3_IN_TEXT.search(r.get("title", "") or "")
        if not m:
            continue
        onc = (r.get("oncogenicity_classification") or {}).get("description", "") or ""
        out.append({"gene": gene, "protein": m.group(1), "label": onc,
                    "vcv": r.get("accession") or uid})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--online", action="store_true", help="query E-utilities instead of the snapshot")
    args = ap.parse_args()
    bench = pd.read_csv(os.path.join(BENCH, "horak_benchmark.tsv"), sep="\t")
    snap = None if args.online else snapshot_records()
    out = {}
    n_onc = 0
    for _, row in bench.iterrows():
        gene = row["gene"]
        aa1 = str(row["aa"]).replace("p.", "")
        if args.online:
            recs = esummary_records(gene, aa1)
            time.sleep(0.34)
        else:
            recs = snap
        rec = match_records(gene, aa1, recs)
        out[f"{gene}|{aa1}"] = rec
        n_onc += int(rec["oncogenic"])
    src = "NCBI E-utilities esummary (exact gene + protein-change match)" if args.online else \
        os.path.relpath(SNAPSHOT, ROOT) + " (ClinVar FTP variant_summary, aggregate Oncogenicity)"
    out["_provenance"] = {
        "source": src,
        "rule": "OS1 iff exact gene + protein-change match labelled Oncogenic/Likely oncogenic",
        "n_variants": len(bench), "n_os1": n_onc,
        "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = os.path.join(BENCH, "horak_clinvar_os1.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=2)
    os.replace(tmp, path)
    print(f"[+] ClinVar OS1 lookup for {len(bench)} Horak variants -> {n_onc} flagged oncogenic")
    print(f"    source: {src}")
    print(f"    wrote {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
