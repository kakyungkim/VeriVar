"""Tests for verifier verdict application (pure, no LLM)."""
from src.models import AMPLevel, AMPTier, ClassificationResult, VICCOncogenicity
from src.classify.verify import VerifierVerdict, apply_verdict


def _result():
    return ClassificationResult(oncogenicity=VICCOncogenicity.LIKELY_ONCOGENIC,
                                tier=AMPTier.TIER_II, tier_level=AMPLevel.C,
                                rationale="base", confidence=0.9)


def test_supported_verdict_is_noop():
    r = _result()
    out = apply_verdict(r, VerifierVerdict(supported=True, reason="ok"))
    assert out.tier == AMPTier.TIER_II and out.confidence == 0.9


def test_refuted_downgrades_to_suggested_tier():
    out = apply_verdict(_result(), VerifierVerdict(
        supported=False, reason="no variant-specific sensitivity evidence",
        suggested_tier=AMPTier.TIER_III))
    assert out.tier == AMPTier.TIER_III
    assert out.tier_level is None              # cleared for Tier III
    assert out.confidence <= 0.5
    assert "Verifier:" in out.rationale


def test_refuted_without_suggestion_defaults_tier_iii():
    out = apply_verdict(_result(), VerifierVerdict(supported=False, reason="overcall"))
    assert out.tier == AMPTier.TIER_III
