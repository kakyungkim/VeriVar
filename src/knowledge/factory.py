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


def build_aggregator(offline: bool = True, am_online: bool = False) -> EvidenceAggregator:
    """Build the default evidence aggregator.

    Args:
        offline: keep the structured sources / trial enricher on the committed
            snapshots (no network). Default ``True`` for reproducibility.
        am_online: when ``True``, build the AlphaMissense annotator with
            ``offline=False`` so it can fetch live GRCh38/GRCh37 scores from the
            Ensembl VEP REST API on a cache miss (and populate the cache),
            **while CIViC/DGIdb/trials stay on the committed snapshots**. This is
            for the bring-your-own-VCF upload path (already online via VEP
            annotation); the cohort/offline pipeline leaves this ``False``.
    """
    return EvidenceAggregator(
        sources=[CivicSource(), DgidbSource()],
        trial_enricher=ClinicalTrialsSource(offline=offline),
        variant_annotators=[AlphaMissenseAnnotator(offline=offline and not am_online)],
    )
