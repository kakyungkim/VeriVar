#!/usr/bin/env python3
"""Fetch a ClinVar *somatic oncogenicity* missense snapshot (GRCh38) from the ClinVar FTP.

Why this replaces ``scripts/run_clinvar_vicc.py`` as the label source
-------------------------------------------------------------------
The old holdout searched E-utilities with ``"<term>"[Oncogenicity Classification]`` and
took the *query term* as the gold label. That field qualifier only restricts correctly for
"Oncogenic"/"Likely oncogenic"; for "Benign", "Likely benign" and "Uncertain significance"
it matches millions of records (germline classifications), so the old BEN/VUS labels were
mostly germline calls, not oncogenicity calls. Here the label is read directly from the
ClinVar FTP ``variant_summary.txt.gz`` column ``Oncogenicity`` (the aggregate somatic
oncogenicity classification, ClinGen/CGC/VICC 5-tier), and the submitter of every
contributing SCV is read from ``submission_summary.txt.gz`` column ``Oncogenicity``.

What is kept
------------
GRCh38 rows whose aggregate ``Oncogenicity`` is a real classification (not "-" / "no
classification for the single variant"), whose ``ReviewStatusOncogenicity`` starts with
"criteria provided", that are single-nucleotide missense changes (``p.Xxx123Yyy``, not
``Ter``/``=``). For each variant the snapshot also carries AlphaMissense and gnomAD
(exomes/genomes, max) allele frequency from the Ensembl VEP REST API (GRCh38), so the
evaluation (``scripts/run_clinvar_onc_holdout.py``) runs fully offline.

Network access happens ONLY in this script (project convention). ClinVar is public domain
(NCBI); AlphaMissense scores are CC BY 4.0 via Ensembl; gnomAD frequencies are ODbL/CC0
summary statistics via Ensembl.

Outputs (under ``data/benchmark/clinvar_onc/``)
  clinvar_oncogenicity_missense_grch38.tsv   one row per ClinVar VariationID
  vep_annotations.json                      VEP cache (AlphaMissense + gnomAD AF)
  provenance.json                           release dates, md5/sha256, filters, counts

Usage
  python -m scripts.fetch_clinvar_oncogenicity [--raw-dir DIR] [--no-download] [--no-vep]
"""
import argparse
import datetime as _dt
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(ROOT, "data", "benchmark", "clinvar_onc")
TSV_NAME = "clinvar_oncogenicity_missense_grch38.tsv"
FTP = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited"
FILES = ("variant_summary.txt.gz", "submission_summary.txt.gz")
VEP_URL = ("https://rest.ensembl.org/vep/human/region"
           "?AlphaMissense=1&af_gnomade=1&af_gnomadg=1")

_AA3 = {"Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q",
        "Glu": "E", "Gly": "G", "His": "H", "Ile": "I", "Leu": "L", "Lys": "K",
        "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W",
        "Tyr": "Y", "Val": "V"}
_MISSENSE = re.compile(r"\(p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})\)\s*$")
_NAME_GENE = re.compile(r"^[^(]+\(([^)]+)\):")
NO_CLASS = {"", "-", "no classification for the single variant"}

TSV_COLUMNS = [
    "variation_id", "allele_id", "gene", "aa", "name", "chrom", "pos", "ref", "alt",
    "oncogenicity", "onc_class", "onc_last_evaluated", "onc_review_status",
    "n_onc_scvs", "onc_submitters", "onc_scvs", "onc_scv_labels", "onc_scv_dates",
    "germline_clinsig_not_used", "origin", "am_pathogenicity", "am_class", "gnomad_af",
]


# --------------------------------------------------------------------------- parsing
def collapse_oncogenicity(label: str) -> str:
    """ClinVar 5-tier oncogenicity -> collapsed class (ONC / VUS / BEN / CONFLICT)."""
    s = (label or "").strip().lower()
    if s.startswith("conflicting"):
        return "CONFLICT"
    if s in ("oncogenic", "likely oncogenic"):
        return "ONC"
    if s in ("benign", "likely benign"):
        return "BEN"
    if s == "uncertain significance":
        return "VUS"
    return "OTHER"


def parse_missense(name: str, gene_symbol: str = "") -> Optional[Tuple[str, str]]:
    """``'NM_000546.6(TP53):c.818G>A (p.Arg273His)'`` -> ``('TP53', 'p.R273H')``.

    Returns None for non-missense (nonsense ``Ter``, synonymous ``=``, indels)."""
    m = _MISSENSE.search(name or "")
    if not m:
        return None
    ref, alt = _AA3.get(m.group(1)), _AA3.get(m.group(3))
    if not ref or not alt or ref == alt:
        return None
    g = _NAME_GENE.match(name or "")
    gene = g.group(1) if g else (gene_symbol or "").split(";")[0]
    return gene, f"p.{ref}{m.group(2)}{alt}"


