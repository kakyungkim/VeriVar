"""Resolve emitted PMIDs / ClinVar IDs against NCBI and cache the records.

Purpose
-------
Supply the existence and content checks the citation taxonomy needs
(categories b1 "no record" and c "real record unrelated to the gene"; see
``src/eval/citation_taxonomy.py``). Network access happens ONLY here (project
convention). The taxonomy itself (``scripts/run_citation_taxonomy.py``) runs
offline from the cache.

Prerequisites
-------------
Network access to eutils.ncbi.nlm.nih.gov and the three committed inputs
listed below. Optional env vars ``NCBI_EMAIL`` / ``NCBI_API_KEY``.

Run
---
::

    python -m scripts.fetch_citation_lookup [--out PATH]

Output
------
``data/outputs/citation_lookup_cache.json``: per PMID ``exists``, ``title``,
``journal``, ``pubdate``, ``abstract``, ``error``; per ClinVar VariationID
``exists``, ``title``, ``genes``, ``accession``; plus ``retrieved_utc`` (the
retrieval date) and the input list. Re-running overwrites the cache and its
date; NCBI records can change, so quote the date with any number derived
from it.

What is looked up
-----------------
Every identifier-bearing token of kind ``pmid`` or ``clinvar`` (see
``src.eval.citation_taxonomy.parse_token``) emitted by any audited arm:

* no-retrieval arm: ``data/outputs/ablation_report.json`` (``rows[].norag_citations``)
* retrieval arm, gpt-4o-mini 106-citation run: ``multimodel_faithfulness_gpt4o.json``
* primary pipeline run: ``cohort_interpretation.json`` (``mode_a.citations``)

Placeholder-pattern numbers are looked up too, so the report can say whether a
record with that number happens to exist.

NCBI E-utilities are called with ``tool=verivar``; an e-mail and API key are
read from the env vars ``NCBI_EMAIL`` / ``NCBI_API_KEY`` if set (never printed).
Requests are spaced 0.4 s apart (0.12 s with a key), under NCBI's 3 (10)
requests/s limit.

* PubMed: ``esummary`` (JSON) for existence + title + journal + date, then
  ``efetch`` (XML) for the abstract text.
* ClinVar: ``esummary db=clinvar`` on the numeric VariationID for title + genes.

"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Set

from src.eval.citation_taxonomy import parse_token

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
OUT = Path("data/outputs/citation_lookup_cache.json")
ABLATION = Path("data/outputs/ablation_report.json")
LABEL_ONLY = Path("data/outputs/multimodel_faithfulness_gpt4o.json")
COHORT = Path("data/outputs/cohort_interpretation.json")


def _params(extra: Dict[str, str]) -> Dict[str, str]:
    p = {"tool": "verivar", **extra}
    if os.environ.get("NCBI_EMAIL"):
        p["email"] = os.environ["NCBI_EMAIL"]
    if os.environ.get("NCBI_API_KEY"):
        p["api_key"] = os.environ["NCBI_API_KEY"]
    return p


def _get(endpoint: str, params: Dict[str, str]) -> bytes:
    url = f"{EUTILS}/{endpoint}?{urllib.parse.urlencode(_params(params))}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read()
        except Exception:  # noqa: BLE001 - retry transient network errors
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def all_tokens() -> Iterable[str]:
    for r in json.loads(ABLATION.read_text())["rows"]:
        yield from r.get("norag_citations") or []
    for r in json.loads(LABEL_ONLY.read_text())["results"]:
        for pm in (r.get("per_model") or {}).values():
            yield from pm.get("cited_ids") or []
    for v in json.loads(COHORT.read_text())["variants"]:
        yield from (v.get("mode_a") or {}).get("citations") or []


def collect_ids() -> Dict[str, Set[str]]:
    ids: Dict[str, Set[str]] = {"pmid": set(), "clinvar": set()}
    for tok in all_tokens():
        p = parse_token(tok)
        if p.kind in ids and p.number:
            ids[p.kind].add(p.number.lstrip("0") or "0")
    return ids


def fetch_pubmed(pmids: List[str], pause: float) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    if not pmids:
        return out
    summ = json.loads(_get("esummary.fcgi", {"db": "pubmed", "id": ",".join(pmids),
                                              "retmode": "json"}))["result"]
    time.sleep(pause)
    for pid in pmids:
        s = summ.get(pid) or {}
        exists = bool(s) and "error" not in s and bool(s.get("title"))
        out[pid] = {"exists": exists, "title": s.get("title"),
                    "journal": s.get("fulljournalname") or s.get("source"),
                    "pubdate": s.get("pubdate"), "error": s.get("error"),
                    "abstract": None}
    found = [p for p in pmids if out[p]["exists"]]
    if found:
        xml = _get("efetch.fcgi", {"db": "pubmed", "id": ",".join(found), "retmode": "xml"})
        time.sleep(pause)
        root = ET.fromstring(xml)
        for art in root.findall(".//PubmedArticle"):
            pid = art.findtext(".//MedlineCitation/PMID")
            parts = ["".join(a.itertext()) for a in art.findall(".//Abstract/AbstractText")]
            if pid in out:
                out[pid]["abstract"] = " ".join(parts) or None
    return out


def fetch_clinvar(vids: List[str], pause: float) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    if not vids:
        return out
    summ = json.loads(_get("esummary.fcgi", {"db": "clinvar", "id": ",".join(vids),
                                              "retmode": "json"}))["result"]
    time.sleep(pause)
    for vid in vids:
        s = summ.get(vid) or {}
        exists = bool(s) and "error" not in s and bool(s.get("title"))
        genes = [g.get("symbol") for g in (s.get("genes") or []) if g.get("symbol")]
        out[vid] = {"exists": exists, "title": s.get("title"), "genes": genes,
                    "accession": s.get("accession"), "error": s.get("error")}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    pause = 0.12 if os.environ.get("NCBI_API_KEY") else 0.4
    ids = collect_ids()
    pubmed = fetch_pubmed(sorted(ids["pmid"], key=int), pause)
    clinvar = fetch_clinvar(sorted(ids["clinvar"], key=int), pause)
    cache = {
        "retrieved_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "NCBI E-utilities (esummary pubmed/clinvar; efetch pubmed abstracts)",
        "inputs": [str(ABLATION), str(LABEL_ONLY), str(COHORT)],
        "pmid": pubmed,
        "clinvar": clinvar,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"[+] wrote {args.out}: {len(pubmed)} PMIDs "
          f"({sum(r['exists'] for r in pubmed.values())} exist), {len(clinvar)} ClinVar IDs "
          f"({sum(r['exists'] for r in clinvar.values())} exist)")
    for pid, r in pubmed.items():
        print(f"    PMID {pid}: exists={r['exists']} | {(r['title'] or r['error'] or '')[:90]}")
    for vid, r in clinvar.items():
        print(f"    ClinVar {vid}: exists={r['exists']} | {r['title']} | {r['genes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
