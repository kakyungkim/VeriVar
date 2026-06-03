"""Fetch structured knowledge snapshots (CIViC, DGIdb) for the driver panel.

Filters CIViC to the cohort gene panel so the committed snapshot stays small and
offline-reproducible. DGIdb drug-gene interactions are pulled per panel gene.

Run:  python -m scripts.fetch_knowledge
Outputs:
  data/knowledge/civic/civic_evidence_panel.tsv
  data/knowledge/dgidb/dgidb_panel.json
  data/knowledge/provenance.json
"""
import csv
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

from scripts.fetch_cohort import GENE_PANEL

CIVIC_URL = "https://civicdb.org/downloads/nightly/nightly-ClinicalEvidenceSummaries.tsv"
DGIDB_URL = "https://dgidb.org/api/graphql"
OUT = Path("data/knowledge")
PANEL = {g.upper() for g in GENE_PANEL}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "llm-variant-pipeline"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def _post(url: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def fetch_civic() -> int:
    raw = _get(CIVIC_URL).decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(raw), delimiter="\t")
    fields = reader.fieldnames
    kept = []
    for row in reader:
        gene = (row.get("molecular_profile", "").split() or [""])[0].upper()
        if gene in PANEL:
            kept.append(row)
    dest = OUT / "civic" / "civic_evidence_panel.tsv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(kept)
    print(f"[+] CIViC: {len(kept)} panel evidence rows -> {dest}")
    return len(kept)


def fetch_dgidb() -> int:
    query = """
    query($names:[String!]!){ genes(names:$names){ nodes{ name
      interactions{ drug{ name } interactionTypes{ type } sources{ sourceDbName } interactionScore }}}}
    """
    data = _post(DGIDB_URL, {"query": query, "variables": {"names": sorted(PANEL)}})
    by_gene = {}
    for node in data.get("data", {}).get("genes", {}).get("nodes", []):
        interactions = []
        for it in node.get("interactions", []):
            interactions.append({
                "drug": (it.get("drug") or {}).get("name", ""),
                "interaction_types": [t["type"] for t in it.get("interactionTypes", [])],
                "sources": [s["sourceDbName"] for s in it.get("sources", [])],
                "score": it.get("interactionScore"),
            })
        by_gene[node["name"].upper()] = interactions
    dest = OUT / "dgidb" / "dgidb_panel.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(by_gene, indent=2))
    total = sum(len(v) for v in by_gene.values())
    print(f"[+] DGIdb: {total} interactions across {len(by_gene)} genes -> {dest}")
    return total


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    n_civic = fetch_civic()
    n_dgidb = fetch_dgidb()
    (OUT / "provenance.json").write_text(json.dumps({
        "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "civic_source": CIVIC_URL,
        "dgidb_source": DGIDB_URL,
        "gene_panel_size": len(PANEL),
        "civic_evidence_rows": n_civic,
        "dgidb_interactions": n_dgidb,
    }, indent=2))
    print(f"[+] Knowledge snapshots written to {OUT}/")


if __name__ == "__main__":
    sys.exit(main())
