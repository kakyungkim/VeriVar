#!/usr/bin/env python3
"""Fetch the pre-registered inputs of the ``sop_strict_v2`` VICC configuration.

Pre-registration: notes/audits/2026-09-24/개선라운드_사전명시_20260924.md (sealed before any
evaluation with these inputs). This is the ONLY network step of the improvement round;
everything downstream runs offline from the snapshots written here.

Three independent steps (``--steps vep,civic,mavedb``; default all):

  vep     Ensembl VEP REST (GRCh38) for every Horak-70 and ClinVar-snapshot variant:
          REVEL, CADD phred, SIFT, PolyPhen-2 (OP1/SBP1 predictor lines, change a) and the
          gnomAD v4 per-population allele frequencies (SBVS1/SBS1 on the maximum of the 5 SOP
          continental populations, change b).
          -> data/knowledge/vep_v2/vep_v2_annotations.json (+ provenance.json)
  civic   CIViC monthly release ClinicalEvidenceSummaries (accepted evidence, CC0), all genes
          (change c1). -> data/knowledge/civic/civic_evidence_release_<date>.tsv
  mavedb  MaveDB DMS score sets for tumour-suppressor genes of the Horak/ClinVar panels, selected
          by the pre-registered eligibility criteria, calibrated exactly like the existing PTEN
          path (nonsense-anchored midpoint) (change c2).
          -> data/knowledge/functional/dms_lof_v2.json (+ provenance_v2.json)

Afterwards ``--steps extract`` (offline) writes per-benchmark input tables to
data/benchmark/vicc_v2/{horak,clinvar}_v2_inputs.json.

Existing snapshots (dms_lof.json, dms_neutral.json, horak_gnomad.json, the AlphaMissense caches,
the CIViC panel TSVs) are never modified.

Usage:  python -m scripts.fetch_vicc_v2_inputs [--steps vep,civic,mavedb,extract]
"""
import argparse
import csv
import datetime as _dt
import hashlib
import io
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.classify.vicc_inputs import (CONTINENTAL_POPS, clinvar_variants,  # noqa: E402
                                      horak_variants, parse_vep_v2_record, v2_key)
from src.classify.vicc_rules import TUMOUR_SUPPRESSORS  # noqa: E402

KNOW = os.path.join(ROOT, "data", "knowledge")
VEP_DIR = os.path.join(KNOW, "vep_v2")
VEP_OUT = os.path.join(VEP_DIR, "vep_v2_annotations.json")
CIVIC_DIR = os.path.join(KNOW, "civic")
FUNC_DIR = os.path.join(KNOW, "functional")
BENCH_V2 = os.path.join(ROOT, "data", "benchmark", "vicc_v2")

VEP_URL = ("https://rest.ensembl.org/vep/human/region?REVEL=1&CADD=1&AlphaMissense=1"
           "&af_gnomade=1&af_gnomadg=1&mane=1&canonical=1")
CIVIC_RELEASE_URL = "https://civicdb.org/downloads/{d}/{d}-ClinicalEvidenceSummaries.tsv"
MAVE_API = "https://api.mavedb.org/api/v1"
UNIPROT = ("https://rest.uniprot.org/uniprotkb/search?query=gene_exact:{g}+AND+organism_id:9606"
           "+AND+reviewed:true&fields=accession,sequence&format=json")
OPEN_LICENCES = {"CC0", "CC BY 4.0"}
EXISTING_DMS_GENES = {"TP53", "PTEN"}          # pre-registered: keep existing sources only
EXISTING_DMS_URNS = ["urn:mavedb:00000054-a-1", "urn:mavedb:00000013-a-1",
                     "urn:mavedb:00001236-0-1"]
MIN_NONSENSE, MIN_MISSENSE, MIN_REF_MATCH = 10, 50, 0.95

_AA3 = {"Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q",
        "Glu": "E", "Gly": "G", "His": "H", "Ile": "I", "Leu": "L", "Lys": "K",
        "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W",
        "Tyr": "Y", "Val": "V", "Ter": "*"}
