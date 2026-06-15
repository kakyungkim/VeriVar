"""Build driver-gene panel BED files (real coordinates) from Ensembl REST.

Why: the bring-your-own-VCF path (:mod:`src.cohort.vcf_loader`) only filters by
gene *symbol* AFTER VEP annotation, so off-panel variants still consume Ensembl
VEP REST calls. A genomic *region* (coordinate) filter applied BEFORE the VEP
batch needs a gene -> (chromosome, start, end) map. This script materialises that
map as committed BED files, one per assembly, by looking up each panel gene's
genomic span via the Ensembl gene-lookup endpoint.

ANTI-FABRICATION: every coordinate written here comes from a live Ensembl REST
gene-lookup response. Genes that fail to resolve are logged and skipped — never
filled in with a guessed/hand-written coordinate.

Genes: the 27-gene driver panel ``scripts.fetch_cohort.GENE_PANEL`` (union of
driver genes across the 5 TCGA cancer studies in this repo).

Assemblies / endpoints (gene-lookup, gene span = transcript-spanning locus):
  GRCh37: https://grch37.rest.ensembl.org/lookup/symbol/homo_sapiens/{gene}
  GRCh38: https://rest.ensembl.org/lookup/symbol/homo_sapiens/{gene}
both with ``?content-type=application/json``.

Output BED format (TSV, one line per resolved gene)::

    chrom\tstart\tend\tgene

Coordinate convention: **BED is 0-based, half-open** ``[start, end)`` by spec.
Ensembl REST returns **1-based, fully-closed** ``[start, end]`` coordinates, so we
write ``bed_start = ensembl_start - 1`` and ``bed_end = ensembl_end`` (the closed
1-based end equals the half-open 0-based end). The span is the whole gene locus;
exon-level intervals are a future refinement (a region pre-filter only needs to be
a *superset* of the true variant locations to be safe, and the gene span is one).

Outputs (committed for offline reproducibility):
  data/knowledge/panel/driver_panel_grch37.bed
  data/knowledge/panel/driver_panel_grch38.bed

Run:  python -m scripts.fetch_panel_bed
"""
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scripts.fetch_cohort import GENE_PANEL

OUT_DIR = Path("data/knowledge/panel")

# assembly label -> (Ensembl REST host, output BED filename)
ASSEMBLIES = {
    "GRCh37": ("https://grch37.rest.ensembl.org", "driver_panel_grch37.bed"),
    "GRCh38": ("https://rest.ensembl.org", "driver_panel_grch38.bed"),
}

_LOOKUP_PATH = "/lookup/symbol/homo_sapiens/{gene}?content-type=application/json"
_TIMEOUT = 30.0
_PAUSE = 0.34  # ~3 req/s, well under Ensembl's 15 req/s rate limit


def _lookup_gene(host: str, gene: str, timeout: float = _TIMEOUT) -> dict:
    """GET one gene's Ensembl gene-lookup record (raises on HTTP/parse error)."""
    import json
    url = host + _LOOKUP_PATH.format(gene=gene)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _span_from_record(rec: dict) -> Tuple[str, int, int]:
    """Extract ``(seq_region_name, start, end)`` (Ensembl 1-based, closed)."""
    chrom = str(rec["seq_region_name"])
    start = int(rec["start"])
    end = int(rec["end"])
    return chrom, start, end


def fetch_assembly_bed(
    host: str,
    genes: List[str],
    pause: float = _PAUSE,
) -> Tuple[List[Tuple[str, int, int, str]], List[str]]:
    """Resolve every gene's span on one assembly.

    Returns ``(rows, failed)`` where each row is the BED tuple
    ``(chrom, bed_start, bed_end, gene)`` (0-based, half-open) and ``failed`` is
    the list of gene symbols that did not resolve. Per-gene try/except: a single
    failure is logged and skipped, never fabricated.
    """
    rows: List[Tuple[str, int, int, str]] = []
    failed: List[str] = []
    for gene in genes:
        try:
            rec = _lookup_gene(host, gene)
            chrom, start_1based, end_1based = _span_from_record(rec)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                OSError, KeyError, ValueError) as e:
            print(f"  [!] {gene}: failed to resolve ({e}) — skipped", file=sys.stderr)
            failed.append(gene)
            continue
        # Ensembl 1-based closed [start, end] -> BED 0-based half-open [start-1, end).
        rows.append((chrom, start_1based - 1, end_1based, gene))
        print(f"  [ok] {gene}: {chrom}:{start_1based}-{end_1based}")
        time.sleep(pause)
    return rows, failed


def write_bed(rows: List[Tuple[str, int, int, str]], dest: Path) -> None:
    """Write BED rows (TSV: chrom, start, end, gene) with a documented header."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Driver-gene panel region filter — gene spans from Ensembl REST gene-lookup.",
        "# Format: 0-based half-open [start, end), TSV columns: chrom start end gene.",
        "# chrom\tstart\tend\tgene",
    ]
    for chrom, start, end, gene in rows:
        lines.append(f"{chrom}\t{start}\t{end}\t{gene}")
    dest.write_text("\n".join(lines) + "\n")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary: Dict[str, dict] = {}
    for assembly, (host, fname) in ASSEMBLIES.items():
        print(f"[*] {assembly} via {host} ({len(GENE_PANEL)} genes)")
        rows, failed = fetch_assembly_bed(host, GENE_PANEL)
        dest = OUT_DIR / fname
        write_bed(rows, dest)
        summary[assembly] = {"resolved": len(rows), "failed": failed, "path": str(dest)}
        print(f"[*] {assembly}: {len(rows)}/{len(GENE_PANEL)} resolved -> {dest}")
        if failed:
            print(f"    failed: {', '.join(failed)}", file=sys.stderr)

    print("\n=== summary ===")
    for assembly, s in summary.items():
        print(f"{assembly}: {s['resolved']}/{len(GENE_PANEL)} resolved, "
              f"failed={s['failed']}")
    # Non-zero exit only if NOTHING resolved on some assembly (network broken).
    if any(s["resolved"] == 0 for s in summary.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
