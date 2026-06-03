"""EvidenceAggregator — merge all knowledge sources into one EvidenceBundle.

This is the structured arm of the hybrid retrieval layer and the direct
replacement for the old fabricating MockRAGDatabase. If every source returns
nothing for a variant (e.g. a pseudogene), the bundle is empty and
``has_evidence`` is False — which the classifier reads as a signal to abstain
(VUS) rather than inventing oncogenic support.
"""
from typing import List, Optional

from src.models import ClinicalTrial, DrugAssociation, Evidence, EvidenceBundle, Variant
from src.knowledge.base import KnowledgeSource


class EvidenceAggregator:
    def __init__(self, sources: List[KnowledgeSource], trial_enricher=None,
                 variant_annotators=None):
        self.sources = sources
        # Optional ClinicalTrialsSource: turns CIViC NCT ids into full trial
        # records (title/status/phase). Offline-safe by default.
        self.trial_enricher = trial_enricher
        # Optional coordinate-level annotators (e.g. AlphaMissenseAnnotator) that
        # take a full Variant; only used by for_variant_obj.
        self.variant_annotators = variant_annotators or []

    def for_variant(self, gene: str, protein_change: str, cancer_type: Optional[str] = None) -> EvidenceBundle:
        evidences: List[Evidence] = []
        drugs: List[DrugAssociation] = []
        trials: List[ClinicalTrial] = []
        for src in self.sources:
            evidences.extend(src.evidence(gene, protein_change, cancer_type))
            drugs.extend(src.drugs(gene, protein_change, cancer_type))
            trials.extend(src.trials(gene, protein_change, cancer_type))

        trials = _dedup_trials(trials)
        if self.trial_enricher is not None and trials:
            trials = self.trial_enricher.enrich([t.nct_id for t in trials])

        key = f"{gene} {protein_change}".strip()
        return EvidenceBundle(
            variant_key=key,
            evidences=evidences,
            drugs=_dedup_drugs(drugs),
            trials=trials,
        )

    def for_variant_obj(self, variant: Variant) -> EvidenceBundle:
        bundle = self.for_variant(variant.gene, variant.hgvsp, variant.cancer_type)
        # Coordinate-level annotators (AlphaMissense, etc.) need the full Variant.
        for ann in self.variant_annotators:
            bundle.evidences.extend(ann.evidence_for_variant(variant))
        return bundle


def _dedup_drugs(drugs: List[DrugAssociation]) -> List[DrugAssociation]:
    """Merge by (drug, source); keep first, union citations."""
    merged = {}
    for d in drugs:
        k = (d.drug.upper(), d.source)
        if k in merged:
            existing = merged[k]
            existing.citations = list(dict.fromkeys(existing.citations + d.citations))
        else:
            merged[k] = d
    return list(merged.values())


def _dedup_trials(trials: List[ClinicalTrial]) -> List[ClinicalTrial]:
    seen, out = set(), []
    for t in trials:
        if t.nct_id not in seen:
            seen.add(t.nct_id)
            out.append(t)
    return out
