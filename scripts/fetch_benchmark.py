"""Fetch the CIViC Assertions ground-truth snapshot for evaluation.

Downloads CIViC AssertionSummaries and keeps single-variant assertions with an
AMP category (the expert tier label). Small and skewed (mostly Tier I) — used as
a secondary external check; the leakage-free faithfulness suite is the headline.

Run:  python -m scripts.fetch_benchmark
Output: data/benchmark/civic_assertions.tsv (+ provenance.json)
"""
import csv
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

URL = "https://civicdb.org/downloads/nightly/nightly-AssertionSummaries.tsv"
OUT = Path("data/benchmark")


def main():
    raw = urllib.request.urlopen(urllib.request.Request(
        URL, headers={"User-Agent": "llm-variant-pipeline"}), timeout=120).read().decode("utf-8", "replace")
    reader = csv.DictReader(io.StringIO(raw), delimiter="\t")
    fields = reader.fieldnames
    kept = [r for r in reader
            if r.get("amp_category") and len(r["molecular_profile"].split()) >= 2
            and "::" not in r["molecular_profile"] and " OR " not in r["molecular_profile"]]
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "civic_assertions.tsv"
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(kept)
    (OUT / "provenance.json").write_text(json.dumps({
        "source": URL, "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_assertions": len(kept),
    }, indent=2))
    print(f"[+] {len(kept)} single-variant assertions -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
