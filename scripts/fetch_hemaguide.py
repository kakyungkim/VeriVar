#!/usr/bin/env python3
"""Fetch HemaGuide Supplementary Table 6 and extract it to a committed CSV.

HemaGuide (Zoller et al., Nat Med 2026;32(9):3224-3234, doi:10.1038/s41591-026-04494-4,
PMC13577921) benchmarked its molecular mode (a point-based ClinGen/CGC/VICC engine) on the
same 70 Horak 2022 missense variants that VeriVar uses. Its Supplementary Table 6 lists, per
variant, the Horak reference call (3-bin decision, points, codes) and HemaGuide's own call.

The article is CC BY 4.0, so the extracted 70 rows are committed as
``data/benchmark/hemaguide/hemaguide_st6.csv`` (see the README beside it). This script is
the only step that touches the network (repo convention: network only in ``scripts/fetch_*``);
``scripts/run_hemaguide_headtohead.py`` reads the committed CSV offline.

The workbook is parsed with the standard library (zipfile + ElementTree) so no ``openpyxl``
dependency is needed. Values are copied verbatim; nothing is recoded here.

Usage:
    python -m scripts.fetch_hemaguide                    # download + extract
    python -m scripts.fetch_hemaguide --xlsx PATH.xlsx   # extract from a local copy
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, List

ESM_URL = ("https://static-content.springer.com/esm/art%3A10.1038%2Fs41591-026-04494-4/"
           "MediaObjects/41591_2026_4494_MOESM4_ESM.xlsx")
SHEET = "Supplementary Table 6"
EXPECTED_HEADER = ["ID", "Gene", "CDS_position", "AA_change", "Horak_2022_decision",
                   "Horak_2022_points", "Horak_2022_codes", "Hemaguide_decision",
                   "HemaGuide_points", "HemaGuide_codes"]
EXPECTED_ROWS = 70

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(ROOT, "data", "benchmark", "hemaguide")
RAW_XLSX = os.path.join(OUT_DIR, "raw", "41591_2026_4494_MOESM4_ESM.xlsx")  # gitignored
OUT_CSV = os.path.join(OUT_DIR, "hemaguide_st6.csv")

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


def _col_index(ref: str) -> int:
    """'C12' -> 2 (zero-based column index)."""
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_sheet(xlsx_path: str, sheet_name: str) -> List[List[str]]:
    """Return a sheet as a list of rows (strings), using only the standard library."""
    with zipfile.ZipFile(xlsx_path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rid_to_target = {r.get("Id"): r.get("Target")
                         for r in rels.findall("rel:Relationship", _NS)}
        target = None
        for s in wb.find("m:sheets", _NS):
            if s.get("name") == sheet_name:
                target = rid_to_target[s.get(f"{{{_NS['r']}}}id")]
        if target is None:
            raise KeyError(f"sheet {sheet_name!r} not found in {xlsx_path}")
        target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        shared: List[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in sst.findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        sheet = ET.fromstring(z.read(target))
    rows: List[List[str]] = []
    for row in sheet.iter(f"{{{_NS['m']}}}row"):
        cells: Dict[int, str] = {}
        for c in row.findall("m:c", _NS):
            t = c.get("t")
            v = c.find("m:v", _NS)
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(f"{{{_NS['m']}}}t"))
            else:
                val = v.text if v is not None and v.text is not None else ""
            cells[_col_index(c.get("r"))] = val
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(width)])
    return rows


def _num(s: str) -> str:
    """Render numeric cells as ints when integral ('10.0' -> '10'); keep text verbatim."""
    try:
        f = float(s)
    except ValueError:
        return s.strip()
    return str(int(f)) if f.is_integer() else str(f)


def extract(xlsx_path: str, out_csv: str = OUT_CSV) -> List[Dict[str, str]]:
    """Extract Supplementary Table 6 to CSV; validate header and row count."""
    rows = read_sheet(xlsx_path, SHEET)
    header = [h.strip() for h in rows[0][:len(EXPECTED_HEADER)]]
    if header != EXPECTED_HEADER:
        raise ValueError(f"unexpected ST6 header: {header}")
    records = []
    for r in rows[1:]:
        r = (r + [""] * len(EXPECTED_HEADER))[:len(EXPECTED_HEADER)]
        if not any(x.strip() for x in r):
            continue
        rec = dict(zip(EXPECTED_HEADER, (x.strip() for x in r)))
        for k in ("ID", "Horak_2022_points", "HemaGuide_points"):
            rec[k] = _num(rec[k])
        records.append(rec)
    if len(records) != EXPECTED_ROWS:
        raise ValueError(f"expected {EXPECTED_ROWS} ST6 rows, got {len(records)}")
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    tmp = out_csv + ".tmp"
    with open(tmp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=EXPECTED_HEADER)
        w.writeheader()
        w.writerows(records)
    os.replace(tmp, out_csv)
    return records


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--xlsx", help="local copy of MOESM4_ESM.xlsx (skip download)")
    args = ap.parse_args(argv)
    path = args.xlsx
    if not path:
        os.makedirs(os.path.dirname(RAW_XLSX), exist_ok=True)
        print(f"[*] downloading {ESM_URL}")
        urllib.request.urlretrieve(ESM_URL, RAW_XLSX)
        path = RAW_XLSX
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    recs = extract(path)
    print(f"[+] {len(recs)} rows from {SHEET!r} (xlsx sha256 {sha}) -> {OUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
