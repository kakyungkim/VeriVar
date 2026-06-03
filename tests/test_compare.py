"""Tests for dual-mode comparison (Phase 4)."""
from src.models import AMPTier, ClassificationResult, Variant, VICCOncogenicity
from src.compare.dualmode import compare, discordance_summary


def _v(cancer="Melanoma"):
    return Variant(chrom="7", pos=1, ref="A", alt="T", gene="BRAF", hgvsp="p.V600E",
                   cancer_type=cancer, variant_type="SNV")


def _r(onc, tier):
    return ClassificationResult(oncogenicity=onc, tier=tier)


def test_compare_concordant_and_discordant():
    c1 = compare(_v(), _r(VICCOncogenicity.ONCOGENIC, AMPTier.TIER_I),
                 _r(VICCOncogenicity.ONCOGENIC, AMPTier.TIER_I))
    assert c1.discordant is False

    c2 = compare(_v(), _r(VICCOncogenicity.ONCOGENIC, AMPTier.TIER_I),
                 _r(VICCOncogenicity.LIKELY_ONCOGENIC, AMPTier.TIER_II))
    assert c2.oncogenicity_concordant is False and c2.tier_concordant is False
    assert c2.discordant is True


def test_discordance_summary_by_cancer():
    comps = [
        compare(_v("Melanoma"), _r(VICCOncogenicity.ONCOGENIC, AMPTier.TIER_I),
                _r(VICCOncogenicity.ONCOGENIC, AMPTier.TIER_I)),
        compare(_v("Colorectal"), _r(VICCOncogenicity.ONCOGENIC, AMPTier.TIER_I),
                _r(VICCOncogenicity.ONCOGENIC, AMPTier.TIER_II)),  # tier discordant
    ]
    s = discordance_summary(comps)
    assert s["overall"]["n"] == 2
    assert s["overall"]["tier_discordant"] == 1
    assert s["by_cancer"]["Colorectal"]["tier_discordant"] == 1
    assert len(s["discordant_variants"]) == 1
