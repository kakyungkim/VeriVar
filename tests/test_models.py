"""Tests for the canonical 2-axis domain models (Phase 1)."""
import pytest
from pydantic import ValidationError

from src.models import (
    AMPTier,
    AMPLevel,
    VICCOncogenicity,
    Evidence,
    EvidenceBundle,
    DrugAssociation,
    Variant,
    MultiOmicsContext,
    InterpretationMode,
    ClassificationResult,
    VariantInterpretation,
    VariantModeComparison,
    CohortInterpretation,
)


def test_standard_enum_values():
    assert VICCOncogenicity.LIKELY_ONCOGENIC.value == "Likely Oncogenic"
    assert AMPTier.TIER_I.value == "Tier I"
    assert AMPLevel.A.value == "Level A"


def test_variant_key():
    v = Variant(chrom="chr7", pos=140753336, ref="A", alt="T", gene="BRAF", hgvsp="p.V600E")
    assert v.key == "BRAF p.V600E"
    # Falls back to hgvsc then alt when protein change is absent.
    assert Variant(chrom="c", pos=1, ref="A", alt="G", gene="X").key == "X G"


def test_evidence_bundle_has_evidence_and_citations():
    empty = EvidenceBundle(variant_key="DDX11L1 p.X")
    assert empty.has_evidence is False
    assert empty.citation_ids() == []

    bundle = EvidenceBundle(
        variant_key="BRAF p.V600E",
        evidences=[Evidence(id="CIViC:EID12", source="CIViC", statement="oncogenic")],
        drugs=[DrugAssociation(drug="Vemurafenib", source="CIViC")],
    )
    assert bundle.has_evidence is True
    assert bundle.citation_ids() == ["CIViC:EID12"]


def test_classification_confidence_bounds():
    with pytest.raises(ValidationError):
        ClassificationResult(oncogenicity=VICCOncogenicity.VUS, tier=AMPTier.TIER_III, confidence=1.5)


def test_unsupported_citations_flags_hallucination():
    bundle = EvidenceBundle(
        variant_key="BRAF p.V600E",
        evidences=[Evidence(id="CIViC:EID12", source="CIViC")],
    )
    vi = VariantInterpretation(
        variant=Variant(chrom="c", pos=1, ref="A", alt="T", gene="BRAF", hgvsp="p.V600E"),
        mode=InterpretationMode.LLM,
        classification=ClassificationResult(
            oncogenicity=VICCOncogenicity.ONCOGENIC,
            tier=AMPTier.TIER_I,
            tier_level=AMPLevel.A,
            citations=["CIViC:EID12", "CIViC:EID999"],  # second id is fabricated
        ),
        evidence_bundle=bundle,
    )
    assert vi.unsupported_citations() == ["CIViC:EID999"]


def test_mode_comparison_discordance():
    concordant = VariantModeComparison(
        variant_key="X", llm_tier=AMPTier.TIER_I, rule_tier=AMPTier.TIER_I,
    )
    assert concordant.discordant is False

    discordant = VariantModeComparison(
        variant_key="DDX11L1",
        llm_oncogenicity=VICCOncogenicity.VUS,
        rule_oncogenicity=VICCOncogenicity.LIKELY_ONCOGENIC,
        oncogenicity_concordant=False,
    )
    assert discordant.discordant is True


def test_cohort_discordance_rate():
    cohort = CohortInterpretation(
        comparisons=[
            VariantModeComparison(variant_key="a"),
            VariantModeComparison(variant_key="b", tier_concordant=False),
        ]
    )
    assert cohort.discordance_rate == 0.5
    assert CohortInterpretation().discordance_rate is None


def test_multiomics_context_reserves_slots():
    ctx = MultiOmicsContext(sample_id="S1", cancer_type="Melanoma")
    assert ctx.genomic_variants == []
    # Reserved slots default to None until Phase 9.
    assert ctx.cnv is None and ctx.expression is None and ctx.methylation is None and ctx.tme is None
