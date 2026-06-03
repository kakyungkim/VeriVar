"""Default evidence aggregator wiring (offline by default).

Bundles the structured sources (CIViC, DGIdb), the AlphaMissense variant
annotator, and the ClinicalTrials enricher into one EvidenceAggregator using the
committed local snapshots — so the pipeline runs without network.
"""
from src.knowledge.aggregator import EvidenceAggregator
from src.knowledge.civic import CivicSource
from src.knowledge.dgidb import DgidbSource
from src.knowledge.alphamissense import AlphaMissenseAnnotator
from src.knowledge.clinical_trials import ClinicalTrialsSource


def build_aggregator(offline: bool = True) -> EvidenceAggregator:
    return EvidenceAggregator(
        sources=[CivicSource(), DgidbSource()],
        trial_enricher=ClinicalTrialsSource(offline=offline),
        variant_annotators=[AlphaMissenseAnnotator(offline=offline)],
    )
