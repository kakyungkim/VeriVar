"""Select which variants go to the (cost-bearing) LLM classifier.

The cohort has hundreds of candidate variants, many of them recurrences of the
same change. Interpretation is variant+context level, not sample level, so we:
  1. de-duplicate by (gene, protein change, cancer type),
  2. keep every variant with variant-specific evidence (CIViC / AlphaMissense),
  3. add a few no-evidence variants per cancer to showcase honest abstention.

This focuses LLM spend on meaningful, distinct interpretations.
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple

from src.models import EvidenceBundle, Variant
from src.knowledge.aggregator import EvidenceAggregator


@dataclass
class SelectedVariant:
    variant: Variant
    bundle: EvidenceBundle
    sample_ids: List[str]   # all cohort samples carrying this variant+context
    has_evidence: bool
    tier: str = ""          # 'civic' | 'alphamissense' | 'none' (evidence tier)


def dedup_key(v: Variant) -> Tuple[str, str, str]:
    return (v.gene.upper(), v.hgvsp.upper(), (v.cancer_type or "").lower())


def _evidence_tier(bundle: EvidenceBundle) -> str:
    if any(e.source == "CIViC" for e in bundle.evidences):
        return "civic"
    if any(e.source == "AlphaMissense" for e in bundle.evidences):
        return "alphamissense"
    return "none"


def select_for_classification(
    aggregator: EvidenceAggregator,
    variants: List[Variant],
    am_per_cancer: int = 4,
    abstain_per_cancer: int = 2,
) -> List[SelectedVariant]:
    """Tiered, cost-controlled selection:

    * ALL variants with CIViC clinical evidence (the dual-mode focus),
    * a capped sample of AlphaMissense-only variants per cancer (computational),
    * a few no-evidence variants per cancer (honest abstention showcase).
    """
    groups: Dict[Tuple[str, str, str], List[Variant]] = {}
    for v in variants:
        groups.setdefault(dedup_key(v), []).append(v)

    civic: List[SelectedVariant] = []
    am_pool: Dict[str, List[SelectedVariant]] = {}
    none_pool: Dict[str, List[SelectedVariant]] = {}

    for key, members in sorted(groups.items()):
        rep = members[0]
        bundle = aggregator.for_variant_obj(rep)
        tier = _evidence_tier(bundle)
        sample_ids = sorted({m.sample_id for m in members if m.sample_id})
        sel = SelectedVariant(rep, bundle, sample_ids, bundle.has_variant_evidence, tier)
        if tier == "civic":
            civic.append(sel)
        elif tier == "alphamissense":
            am_pool.setdefault(rep.cancer_type or "Unknown", []).append(sel)
        else:
            none_pool.setdefault(rep.cancer_type or "Unknown", []).append(sel)

    def _take(pool: Dict[str, List[SelectedVariant]], n: int) -> List[SelectedVariant]:
        out = []
        for cancer, lst in pool.items():
            lst.sort(key=lambda s: (-len(s.sample_ids), s.variant.key))  # recurrent first
            out.extend(lst[:n])
        return out

    return civic + _take(am_pool, am_per_cancer) + _take(none_pool, abstain_per_cancer)
