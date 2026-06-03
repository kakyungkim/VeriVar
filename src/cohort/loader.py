"""Load cBioPortal cohort snapshots into canonical ``Variant`` objects.

Reads the JSON snapshots produced by ``scripts/fetch_cohort.py`` (offline,
no network) and converts each mutation record into a
:class:`src.models.Variant`, tagging sample id + cancer type. A candidate
filter drops non-coding / silent calls so only interpretation-worthy variants
reach the (cost-bearing) LLM layer.
"""
import json
from pathlib import Path
from typing import Dict, List

from src.models import Variant

COHORT_DIR = Path("data/cohorts")

# cBioPortal mutationType values that are not candidate somatic drivers.
NON_CANDIDATE_TYPES = {
    "Silent", "3'UTR", "5'UTR", "3'Flank", "5'Flank", "Intron", "IGR",
    "RNA", "lincRNA", "Targeted_Region",
}


def _variant_type(mutation_type: str, variant_type: str) -> str:
    """Map cBioPortal type fields onto our SNV/INDEL classification."""
    vt = (variant_type or "").upper()
    if vt in {"SNP", "DNP", "TNP", "ONP", "MNP"}:
        return "SNV"
    if vt in {"INS", "DEL"}:
        return "INDEL"
    if "Frame" in mutation_type or "Ins" in mutation_type or "Del" in mutation_type:
        return "INDEL"
    return "SNV"


def is_candidate(record: dict) -> bool:
    """True if a mutation record is an interpretation candidate (coding, non-silent)."""
    if record.get("mutation_type") in NON_CANDIDATE_TYPES:
        return False
    # Require a protein change — keeps the LLM focused on protein-altering events.
    return bool(record.get("protein_change"))


def _to_variant(record: dict, cancer_type: str) -> Variant:
    pc = record.get("protein_change", "") or ""
    hgvsp = pc if (pc.startswith("p.") or not pc) else f"p.{pc}"
    return Variant(
        chrom=str(record.get("chrom", "")),
        pos=int(record["pos"]) if record.get("pos") is not None else 0,
        ref=record.get("ref", "") or "",
        alt=record.get("alt", "") or "",
        gene=record.get("gene", "Unknown") or "Unknown",
        hgvsp=hgvsp,
        variant_type=_variant_type(record.get("mutation_type", ""), record.get("variant_type", "")),
        sample_id=record.get("sample_id"),
        cancer_type=cancer_type,
    )


def variants_from_snapshot(snapshot: dict, candidates_only: bool = True) -> List[Variant]:
    """Convert one study snapshot dict into Variant objects."""
    cancer_type = snapshot.get("cancer_type")
    out = []
    for rec in snapshot.get("mutations", []):
        if candidates_only and not is_candidate(rec):
            continue
        out.append(_to_variant(rec, cancer_type))
    return out


def load_snapshot(path) -> dict:
    return json.loads(Path(path).read_text())


def load_cohort(cohort_dir=COHORT_DIR, candidates_only: bool = True) -> List[Variant]:
    """Load every study snapshot in a directory into a flat Variant list."""
    cohort_dir = Path(cohort_dir)
    variants: List[Variant] = []
    for path in sorted(cohort_dir.glob("*.json")):
        if path.name == "cohort_manifest.json":
            continue
        variants.extend(variants_from_snapshot(load_snapshot(path), candidates_only))
    return variants


def variants_by_sample(variants: List[Variant]) -> Dict[str, List[Variant]]:
    """Group variants by sample id (preserves input order within a sample)."""
    grouped: Dict[str, List[Variant]] = {}
    for v in variants:
        grouped.setdefault(v.sample_id or "UNKNOWN", []).append(v)
    return grouped
