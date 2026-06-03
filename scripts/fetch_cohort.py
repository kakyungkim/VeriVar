"""Fetch a small, reproducible multi-cancer cohort from cBioPortal (public).

Uses the cBioPortal REST API (no login, no key) instead of the S3 datahub
tarballs (which block anonymous access). For each of the 5 cancer studies it
pulls mutations in a curated driver-gene panel, then selects ~6-8 samples per
cancer, *guaranteeing* the showcase variants needed for the dual-mode story
(notably BRAF V600E in BOTH melanoma and colorectal -> same variant, different
actionability tier).

Outputs (committed for offline reproducibility):
  data/cohorts/<study>.json        per-study snapshot (selected samples+mutations)
  data/cohorts/cohort_manifest.json provenance + selection summary

Run:  python -m scripts.fetch_cohort
"""
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

API = "https://www.cbioportal.org/api"
OUT_DIR = Path("data/cohorts")
SAMPLES_PER_STUDY = 7

# study_id -> (cancer_type label, showcase protein changes to guarantee)
STUDIES = {
    "luad_tcga_pan_can_atlas_2018": ("Lung Adenocarcinoma (NSCLC)", {"EGFR": ["L858R"], "KRAS": ["G12C", "G12D", "G12V"]}),
    "brca_tcga_pan_can_atlas_2018": ("Breast Carcinoma", {"PIK3CA": ["H1047R", "E545K"], "TP53": []}),
    "coadread_tcga_pan_can_atlas_2018": ("Colorectal Adenocarcinoma", {"BRAF": ["V600E"], "KRAS": ["G12D", "G12V", "G13D"]}),
    "skcm_tcga_pan_can_atlas_2018": ("Cutaneous Melanoma", {"BRAF": ["V600E"], "NRAS": ["Q61R", "Q61K"]}),
    "paad_tcga_pan_can_atlas_2018": ("Pancreatic Adenocarcinoma", {"KRAS": ["G12D", "G12V"], "TP53": []}),
}

# Curated driver-gene panel (union across the 5 cancers) — keeps the cohort
# candidate-focused and small for LLM cost control.
GENE_PANEL = [
    "TP53", "KRAS", "NRAS", "BRAF", "PIK3CA", "PTEN", "EGFR", "ERBB2", "MET",
    "ALK", "ROS1", "RET", "AKT1", "ESR1", "GATA3", "CDH1", "MAP3K1", "APC",
    "SMAD4", "FBXW7", "KIT", "NF1", "CDKN2A", "STK11", "KEAP1", "BRCA1", "BRCA2",
]


def _post(url: str, payload) -> list:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _get(url: str) -> list:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def resolve_entrez(symbols: List[str]) -> Dict[str, int]:
    genes = _post(f"{API}/genes/fetch?geneIdType=HUGO_GENE_SYMBOL", symbols)
    return {g["hugoGeneSymbol"]: g["entrezGeneId"] for g in genes}


def fetch_study_mutations(study: str, entrez_ids: List[int]) -> List[dict]:
    mp = f"{study}_mutations"
    url = f"{API}/molecular-profiles/{mp}/mutations/fetch?projection=DETAILED"
    raw = _post(url, {"sampleListId": f"{study}_all", "entrezGeneIds": entrez_ids})
    out = []
    for m in raw:
        out.append({
            "sample_id": m.get("sampleId"),
            "gene": (m.get("gene") or {}).get("hugoGeneSymbol", ""),
            "chrom": str(m.get("chr", "")),
            "pos": m.get("startPosition"),
            "ref": m.get("referenceAllele", ""),
            "alt": m.get("variantAllele", ""),
            "protein_change": m.get("proteinChange", ""),
            "mutation_type": m.get("mutationType", ""),
            "variant_type": m.get("variantType", ""),
        })
    return out


PER_TARGET = 2  # guarantee up to this many carriers of each showcase variant


def select_samples(mutations: List[dict], showcase: Dict[str, List[str]]) -> List[str]:
    """Deterministically pick samples, *guaranteeing* representation of each
    showcase variant in priority order before filling by driver count.

    This is what keeps BRAF V600E present in BOTH melanoma and colorectal (the
    same-variant / different-tier contrast), instead of one cancer's slots being
    consumed by a more frequent driver (e.g. KRAS) first.
    """
    by_sample: Dict[str, List[dict]] = {}
    for m in mutations:
        by_sample.setdefault(m["sample_id"], []).append(m)

    def carriers(gene: str, variants: List[str]) -> List[str]:
        hits = []
        for s, muts in by_sample.items():
            for mut in muts:
                if mut["gene"] == gene and (not variants or mut["protein_change"] in variants):
                    hits.append(s)
                    break
        return sorted(hits)

    selected: List[str] = []
    # 1) Guarantee each showcase target (dict order = priority) gets a few carriers.
    for gene, variants in showcase.items():
        for s in carriers(gene, variants):
            if len([x for x in selected if x in carriers(gene, variants)]) >= PER_TARGET:
                break
            if s not in selected and len(selected) < SAMPLES_PER_STUDY:
                selected.append(s)

    # 2) Fill remaining slots by driver count (desc), tie-break by id.
    others = sorted((s for s in by_sample if s not in selected),
                    key=lambda s: (-len(by_sample[s]), s))
    for s in others:
        if len(selected) >= SAMPLES_PER_STUDY:
            break
        selected.append(s)
    return sorted(selected)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entrez = resolve_entrez(GENE_PANEL)
    entrez_ids = sorted(entrez.values())
    print(f"[*] Resolved {len(entrez_ids)} panel genes.")

    manifest = {
        "source": "cBioPortal REST API (https://www.cbioportal.org/api)",
        "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gene_panel": GENE_PANEL,
        "samples_per_study": SAMPLES_PER_STUDY,
        "studies": {},
    }

    for study, (cancer_type, showcase) in STUDIES.items():
        try:
            muts = fetch_study_mutations(study, entrez_ids)
        except Exception as e:  # noqa: BLE001 - report and continue to next study
            print(f"[!] {study}: fetch failed ({e}); skipping.")
            continue
        selected = select_samples(muts, showcase)
        sel_muts = [m for m in muts if m["sample_id"] in selected]
        snapshot = {
            "study_id": study,
            "cancer_type": cancer_type,
            "samples": selected,
            "n_mutations": len(sel_muts),
            "mutations": sel_muts,
        }
        (OUT_DIR / f"{study}.json").write_text(json.dumps(snapshot, indent=2))
        manifest["studies"][study] = {
            "cancer_type": cancer_type,
            "n_samples": len(selected),
            "n_mutations": len(sel_muts),
            "samples": selected,
        }
        print(f"[+] {study}: {len(selected)} samples, {len(sel_muts)} panel mutations.")

    (OUT_DIR / "cohort_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"[+] Cohort written to {OUT_DIR}/ ({len(manifest['studies'])} studies).")


if __name__ == "__main__":
    sys.exit(main())
