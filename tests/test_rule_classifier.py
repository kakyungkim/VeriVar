"""Tests for the direction-aware 2-axis rule classifier (Mode B, Phase 4a)."""
from src.models import (
    AMPLevel, AMPTier, DrugAssociation, Evidence, EvidenceBundle, Variant,
    VICCOncogenicity,
)
from src.classify.rules import RuleClassifier


def _variant(cancer="Cutaneous Melanoma"):
    return Variant(chrom="7", pos=140453136, ref="A", alt="T", gene="BRAF",
                   hgvsp="p.V600E", cancer_type=cancer, variant_type="SNV")


def _civic(level="A", disease="Melanoma", direction="Supports",
           significance="Sensitivity/Response", etype="Predictive", eid="EID1"):
    return Evidence(id=f"CIViC:{eid}", source="CIViC", gene="BRAF", variant="V600E",
                    disease=disease, statement="...", evidence_level=level,
                    direction=direction, evidence_type=etype, significance=significance)


def _am(score):
    return Evidence(id="AlphaMissense:x", source="AlphaMissense", score=score, statement="...")


def _drug():
    return DrugAssociation(drug="Vemurafenib", source="CIViC")


def test_actionable_same_cancer_is_tier_i_oncogenic():
    bundle = EvidenceBundle(variant_key="BRAF V600E", evidences=[_civic("A", "Melanoma")],
                            drugs=[_drug()])
    res = RuleClassifier().classify(_variant("Cutaneous Melanoma"), bundle)
    assert res.oncogenicity == VICCOncogenicity.ONCOGENIC
    assert res.tier == AMPTier.TIER_I and res.tier_level == AMPLevel.A
    assert res.abstained is False
    assert res.citations == ["CIViC:EID1"]


def test_actionable_different_cancer_is_tier_ii():
    bundle = EvidenceBundle(variant_key="BRAF V600E", evidences=[_civic("A", "Melanoma")],
                            drugs=[_drug()])
    res = RuleClassifier().classify(_variant("Colorectal Adenocarcinoma"), bundle)
    assert res.tier == AMPTier.TIER_II          # context-dependent tiering
    assert res.oncogenicity == VICCOncogenicity.ONCOGENIC


def test_unaltered_function_is_not_oncogenic():
    # EGFR E114K case: Functional / Supports / Unaltered Function -> benign-leaning.
    bundle = EvidenceBundle(
        variant_key="EGFR E114K",
        evidences=[_civic(level="D", significance="Unaltered Function", etype="Functional")],
        drugs=[_drug()])  # gene-level drugs must NOT make it actionable
    res = RuleClassifier().classify(_variant(), bundle)
    assert res.oncogenicity == VICCOncogenicity.LIKELY_BENIGN
    assert res.tier == AMPTier.TIER_IV


def test_does_not_support_is_not_oncogenic():
    # TP53 P152L case: Functional / Does Not Support -> refuting, not supporting.
    bundle = EvidenceBundle(
        variant_key="TP53 P152L",
        evidences=[_civic(direction="Does Not Support", significance="Dominant Negative",
                          etype="Functional", level="D")])
    res = RuleClassifier().classify(_variant(), bundle)
    assert res.oncogenicity == VICCOncogenicity.LIKELY_BENIGN


def test_gene_level_drugs_alone_do_not_make_tier_ii():
    # AlphaMissense-pathogenic + gene-level drugs, but NO sensitivity evidence.
    bundle = EvidenceBundle(variant_key="X p.Y", evidences=[_am(0.98)],
                            drugs=[DrugAssociation(drug="Crizotinib", source="DGIdb")])
    res = RuleClassifier().classify(_variant(), bundle)
    assert res.oncogenicity == VICCOncogenicity.LIKELY_ONCOGENIC  # OP1
    assert res.tier == AMPTier.TIER_III          # not actionable without sensitivity evidence


def test_alphamissense_benign_is_likely_benign_tier_iv():
    bundle = EvidenceBundle(variant_key="X p.Y", evidences=[_am(0.10)])
    res = RuleClassifier().classify(_variant(), bundle)
    assert res.oncogenicity == VICCOncogenicity.LIKELY_BENIGN
    assert res.tier == AMPTier.TIER_IV


def test_no_evidence_abstains_vus_tier_iii():
    bundle = EvidenceBundle(variant_key="X p.Y")
    res = RuleClassifier().classify(_variant(), bundle)
    assert res.oncogenicity == VICCOncogenicity.VUS
    assert res.tier == AMPTier.TIER_III
    assert res.abstained is True
