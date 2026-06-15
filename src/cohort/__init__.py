"""Cohort loading: cBioPortal snapshots -> canonical Variant objects."""
from src.cohort.loader import (
    is_candidate,
    variants_from_snapshot,
    load_snapshot,
    load_cohort,
    variants_by_sample,
)
from src.cohort.vcf_loader import (
    detect_assembly,
    parse_vcf,
    annotate_variants,
)

__all__ = [
    "is_candidate",
    "variants_from_snapshot",
    "load_snapshot",
    "load_cohort",
    "variants_by_sample",
    "detect_assembly",
    "parse_vcf",
    "annotate_variants",
]