_HGVS_PRO = re.compile(r"p\.\(?([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2}|=)\)?$")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _get(url: str, data: Optional[bytes] = None, timeout: int = 180, tries: int = 4,
         headers: Optional[dict] = None) -> bytes:
    hdr = {"Accept": "application/json", "User-Agent": "VeriVar-research/0.1"}
    if data is not None:
        hdr["Content-Type"] = "application/json"
    hdr.update(headers or {})
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return f.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            last = e
        except Exception as e:  # noqa: BLE001 - network retry
            last = e
        print(f"    retry {attempt + 1}: {last}")
        time.sleep(5 * (attempt + 1))
    raise SystemExit(f"request failed repeatedly: {url} ({last})")


def _write_json(path: str, obj, **kw) -> None:
    """Write via a temp file + atomic replace (never truncates the target on failure)."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, **kw)
    os.replace(tmp, path)


# --------------------------------------------------------------------------- VEP
def step_vep(batch: int = 100) -> None:
    os.makedirs(VEP_DIR, exist_ok=True)
    variants = horak_variants() + clinvar_variants()
    by_key: Dict[str, str] = {}
    for v in variants:
        by_key[v2_key(v["chrom"], v["pos"], v["ref"], v["alt"])] = v["gene"]
    cache = json.load(open(VEP_OUT)) if os.path.exists(VEP_OUT) else {}
    todo = [k for k in by_key if k not in cache]
    print(f"  VEP: {len(by_key)} unique GRCh38 variants, {len(todo)} to fetch")
    for i in range(0, len(todo), batch):
        keys = todo[i:i + batch]
        inputs = {f"{k.split()[0]} {k.split()[1]} . {k.split()[2]} {k.split()[3]} . . .": k
                  for k in keys}
        body = json.dumps({"variants": list(inputs)}).encode()
        data = json.loads(_get(VEP_URL, data=body))
        for rec in data:
            k = inputs.get(rec.get("input"))
            if k:
                cache[k] = parse_vep_v2_record(rec, by_key[k])
        for k in keys:
            cache.setdefault(k, {"vep_returned": False})
        _write_json(VEP_OUT, cache, indent=1, sort_keys=True)
        print(f"    VEP {min(i + batch, len(todo))}/{len(todo)}")
        time.sleep(1)
    info = json.loads(_get("https://rest.ensembl.org/info/data?content-type=application/json"))
    try:
        sw = json.loads(_get("https://rest.ensembl.org/info/software?content-type=application/json"))
    except SystemExit:
        sw = {}
    prov = {"fetched_utc": _now(), "script": "scripts/fetch_vicc_v2_inputs.py --steps vep",
            "endpoint": VEP_URL, "assembly": "GRCh38", "ensembl_release": info.get("releases"),
            "ensembl_software": sw, "n_variants": len(cache),
            "sha256": _sha256(VEP_OUT),
            "fields": "REVEL (plugin; value from a same-gene transcript with the MANE amino-acid "
                      "change), CADD phred (variant level), SIFT and PolyPhen-2 (MANE Select, "
                      "else canonical), AlphaMissense (MANE, QC only), gnomAD v4 exomes/genomes "
                      "per-population AF from colocated_variants",
            "continental_pops": CONTINENTAL_POPS,
            "licences": "Ensembl (open); REVEL (free for non-commercial research); CADD "
                        "(free for non-commercial use); gnomAD (ODbL/CC0 summary data); "
                        "AlphaMissense (CC BY 4.0)",
            "prereg": "notes/audits/2026-09-24/개선라운드_사전명시_20260924.md"}
    _write_json(os.path.join(VEP_DIR, "provenance.json"), prov, indent=2, ensure_ascii=False)
    print(f"[+] wrote {VEP_OUT}")


# --------------------------------------------------------------------------- CIViC
def step_civic() -> None:
    today = _dt.date.today()
    tried = []
    for back in range(0, 4):
        y, m = today.year, today.month - back
        while m <= 0:
            y, m = y - 1, m + 12
        d = _dt.date(y, m, 1).strftime("%d-%b-%Y")
        url = CIVIC_RELEASE_URL.format(d=d)
        tried.append(url)
        try:
            raw = _get(url, timeout=300, tries=2, headers={"Accept": "text/tab-separated-values"})
        except (urllib.error.HTTPError, SystemExit):
            continue
        if not raw.startswith(b"molecular_profile"):
            continue
        out = os.path.join(CIVIC_DIR, f"civic_evidence_release_{d}.tsv")
        with open(out + ".tmp", "wb") as f:
            f.write(raw)
        os.replace(out + ".tmp", out)
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8")), delimiter="\t"))
        prov_path = os.path.join(CIVIC_DIR, "provenance_release.json")
        prov = {"fetched_utc": _now(), "script": "scripts/fetch_vicc_v2_inputs.py --steps civic",
                "url": url, "release": d, "file": os.path.relpath(out, ROOT),
                "sha256": _sha256(out), "n_rows": len(rows),
                "n_genes": len({r["molecular_profile"].split()[0] for r in rows}),
                "evidence_status": sorted({r.get("evidence_status", "") for r in rows}),
                "licence": "CIViC data are CC0 1.0",
                "use": "sop_strict_v2 change c1: unioned with horak_civic.tsv and "
                       "civic_evidence_panel.tsv by evidence_id (existing rows take precedence); "
                       "SOP mapping civic_signal_from_rows unchanged"}
        _write_json(prov_path, prov, indent=2)
        print(f"[+] CIViC release {d}: {len(rows)} rows -> {out}")
        return
    raise SystemExit(f"no CIViC monthly release found; tried {tried}")


# --------------------------------------------------------------------------- MaveDB
def parse_hgvs_pro(hp: str) -> Optional[Tuple[str, int, str]]:
    """'p.Thr131Ile' / 'NP_x:p.(Thr131Ile)' -> ('T', 131, 'I'); synonymous -> ('T',131,'=')."""
    m = _HGVS_PRO.search((hp or "").strip())
    if not m:
        return None
    r = _AA3.get(m.group(1))
    a = "=" if m.group(3) == "=" else _AA3.get(m.group(3))
    return (r, int(m.group(2)), a) if r and a else None


def _scores(urn: str) -> List[Tuple[str, Optional[float]]]:
    raw = _get(f"{MAVE_API}/score-sets/{urn}/scores", timeout=300,
               headers={"Accept": "text/csv"}).decode("utf-8")
    rd = csv.DictReader(io.StringIO(raw))
    out = []
    for r in rd:
        try:
            s = float(r.get("score"))
        except (TypeError, ValueError):
            s = None
        if s is not None and s != s:          # NaN
            s = None
        out.append((r.get("hgvs_pro") or "", s))
    return out


def _uniprot_seq(gene: str) -> Tuple[Optional[str], Optional[str]]:
    d = json.loads(_get(UNIPROT.format(g=gene)))
    for r in d.get("results", []):
        return r.get("primaryAccession"), r.get("sequence", {}).get("value")
    return None, None


def calibrate(rows: List[Tuple[str, Optional[float]]], seq: Optional[str]) -> dict:
    """Nonsense-anchored midpoint calibration (the existing PTEN path), direction-general.

    Returns the per-set summary and the LoF amino-acid changes. Multiple nucleotide variants of
    one amino-acid change are collapsed to their median score first."""
    per_aa: Dict[str, List[float]] = defaultdict(list)
    nonsense: List[float] = []
    synonymous: List[float] = []
    ref_ok = ref_n = 0
    for hp, s in rows:
        pp = parse_hgvs_pro(hp)
        if not pp or s is None:
            continue
        r, p, a = pp
        if a == "*":
            nonsense.append(s)
        elif a == "=" or a == r:
            synonymous.append(s)
        else:
            per_aa[f"{r}{p}{a}"].append(s)
            if seq:
                ref_n += 1
                ref_ok += int(p - 1 < len(seq) and seq[p - 1] == r)
    miss = {k: statistics.median(v) for k, v in per_aa.items()}
    summ = {"n_missense_aa": len(miss), "n_nonsense": len(nonsense),
            "n_synonymous": len(synonymous),
            "ref_match": round(ref_ok / ref_n, 4) if ref_n else None}
    if len(nonsense) < MIN_NONSENSE or len(miss) < MIN_MISSENSE:
        summ["eligible"] = False
        summ["reason"] = "too few nonsense or missense scores"
        return {"summary": summ, "lof": {}, "keys": set(miss)}
    if summ["ref_match"] is None or summ["ref_match"] < MIN_REF_MATCH:
        summ["eligible"] = False
        summ["reason"] = "reference amino acids do not match UniProt numbering (>=95% required)"
        return {"summary": summ, "lof": {}, "keys": set(miss)}
    mis_med = statistics.median(miss.values())
    non_med = statistics.median(nonsense)
    cutoff = (mis_med + non_med) / 2.0
    lof_low = non_med < mis_med
    if synonymous:
        syn_med = statistics.median(synonymous)
        summ["synonymous_median"] = round(syn_med, 4)
        if (syn_med <= cutoff) == lof_low:
            summ["eligible"] = False
            summ["reason"] = "synonymous median on the LoF side (inverted controls)"
            return {"summary": summ, "lof": {}, "keys": set(miss)}
    lof = {k: True for k, s in miss.items() if (s <= cutoff if lof_low else s >= cutoff)}
    summ.update({"eligible": True, "missense_median": round(mis_med, 4),
                 "nonsense_median": round(non_med, 4), "cutoff": round(cutoff, 4),
                 "lof_side": "low" if lof_low else "high", "n_lof": len(lof)})
    return {"summary": summ, "lof": lof, "keys": set(miss)}


def _mave_meta(urn: str) -> dict:
    d = json.loads(_get(f"{MAVE_API}/score-sets/{urn}"))
    lic = d.get("license") or {}
    tgs = d.get("targetGenes") or []
    return {"urn": urn, "title": d.get("title"),
            "licence": lic.get("shortName") if isinstance(lic, dict) else lic,
            "published": bool(d.get("publishedDate")),
            "superseded_by": (d.get("supersedingScoreSet") or {}).get("urn")
            if isinstance(d.get("supersedingScoreSet"), dict) else d.get("supersedingScoreSet"),
            "targets": [t.get("name") for t in tgs],
            "organism": [((t.get("targetSequence") or {}).get("taxonomy") or {}).get("organismName")
                         for t in tgs],
            "experiment_set": (d.get("experiment") or {}).get("experimentSetUrn"),
            "num_variants": d.get("numVariants"),
            "doi_pubmed": [p.get("identifier") for p in
                           (d.get("primaryPublicationIdentifiers") or [])]}


def step_mavedb() -> None:
    os.makedirs(FUNC_DIR, exist_ok=True)
    panel = {v["gene"] for v in horak_variants()} | {v["gene"] for v in clinvar_variants()}
    genes = sorted((panel & TUMOUR_SUPPRESSORS) - EXISTING_DMS_GENES)
    print(f"  MaveDB candidate genes (TSG in panels, minus TP53/PTEN): {genes}")
    prov = {"fetched_utc": _now(), "script": "scripts/fetch_vicc_v2_inputs.py --steps mavedb",
            "api": MAVE_API, "candidate_genes": genes, "criteria": {
                "gene": "(Horak-9 U ClinVar-snapshot genes) & TUMOUR_SUPPRESSORS, minus TP53/PTEN",
                "licence": sorted(OPEN_LICENCES), "published_not_superseded": True,
                "single_human_target_equal_to_gene": True,
                "min_nonsense": MIN_NONSENSE, "min_missense_aa": MIN_MISSENSE,
                "min_uniprot_ref_match": MIN_REF_MATCH,
                "exclude_inverted_synonymous": True,
                "partition_subsets_dropped": "a set whose scored amino-acid changes are all "
                                             "contained in a larger eligible set of the same "
                                             "MaveDB experiment set is dropped (exon-level "
                                             "partitions of one SGE screen)"},
            "calibration": "cutoff = (median missense + median nonsense)/2; LoF side = side of "
                           "the nonsense median; per-aa median over nucleotide variants; LoF in "
                           "ANY eligible set of the gene -> LoF; no neutral calls",
            "existing_sources_licence": {}, "sets": [], "genes": {}}
    for urn in EXISTING_DMS_URNS:
        try:
            m = _mave_meta(urn)
            prov["existing_sources_licence"][urn] = m["licence"]
        except Exception as e:  # noqa: BLE001
            prov["existing_sources_licence"][urn] = f"lookup failed: {e}"
    dms_v2: Dict[str, Dict[str, bool]] = {}
    for g in genes:
        res = json.loads(_get(f"{MAVE_API}/score-sets/search",
                              data=json.dumps({"targets": [g]}).encode()))
        acc, seq = _uniprot_seq(g)
        eligible = []
        for s in res.get("scoreSets", []):
            urn = s["urn"]
            m = _mave_meta(urn)
            rec = dict(m, gene=g, uniprot=acc)
            why = None
            if m["licence"] not in OPEN_LICENCES:
                why = f"licence {m['licence']}"
            elif not m["published"]:
                why = "not published"
            elif m["superseded_by"]:
                why = f"superseded by {m['superseded_by']}"
            elif m["targets"] != [g]:
                why = f"targets {m['targets']} (multi-target or different gene)"
            elif any(o and "sapiens" not in o for o in m["organism"]):
                why = f"organism {m['organism']}"
            if why:
                rec.update(eligible=False, reason=why)
                prov["sets"].append(rec)
                continue
            cal = calibrate(_scores(urn), seq)
            rec.update(cal["summary"])
            prov["sets"].append(rec)
            if cal["summary"].get("eligible"):
                eligible.append((urn, m, cal))
            time.sleep(0.5)
        # drop partition subsets: a set whose scored amino-acid changes are all contained in a
        # strictly larger eligible set of the same MaveDB experiment set (exon partitions)
        keep = []
        for urn, m, cal in eligible:
            sub = any(urn2 != urn and m2["experiment_set"] == m["experiment_set"]
                      and len(cal2["keys"]) > len(cal["keys"])
                      and cal["keys"] <= cal2["keys"]
                      for urn2, m2, cal2 in eligible)
            if sub:
                for r in prov["sets"]:
                    if r["urn"] == urn:
                        r.update(eligible=False, reason="partition subset of a larger set "
                                                        "in the same experiment set")
            else:
                keep.append((urn, cal))
        lof: Dict[str, bool] = {}
        for urn, cal in keep:
            lof.update(cal["lof"])
        if keep:
            dms_v2[g] = lof
        prov["genes"][g] = {"uniprot": acc, "sets_used": [u for u, _ in keep],
                            "n_lof_aa": len(lof)}
        print(f"    {g}: {len(keep)} set(s) used, {len(lof)} LoF aa changes")
    # carry over the existing sources unchanged (TP53, PTEN)
    existing = json.load(open(os.path.join(FUNC_DIR, "dms_lof.json")))
    for g in EXISTING_DMS_GENES:
        if g in existing:
            dms_v2[g] = existing[g]
    out = os.path.join(FUNC_DIR, "dms_lof_v2.json")
    _write_json(out, dms_v2)
    prov["output"] = os.path.relpath(out, ROOT)
    prov["sha256"] = _sha256(out)
    prov["note"] = ("TP53 and PTEN are copied unchanged from dms_lof.json; dms_neutral.json is "
                    "unchanged and still the only neutral (SBS2) DMS source")
    _write_json(os.path.join(FUNC_DIR, "provenance_v2.json"), prov, indent=2)
    print(f"[+] wrote {out}")


# --------------------------------------------------------------------------- extract
def step_extract() -> None:
    from src.classify.vicc_inputs import build_benchmark_inputs
    os.makedirs(BENCH_V2, exist_ok=True)
    for name, variants in (("horak", horak_variants()), ("clinvar", clinvar_variants())):
        table, cov = build_benchmark_inputs(variants)
        out = os.path.join(BENCH_V2, f"{name}_v2_inputs.json")
        _write_json(out, {"coverage": cov, "variants": table}, indent=1, sort_keys=True)
        print(f"[+] {name}: {len(table)} variants -> {out}")
        print("    " + json.dumps(cov))
    prov = {"built_utc": _now(), "script": "scripts/fetch_vicc_v2_inputs.py --steps extract",
            "sources": {p: _sha256(os.path.join(ROOT, p)) for p in (
                os.path.relpath(VEP_OUT, ROOT),
                os.path.relpath(os.path.join(FUNC_DIR, "dms_lof_v2.json"), ROOT))
                if os.path.exists(os.path.join(ROOT, p))},
            "prereg": "notes/audits/2026-09-24/개선라운드_사전명시_20260924.md"}
    _write_json(os.path.join(BENCH_V2, "provenance.json"), prov, indent=2, ensure_ascii=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--steps", default="vep,civic,mavedb,extract")
    args = ap.parse_args()
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    for s in steps:
        {"vep": step_vep, "civic": step_civic, "mavedb": step_mavedb,
         "extract": step_extract}[s]()


if __name__ == "__main__":
    main()
