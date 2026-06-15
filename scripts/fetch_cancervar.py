#!/usr/bin/env python3
"""Fetch CancerVar's OWN per-variant predictions for the Horak-70 gold variants.

ANTI-FABRICATION: every label written here is parsed verbatim from a live response of
the official CancerVar web server (https://cancervar.wglab.org, WGLab; Li et al.,
Sci. Adv. 2022). We query by genomic coordinate (build hg38/GRCh38, using the Horak
b38 coordinates) and parse CancerVar's emitted verdict (`clnsg=Tier_X` + `c_points=N`)
out of the result HTML. We DO NOT compute or guess any tier ourselves.

CancerVar reports an AMP/ASCO/CAP tier (Tier_I..Tier_IV), not a VICC oncogenicity label;
the scoring script maps tier -> ONC/VUS/BEN for the 3-class head-to-head.

Raw HTML for each variant is saved under data/benchmark/cancervar/raw/ for provenance/audit.

Network access — run only as a fetch step:  python -m scripts.fetch_cancervar
"""
import datetime
import json
import os
import re
import time
import urllib.parse
import urllib.request

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
GOLD = os.path.join(BENCH, "horak_benchmark.tsv")
OUT_DIR = os.path.join(BENCH, "cancervar")
RAW_DIR = os.path.join(OUT_DIR, "raw")
ENDPOINT = "https://cancervar.wglab.org/results_new.php"

# CancerVar build option value for GRCh38 (from the live form <select name="build">).
BUILD = "hg38_update"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")


def query(chrom, pos, ref, alt, build=BUILD, cancer="All_types", timeout=90):
    """POST one variant to the CancerVar server; return (raw_html, status)."""
    chrom = str(chrom).replace("chr", "")
    data = urllib.parse.urlencode({
        "build": build,
        "cancer_types": cancer,
        "queryType": "position",
        "chr": chrom,
        "pos": str(pos),
        "ref": ref,
        "alt": alt,
        ".submit": "",
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=data,
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace"), r.status


def parse_verdict(html):
    """Extract CancerVar's own tier + score from its result HTML.

    Returns dict with raw_tier (e.g. 'Tier_I_strong'), tier (collapsed Tier_I..IV),
    points (int), and parse_ok flag. Returns parse_ok=False if no verdict present.
    """
    # CancerVar embeds e.g. ...&clnsg=Tier_I_strong&c_points=11 in a results link.
    m_tier = re.search(r"clnsg=Tier_([IViv]+)(_strong|_potential)?", html)
    m_pts = re.search(r"c_points=(-?\d+)", html)
    if not m_tier:
        return {"parse_ok": False, "raw_tier": None, "tier": None, "points": None}
    roman = m_tier.group(1).upper()
    suffix = (m_tier.group(2) or "")
    raw_tier = f"Tier_{roman}{suffix}"
    tier = f"Tier_{roman}"
    pts = int(m_pts.group(1)) if m_pts else None
    return {"parse_ok": True, "raw_tier": raw_tier, "tier": tier, "points": pts}


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    gold = pd.read_csv(GOLD, sep="\t")
    rows, n_ok, n_fail = [], 0, 0
    for i, g in gold.iterrows():
        vid = f"{g['gene']}_{g['aa'].replace('p.', '')}"
        chrom, pos = g["b38_chr"], g["b38_pos"]
        ref, alt = g["b38_ref"], g["b38_alt"]
        try:
            html, status = query(chrom, pos, ref, alt)
        except Exception as e:  # noqa: BLE001
            html, status = "", f"ERROR: {e}"
        raw_path = os.path.join(RAW_DIR, f"{vid}.html")
        with open(raw_path, "w") as fh:
            fh.write(html)
        verdict = parse_verdict(html)
        ok = verdict["parse_ok"]
        n_ok += int(ok)
        n_fail += int(not ok)
        rows.append({
            "variant": f"{g['gene']} {g['aa']}",
            "gene": g["gene"],
            "aa": g["aa"],
            "b38": f"chr{str(chrom).replace('chr','')}:{pos}{ref}>{alt}",
            "gold": str(g["oncogenicity"]).strip(),
            "cancervar_raw_tier": verdict["raw_tier"],
            "cancervar_tier": verdict["tier"],
            "cancervar_points": verdict["points"],
            "http_status": status,
            "parse_ok": ok,
            "raw_html": os.path.relpath(raw_path, ROOT),
        })
        print(f"  [{i+1:2d}/{len(gold)}] {vid:18s} -> "
              f"{verdict['raw_tier'] or 'NO-VERDICT'} (status {status})")
        time.sleep(1.5)  # be polite to the public server

    out = {
        "provenance": {
            "tool": "CancerVar (WGLab)",
            "source": "official web server",
            "endpoint": ENDPOINT,
            "citation": ("Li Q, Ren Z, Cao K, Li MM, Zhou Y, Wang K. CancerVar: an "
                         "Artificial Intelligence empowered platform for clinical "
                         "interpretation of somatic mutations in cancer. "
                         "Sci. Adv. 2022;8(18):eabj1624."),
            "build": BUILD + " (GRCh38, Horak b38 coordinates)",
            "cancer_type": "All_types",
            "query_type": "position (chr/pos/ref/alt)",
            "fetched_utc": datetime.datetime.utcnow().isoformat() + "Z",
            "note": ("Tiers parsed verbatim from CancerVar result HTML (clnsg=Tier_X, "
                     "c_points=N). No tier was computed or assigned by this pipeline. "
                     "CancerVar emits AMP/ASCO/CAP tiers, not VICC oncogenicity labels."),
        },
        "n_total": len(rows),
        "n_parsed": n_ok,
        "n_failed": n_fail,
        "rows": rows,
    }
    with open(os.path.join(OUT_DIR, "cancervar_predictions.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\n[+] CancerVar predictions: {n_ok}/{len(rows)} parsed, "
          f"{n_fail} failed -> {OUT_DIR}/cancervar_predictions.json")


if __name__ == "__main__":
    main()
