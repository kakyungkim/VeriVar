"""Tests for self-consistency vote aggregation (pure, no LLM)."""
import pytest

from src.models import AMPTier, AMPLevel, ClassificationResult, VICCOncogenicity
from src.classify.voting import aggregate_votes


def _r(onc, tier, level=None, abstained=False, citations=None):
    return ClassificationResult(oncogenicity=onc, tier=tier, tier_level=level,
                                abstained=abstained, citations=citations or [])


def test_unanimous_gives_full_confidence():
    res = aggregate_votes([_r(VICCOncogenicity.ONCOGENIC, AMPTier.TIER_I)] * 3)
    assert res.oncogenicity == VICCOncogenicity.ONCOGENIC
    assert res.tier == AMPTier.TIER_I
    assert res.confidence == 1.0


def test_majority_vote_per_axis_and_confidence():
    runs = [
        _r(VICCOncogenicity.ONCOGENIC, AMPTier.TIER_I),
        _r(VICCOncogenicity.ONCOGENIC, AMPTier.TIER_II),
        _r(VICCOncogenicity.LIKELY_ONCOGENIC, AMPTier.TIER_I),
    ]
    res = aggregate_votes(runs)
    # oncogenicity: 2x Oncogenic wins; tier: 2x Tier I wins.
    assert res.oncogenicity == VICCOncogenicity.ONCOGENIC
    assert res.tier == AMPTier.TIER_I
    # agreement = (2 + 2) / (2*3) = 0.667
    assert res.confidence == pytest.approx(0.667, abs=0.01)


def test_abstention_majority():
    runs = [_r(VICCOncogenicity.VUS, AMPTier.TIER_III, abstained=True),
            _r(VICCOncogenicity.VUS, AMPTier.TIER_III, abstained=True),
            _r(VICCOncogenicity.LIKELY_ONCOGENIC, AMPTier.TIER_III, abstained=False)]
    res = aggregate_votes(runs)
    assert res.abstained is True
    assert res.tier == AMPTier.TIER_III


def test_representative_carries_level_and_citations():
    runs = [_r(VICCOncogenicity.ONCOGENIC, AMPTier.TIER_I, AMPLevel.A, citations=["CIViC:EID1"]),
            _r(VICCOncogenicity.ONCOGENIC, AMPTier.TIER_I, AMPLevel.A, citations=["CIViC:EID1"]),
            _r(VICCOncogenicity.VUS, AMPTier.TIER_III)]
    res = aggregate_votes(runs)
    assert res.tier_level == AMPLevel.A
    assert res.citations == ["CIViC:EID1"]


def test_empty_raises():
    with pytest.raises(ValueError):
        aggregate_votes([])
