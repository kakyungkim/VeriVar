"""Self-consistency voting for Mode A (LLM) classification.

LLM output is non-deterministic, so we sample the classifier several times and
take a majority vote per axis. The agreement fraction becomes a calibrated
confidence: variants where the runs disagree are low-confidence and good
candidates for review. ``aggregate_votes`` is pure so the logic is unit-tested
without any LLM calls.
"""
from collections import Counter
from typing import List

from src.models import ClassificationResult


def aggregate_votes(results: List[ClassificationResult]) -> ClassificationResult:
    if not results:
        raise ValueError("no results to aggregate")
    n = len(results)
    onc_counts = Counter(r.oncogenicity for r in results)
    tier_counts = Counter(r.tier for r in results)
    top_onc, onc_n = onc_counts.most_common(1)[0]
    top_tier, tier_n = tier_counts.most_common(1)[0]

    # Representative run matching the majority on both axes (for level/rationale/citations).
    rep = next((r for r in results if r.oncogenicity == top_onc and r.tier == top_tier), results[0])
    agreement = round((onc_n + tier_n) / (2 * n), 3)
    abstained = sum(r.abstained for r in results) > n / 2

    return ClassificationResult(
        oncogenicity=top_onc,
        oncogenicity_codes=rep.oncogenicity_codes,
        tier=top_tier,
        tier_level=rep.tier_level,
        rationale=rep.rationale,
        citations=rep.citations,
        confidence=agreement,
        abstained=abstained,
    )
