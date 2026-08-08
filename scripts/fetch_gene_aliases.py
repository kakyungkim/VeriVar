"""Fetch HGNC-authoritative gene symbol aliases for the cohort genes (network).

The input-context ablation (``scripts/run_context_ablation.py``) perturbs the
gene symbol on the way into the pipeline and asks whether the same variant is
still interpreted the same way. That test is only meaningful if the alternative
symbols are real ones a clinician or a legacy report would actually use, so we
take them from HGNC rather than inventing them: ``alias_symbol`` (currently
used alternatives) and ``prev_symbol`` (officially withdrawn previous symbols).

Output: ``data/knowledge/gene_aliases.json`` (+ provenance), committed so the
ablation itself runs offline.

Run:  python -m scripts.fetch_gene_aliases
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

OUT = Path("data/knowledge/gene_aliases.json")
HGNC = "https://rest.genenames.org/fetch/symbol/{symbol}"

#: The driver-panel genes present in the committed cohort.
COHORT_GENES = [
    "AKT1", "ALK", "APC", "BRAF", "BRCA2", "CDKN2A", "EGFR", "ERBB2",
    "ESR1", "KRAS", "NRAS", "PIK3CA", "PTEN", "ROS1", "TP53",
]


def fetch_one(symbol: str) -> Optional[dict]:
    """Fetch one HGNC record; None when the symbol is not found."""
    req = urllib.request.Request(
        HGNC.format(symbol=symbol),
        headers={"Accept": "application/json", "User-Agent": "VeriVar/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        docs = json.load(r).get("response", {}).get("docs", [])
    if not docs:
        return None
    d = docs[0]
    return {
        "symbol": d.get("symbol"),
        "name": d.get("name"),
        "hgnc_id": d.get("hgnc_id"),
        "entrez_id": d.get("entrez_id"),
        "alias_symbol": d.get("alias_symbol", []),
        "prev_symbol": d.get("prev_symbol", []),
    }


def main() -> int:
    records: Dict[str, dict] = {}
    missing: List[str] = []
    for g in COHORT_GENES:
        rec = fetch_one(g)
        if rec is None:
            missing.append(g)
            print(f"[!] no HGNC record for {g}")
            continue
        records[g] = rec
        n = len(rec["alias_symbol"]) + len(rec["prev_symbol"])
        print(f"    {g}: {n} alternative symbol(s) — {rec['hgnc_id']}")

    payload = {
        "provenance": {
            "source": "HGNC REST (rest.genenames.org/fetch/symbol/{symbol})",
            "fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "n_genes": len(records),
            "missing": missing,
            "fields": "alias_symbol (current alternatives) + prev_symbol (withdrawn previous symbols)",
        },
        "genes": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"[+] wrote {OUT} ({len(records)}/{len(COHORT_GENES)} genes)")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
