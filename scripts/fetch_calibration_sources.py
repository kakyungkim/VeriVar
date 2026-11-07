#!/usr/bin/env python3
"""Fetch the published predictor calibrations behind the v2 OP1/SBP1 thresholds and check
that the engine constants match them.

Purpose:  the pre-registered sop_strict_v2 thresholds (``PREDICTOR_THRESHOLDS["clingen"]`` in
          ``src/classify/vicc_rules.py``) are the supporting-level boundaries of
          Pejaver et al. AJHG 2022 Table 2 (REVEL, CADD, SIFT, PolyPhen-2) and Bergquist et al.
          Genet Med 2025 Table 1 (AlphaMissense). This script downloads both open-access tables,
          stores their text as a snapshot, and asserts every engine constant appears in the
          corresponding table row.
Prereq:   network (Europe PMC REST for Pejaver PMC9748256; PMC HTML for Bergquist PMC12208618).
Run:      python -m scripts.fetch_calibration_sources
Output:   data/knowledge/calibration/{pejaver2022_table2.txt, bergquist2025_table1.txt,
          provenance.json}; exits non-zero if a constant is not found in its source row.
"""
import datetime as _dt
import hashlib
import html
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from src.classify.vicc_rules import PREDICTOR_THRESHOLDS  # noqa: E402

OUT = os.path.join(ROOT, "data", "knowledge", "calibration")
PEJAVER = "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9748256/fullTextXML"
BERGQUIST = "https://pmc.ncbi.nlm.nih.gov/articles/PMC12208618/"


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
    with urllib.request.urlopen(req, timeout=120) as f:
        return f.read().decode("utf-8", errors="ignore")


def _flat(markup: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", markup, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))


def _row(text: str, tool: str, next_tools) -> str:
    i = text.find(f" {tool} ")
    if i < 0:
        return ""
    ends = [text.find(f" {n} ", i + len(tool) + 2) for n in next_tools]
    ends = [e for e in ends if e > 0]
    return text[i:min(ends) if ends else i + 200]


def _fmt(x: float) -> list:
    """Spellings of a number as printed in the tables (0.290 / 0.29, 25.3)."""
    s = {f"{x:.3f}", f"{x:.2f}", f"{x:.1f}", f"{x:g}"}
    return sorted(s)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    pj = _flat(_get(PEJAVER))
    i = pj.find("Estimated threshold ranges for all tools")
    pj_tab = pj[i:i + 2500]
    bq = _flat(_get(BERGQUIST))
    j = bq.find("Table 1. Estimated threshold intervals")
    bq_tab = bq[j:j + 3000]
    if i < 0 or j < 0:
        print("table not found in source")
        return 1
    for name, txt in (("pejaver2022_table2.txt", pj_tab), ("bergquist2025_table1.txt", bq_tab)):
        with open(os.path.join(OUT, name), "w") as f:
            f.write(txt + "\n")
    tools = ["BayesDel", "CADD", "EA", "FATHMM", "GERP++", "MPC", "MutPred2", "PhyloP",
             "PolyPhen2", "PrimateAI", "REVEL", "SIFT", "VEST4", "AlphaMissense", "ESM1b",
             "VARITY_R", "A “–”"]
    checks = {"revel": ("REVEL", pj_tab), "cadd_phred": ("CADD", pj_tab),
              "sift": ("SIFT", pj_tab), "polyphen": ("PolyPhen2", pj_tab),
              "alphamissense": ("AlphaMissense", bq_tab)}
    results, ok = {}, True
    for key, (tool, tab) in checks.items():
        row = _row(tab, tool, [t for t in tools if t != tool])
        thr = PREDICTOR_THRESHOLDS["clingen"][key]
        found = {v: any(s in row for s in _fmt(v)) for v in (thr.onco, thr.benign)}
        results[key] = {"row": row.strip(), "onco": thr.onco, "benign": thr.benign,
                        "found": {str(k): v for k, v in found.items()}}
        ok &= all(found.values())
        print(f"  {key:14s} onco {thr.onco} benign {thr.benign} -> "
              f"{'OK' if all(found.values()) else 'NOT FOUND'} | {row.strip()[:110]}")
    prov = {"fetched_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "script": "scripts/fetch_calibration_sources.py",
            "sources": {"pejaver2022": {"url": PEJAVER, "doi": "10.1016/j.ajhg.2022.10.013",
                                        "table": "Table 2"},
                        "bergquist2025": {"url": BERGQUIST, "doi": "10.1016/j.gim.2025.101402",
                                          "table": "Table 1"}},
            "sha256": {n: hashlib.sha256(open(os.path.join(OUT, n), "rb").read()).hexdigest()
                       for n in ("pejaver2022_table2.txt", "bergquist2025_table1.txt")},
            "checks": results, "all_constants_found": ok}
    with open(os.path.join(OUT, "provenance.json"), "w") as f:
        json.dump(prov, f, indent=2, ensure_ascii=False)
    print(f"[+] all engine constants found in source rows: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