def parse_date(s: str) -> str:
    """ClinVar 'Mar 04, 2025' -> '2025-03-04' ('' when absent/unparseable)."""
    try:
        return _dt.datetime.strptime((s or "").strip(), "%b %d, %Y").date().isoformat()
    except ValueError:
        return ""


def parse_variant_summary(lines: Iterable[str]) -> Tuple[List[dict], Counter]:
    """Filter variant_summary rows to GRCh38 missense SNVs with a criteria-provided
    somatic oncogenicity classification. Returns (rows, funnel counts)."""
    funnel: Counter = Counter()
    header: Optional[List[str]] = None
    rows: List[dict] = []
    for line in lines:
        if header is None:
            header = line.lstrip("#").rstrip("\n").split("\t")
            continue
        f = dict(zip(header, line.rstrip("\n").split("\t")))
        if f.get("Assembly") != "GRCh38":
            continue
        onc = f.get("Oncogenicity", "-")
        if onc in NO_CLASS:
            continue
        funnel["grch38_with_oncogenicity_classification"] += 1
        rs = f.get("ReviewStatusOncogenicity", "")
        if not rs.startswith("criteria provided"):
            funnel["dropped_no_assertion_criteria"] += 1
            continue
        funnel["criteria_provided"] += 1
        if f.get("Type") != "single nucleotide variant":
            funnel["dropped_not_snv"] += 1
            continue
        mm = parse_missense(f.get("Name", ""), f.get("GeneSymbol", ""))
        if not mm:
            funnel["dropped_snv_not_missense"] += 1
            continue
        funnel["kept_missense"] += 1
        gene, aa = mm
        rows.append({
            "variation_id": f.get("VariationID", ""),
            "allele_id": f.get("AlleleID", ""),
            "gene": gene, "aa": aa, "name": f.get("Name", ""),
            "chrom": f.get("Chromosome", ""), "pos": f.get("PositionVCF", ""),
            "ref": f.get("ReferenceAlleleVCF", ""), "alt": f.get("AlternateAlleleVCF", ""),
            "oncogenicity": onc, "onc_class": collapse_oncogenicity(onc),
            "onc_last_evaluated": parse_date(f.get("OncogenicityLastEvaluated", "")),
            "onc_review_status": rs,
            "germline_clinsig_not_used": f.get("ClinicalSignificance", ""),
            "origin": f.get("OriginSimple", ""),
        })
    return rows, funnel


def parse_submission_summary(lines: Iterable[str], keep_ids: Optional[set] = None
                             ) -> Dict[str, List[dict]]:
    """VariationID -> list of SCVs that carry a somatic oncogenicity classification."""
    out: Dict[str, List[dict]] = defaultdict(list)
    header: Optional[List[str]] = None
    for line in lines:
        if line.startswith("##"):
            continue
        if line.startswith("#VariationID\t"):
            header = line.lstrip("#").rstrip("\n").split("\t")
            continue
        if header is None or line.startswith("#"):
            continue
        f = dict(zip(header, line.rstrip("\n").split("\t")))
        onc = f.get("Oncogenicity", "-")
        if onc in NO_CLASS:
            continue
        vid = f.get("VariationID", "")
        if keep_ids is not None and vid not in keep_ids:
            continue
        out[vid].append({"scv": f.get("SCV", ""), "submitter": f.get("Submitter", ""),
                         "label": onc, "date": parse_date(f.get("DateLastEvaluated", "")),
                         "review_status": f.get("ReviewStatus", ""),
                         "contributes": f.get("ContributesToAggregateClassification", "")})
    return dict(out)


def attach_scvs(rows: List[dict], scvs: Dict[str, List[dict]]) -> None:
    """Add submitter / SCV columns in place (only SCVs that contribute, if flagged)."""
    for r in rows:
        lst = scvs.get(r["variation_id"], [])
        contrib = [s for s in lst if s["contributes"].lower() == "yes"] or lst
        r["n_onc_scvs"] = len(contrib)
        r["onc_submitters"] = "|".join(s["submitter"] for s in contrib)
        r["onc_scvs"] = "|".join(s["scv"] for s in contrib)
        r["onc_scv_labels"] = "|".join(s["label"] for s in contrib)
        r["onc_scv_dates"] = "|".join(s["date"] for s in contrib)


# --------------------------------------------------------------------------- VEP
def vep_key(chrom: str, pos: str, ref: str, alt: str) -> str:
    return f"{chrom} {pos} . {ref} {alt} . . ."


