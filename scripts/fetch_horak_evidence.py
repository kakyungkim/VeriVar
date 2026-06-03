"""Fetch evidence for the Horak benchmark genes (some are outside the cohort panel).

CIViC evidence + DGIdb drugs filtered to the 9 Horak genes, and AlphaMissense
(VEP REST, GRCh37) warmed for the 70 variants. Snapshots committed for offline
reproducibility.

Run:  python -m scripts.fetch_horak_evidence
Outputs: data/benchmark/horak_civic.tsv, horak_dgidb.json (+ shared AlphaMissense cache)
"""
import csv
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

from src.models import Variant
from src.knowledge.alphamissense import AlphaMissenseAnnotator

BENCH = Path("data/benchmark/horak_benchmark.tsv")
OUT = Path("data/benchmark")
CIVIC_URL = "https://civicdb.org/downloads/nightly/nightly-ClinicalEvidenceSummaries.tsv"
DGIDB_URL = "https://dgidb.org/api/graphql"


def main():
    d = pd.read_csv(BENCH, sep="\t")
    genes = sorted(d["gene"].str.upper().unique())
    print(f"[*] Horak genes: {genes}")

    # CIViC evidence filtered to Horak genes
    raw = urllib.request.urlopen(urllib.request.Request(
        CIVIC_URL, headers={"User-Agent": "llm-variant-pipeline"}), timeout=120).read().decode("utf-8", "replace")
    reader = csv.DictReader(io.StringIO(raw), delimiter="\t")
    fields = reader.fieldnames
    kept = [r for r in reader if (r.get("molecular_profile", "").split() or [""])[0].upper() in genes]
    civ = OUT / "horak_civic.tsv"
    with civ.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t"); w.writeheader(); w.writerows(kept)
    print(f"[+] CIViC: {len(kept)} evidence rows -> {civ}")

    # DGIdb
    query = ("query($names:[String!]!){ genes(names:$names){ nodes{ name interactions{ "
             "drug{ name } interactionTypes{ type } sources{ sourceDbName } interactionScore }}}}")
    req = urllib.request.Request(DGIDB_URL, data=json.dumps({"query": query, "variables": {"names": genes}}).encode(),
                                 headers={"Content-Type": "application/json"})
    data = json.load(urllib.request.urlopen(req, timeout=120))
    by_gene = {}
    for node in data.get("data", {}).get("genes", {}).get("nodes", []):
        by_gene[node["name"].upper()] = [{
            "drug": (it.get("drug") or {}).get("name", ""),
            "interaction_types": [t["type"] for t in it.get("interactionTypes", [])],
            "sources": [s["sourceDbName"] for s in it.get("sources", [])],
            "score": it.get("interactionScore")} for it in node.get("interactions", [])]
    dg = OUT / "horak_dgidb.json"
    dg.write_text(json.dumps(by_gene, indent=2))
    print(f"[+] DGIdb: {sum(len(v) for v in by_gene.values())} interactions -> {dg}")

    # AlphaMissense (GRCh37 coords) — warm the shared cache
    amis = AlphaMissenseAnnotator(offline=False)
    n = 0
    for _, r in d.iterrows():
        v = Variant(chrom=str(r["b37_chr"]), pos=int(r["b37_pos"]), ref=str(r["b37_ref"]),
                    alt=str(r["b37_alt"]), gene=r["gene"], hgvsp=r["aa"], variant_type="SNV")
        if amis.evidence_for_variant(v):
            n += 1
        time.sleep(0.2)
    print(f"[+] AlphaMissense: scored {n}/{len(d)} -> {amis.cache_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
