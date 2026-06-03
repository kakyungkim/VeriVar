"""Download the full AlphaMissense dataset (Zenodo) for local lookup.

NOT needed for the default pipeline — Phase 3d queries AlphaMissense per-variant
via the Ensembl VEP REST API for the small cohort. This script is provided for
when a genome-wide local lookup is wanted (large cohorts / offline / batch).

Source: Cheng et al., Science 2023 — Zenodo record 8208688.
License: CC BY-NC-SA 4.0 (non-commercial). Compatible with this repo's
research/education-only scope; do NOT commit the downloaded files (they live
under data/knowledge/, which is gitignored).

Usage:
  python -m scripts.fetch_alphamissense --file hg38          # ~643 MB (default)
  python -m scripts.fetch_alphamissense --file aa_subs       # ~1.2 GB
  python -m scripts.fetch_alphamissense --file gene_hg38     # ~254 KB
  python -m scripts.fetch_alphamissense --list
"""
import argparse
import sys
import urllib.request
from pathlib import Path

ZENODO = "https://zenodo.org/records/8208688/files/{name}?download=1"
OUT_DIR = Path("data/knowledge/alphamissense")

FILES = {
    "hg38": ("AlphaMissense_hg38.tsv.gz", "~643 MB — all hg38 SNV predictions"),
    "hg19": ("AlphaMissense_hg19.tsv.gz", "~ similar — all hg19 SNV predictions"),
    "aa_subs": ("AlphaMissense_aa_substitutions.tsv.gz", "~1.2 GB — all protein substitutions"),
    "gene_hg38": ("AlphaMissense_gene_hg38.tsv.gz", "~254 KB — gene-level aggregates"),
    "isoforms_aa_subs": ("AlphaMissense_isoforms_aa_substitutions.tsv.gz", "isoform substitutions"),
}


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


def download(name: str, dest: Path) -> None:
    """Stream-download with resume (HTTP Range) and a simple progress line."""
    url = ZENODO.format(name=name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    existing = dest.stat().st_size if dest.exists() else 0

    req = urllib.request.Request(url)
    if existing:
        req.add_header("Range", f"bytes={existing}-")
        print(f"[*] Resuming {name} from {_human(existing)}")

    with urllib.request.urlopen(req, timeout=120) as r:
        total = int(r.headers.get("Content-Length", 0)) + existing
        mode = "ab" if existing and r.status == 206 else "wb"
        if mode == "wb":
            existing = 0
        done = existing
        with open(dest, mode) as f:
            while True:
                chunk = r.read(1 << 20)  # 1 MB
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                pct = f"{done/total*100:5.1f}%" if total else "  ?  "
                sys.stdout.write(f"\r    {name}: {pct} ({_human(done)})   ")
                sys.stdout.flush()
    print(f"\n[+] Saved {dest} ({_human(dest.stat().st_size)})")


def main():
    ap = argparse.ArgumentParser(description="Download AlphaMissense data (Zenodo 8208688).")
    ap.add_argument("--file", default="hg38", choices=list(FILES), help="which file to download")
    ap.add_argument("--list", action="store_true", help="list available files and exit")
    args = ap.parse_args()

    if args.list:
        print("Available AlphaMissense files (CC BY-NC-SA 4.0):")
        for key, (fname, desc) in FILES.items():
            print(f"  {key:18s} {desc}  [{fname}]")
        return 0

    fname, desc = FILES[args.file]
    print(f"[*] Downloading {fname} ({desc})")
    print("    License: CC BY-NC-SA 4.0 (non-commercial). Do not commit or redistribute.")
    download(fname, OUT_DIR / fname)
    return 0


if __name__ == "__main__":
    sys.exit(main())