def parse_vep_record(rec: dict, gene: str) -> dict:
    """Extract max AlphaMissense (transcripts of ``gene``) and max gnomAD AF."""
    alt = rec.get("allele_string", "/").split("/")[-1]
    best = None
    for tc in rec.get("transcript_consequences", []) or []:
        am = tc.get("alphamissense")
        if am and "am_pathogenicity" in am and (tc.get("gene_symbol") in (gene, None)):
            if best is None or am["am_pathogenicity"] > best["am_pathogenicity"]:
                best = {"am_pathogenicity": am["am_pathogenicity"],
                        "am_class": am.get("am_class", "")}
    af = 0.0   # absent from gnomAD -> 0.0 (same convention as horak_gnomad.json)
    for cv in rec.get("colocated_variants", []) or []:
        fr = (cv.get("frequencies") or {}).get(alt) or {}
        for k in ("gnomade", "gnomadg"):
            if k in fr:
                af = max(af, float(fr[k]))
    return {"am_pathogenicity": best["am_pathogenicity"] if best else None,
            "am_class": best["am_class"] if best else "", "gnomad_af": af}


def vep_annotate(rows: List[dict], cache_path: str, batch: int = 150) -> dict:
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    todo = [r for r in rows if vep_key(r["chrom"], r["pos"], r["ref"], r["alt"]) not in cache]
    by_key = {vep_key(r["chrom"], r["pos"], r["ref"], r["alt"]): r["gene"] for r in rows}
    for i in range(0, len(todo), batch):
        keys = [vep_key(r["chrom"], r["pos"], r["ref"], r["alt"]) for r in todo[i:i + batch]]
        body = json.dumps({"variants": keys}).encode()
        data = None
        for attempt in range(4):
            try:
                req = urllib.request.Request(VEP_URL, data=body, headers={
                    "Content-Type": "application/json", "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=180) as f:
                    data = json.load(f)
                break
            except Exception as e:  # noqa: BLE001 - network retry
                print(f"    VEP retry {attempt + 1}: {e}")
                time.sleep(5 * (attempt + 1))
        if data is None:
            raise SystemExit("VEP REST failed repeatedly; rerun later (cache is kept).")
        for rec in data:
            k = rec.get("input")
            if k in by_key:
                cache[k] = parse_vep_record(rec, by_key[k])
        for k in keys:                      # remember misses so we do not refetch
            cache.setdefault(k, {"am_pathogenicity": None, "am_class": "", "gnomad_af": None})
        json.dump(cache, open(cache_path, "w"), indent=1, sort_keys=True)
        print(f"    VEP {min(i + batch, len(todo))}/{len(todo)}")
        time.sleep(1)
    return cache


# --------------------------------------------------------------------------- IO
def _md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _head(url: str) -> dict:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        return {"last_modified": r.headers.get("Last-Modified"),
                "content_length": int(r.headers.get("Content-Length") or 0)}


def ensure_file(name: str, raw_dir: str, download: bool) -> dict:
    """Make sure ``raw_dir/name`` is the current FTP release; return its provenance."""
    url = f"{FTP}/{name}"
    path = os.path.join(raw_dir, name)
    info: dict = {"url": url, "path_local": path}
    remote_md5 = None
    if download:
        info.update(_head(url))
        with urllib.request.urlopen(url + ".md5", timeout=60) as r:
            remote_md5 = r.read().decode().split()[0]
        info["md5_remote"] = remote_md5
        if not (os.path.exists(path) and _md5(path) == remote_md5):
            print(f"[*] downloading {url}")
            tmp = path + ".part"
            with urllib.request.urlopen(url, timeout=600) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(tmp, path)
    if not os.path.exists(path):
        raise SystemExit(f"missing {path}; run without --no-download")
    info["md5_local"] = _md5(path)
    info["sha256_local"] = _sha256(path)
    info["size_bytes"] = os.path.getsize(path)
    if remote_md5 and info["md5_local"] != remote_md5:
        raise SystemExit(f"md5 mismatch for {name}")
    return info


def write_tsv(rows: List[dict], path: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\t".join(TSV_COLUMNS) + "\n")
        for r in rows:
            f.write("\t".join("" if r.get(c) is None else str(r.get(c)).replace("\t", " ")
                              for c in TSV_COLUMNS) + "\n")
    os.replace(tmp, path)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--raw-dir", default=os.path.join(ROOT, "data", "raw", "clinvar"),
                    help="where the large FTP files live (git-ignored)")
    ap.add_argument("--no-download", action="store_true",
                    help="use files already in --raw-dir (skip HEAD/md5 check)")
    ap.add_argument("--no-vep", action="store_true", help="skip the VEP annotation step")
    args = ap.parse_args(argv)
    os.makedirs(args.raw_dir, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    files = {n: ensure_file(n, args.raw_dir, not args.no_download) for n in FILES}

    print("[*] parsing variant_summary")
    with gzip.open(files["variant_summary.txt.gz"]["path_local"], "rt",
                   encoding="utf-8", errors="replace") as fh:
        rows, funnel = parse_variant_summary(fh)
    ids = {r["variation_id"] for r in rows}
    print(f"    kept {len(rows)} missense rows; funnel {dict(funnel)}")

    print("[*] parsing submission_summary (SCV-level oncogenicity + submitter)")
    with gzip.open(files["submission_summary.txt.gz"]["path_local"], "rt",
                   encoding="utf-8", errors="replace") as fh:
        scvs_all = parse_submission_summary(fh)
    all_scv = [s for lst in scvs_all.values() for s in lst]
    attach_scvs(rows, {k: v for k, v in scvs_all.items() if k in ids})

    vep_meta = {"skipped": True}
    if not args.no_vep:
        print("[*] VEP REST (GRCh38): AlphaMissense + gnomAD AF")
        cache = vep_annotate(rows, os.path.join(OUT_DIR, "vep_annotations.json"))
        for r in rows:
            a = cache.get(vep_key(r["chrom"], r["pos"], r["ref"], r["alt"]), {})
            r["am_pathogenicity"] = a.get("am_pathogenicity")
            r["am_class"] = a.get("am_class", "")
            r["gnomad_af"] = a.get("gnomad_af")
        try:
            with urllib.request.urlopen("https://rest.ensembl.org/info/data?content-type="
                                        "application/json", timeout=30) as f:
                rel = json.load(f).get("releases")
        except Exception:  # noqa: BLE001
            rel = None
        vep_meta = {"skipped": False, "endpoint": VEP_URL, "ensembl_release": rel,
                    "n_with_alphamissense": sum(r.get("am_pathogenicity") is not None
                                                for r in rows),
                    "n_with_gnomad_af_gt0": sum((r.get("gnomad_af") or 0) > 0 for r in rows),
                    "gnomad_rule": "max(gnomADe AF, gnomADg AF) for the alt allele; "
                                   "0.0 when no gnomAD record is co-located"}

    rows.sort(key=lambda r: (r["gene"], int(re.sub(r"\D", "", r["aa"]) or 0), r["aa"],
                             r["variation_id"]))
    write_tsv(rows, os.path.join(OUT_DIR, TSV_NAME))

    sub_counter = Counter()
    for r in rows:
        for s in filter(None, r["onc_submitters"].split("|")):
            sub_counter[s] += 1
    prov = {
        "fetched_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "script": "scripts/fetch_clinvar_oncogenicity.py",
        "license": "ClinVar data are public domain (NCBI). AlphaMissense (CC BY 4.0) and "
                   "gnomAD AF obtained through the Ensembl VEP REST API.",
        "source_files": {n: {k: v for k, v in d.items() if k != "path_local"}
                         for n, d in files.items()},
        "label_field": "variant_summary column 'Oncogenicity' (aggregate somatic "
                       "oncogenicity classification); NOT the E-utilities "
                       "[Oncogenicity Classification] search qualifier",
        "filters": ["Assembly == GRCh38",
                    "Oncogenicity not in {'-', 'no classification for the single variant'}",
                    "ReviewStatusOncogenicity startswith 'criteria provided'",
                    "Type == 'single nucleotide variant'",
                    "Name ends with a missense p.(Xxx###Yyy) (no Ter, no '=')"],
        "funnel": dict(funnel),
        "n_rows": len(rows),
        "label_dist": dict(Counter(r["oncogenicity"] for r in rows)),
        "class_dist": dict(Counter(r["onc_class"] for r in rows)),
        "onc_last_evaluated_year": dict(Counter((r["onc_last_evaluated"] or "-")[:4]
                                                for r in rows)),
        "submitters_in_snapshot": dict(sub_counter.most_common()),
        "all_oncogenicity_scvs_in_clinvar": {
            "n_scv": len(all_scv),
            "n_submitters": len({s["submitter"] for s in all_scv}),
            "by_submitter": dict(Counter(s["submitter"] for s in all_scv).most_common()),
        },
        "vep": vep_meta,
    }
    json.dump(prov, open(os.path.join(OUT_DIR, "provenance.json"), "w"), indent=2)
    print(f"[+] wrote {len(rows)} rows -> {os.path.relpath(os.path.join(OUT_DIR, TSV_NAME), ROOT)}")
    print(f"    classes {prov['class_dist']}; top submitter "
          f"{sub_counter.most_common(1)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
