"""International standard classification vocabularies for somatic variants.

Two complementary axes (the project's canonical terminology — replaces the
ad-hoc ``candidate_Tier_*`` / free-text ``Tier`` strings):

* **Oncogenicity** — ClinGen/CGC/VICC 2022 (Horak et al., Genet Med 2022).
  Five-class scale derived from a point-based evidence code system.
* **Clinical actionability tier** — AMP/ASCO/CAP 2017 (Li et al., J Mol Diagn
  2017). Four tiers; Tier I/II additionally carry an evidence Level (A–D).

NOTE: ACMG/AMP 2015 (Richards et al.) is the *germline* pathogenicity standard
and is intentionally NOT used here — its somatic analogue is the VICC scale.
"""
from enum import Enum


class VICCOncogenicity(str, Enum):
    """ClinGen/CGC/VICC 2022 somatic oncogenicity classes."""
    ONCOGENIC = "Oncogenic"
    LIKELY_ONCOGENIC = "Likely Oncogenic"
    VUS = "VUS"  # Variant of Uncertain Significance
    LIKELY_BENIGN = "Likely Benign"
    BENIGN = "Benign"


class VICCEvidenceCode(str, Enum):
    """ClinGen/CGC/VICC oncogenicity evidence codes (point-based system).

    Used by the rule/reasoning classifier and by the foundation-model
    computational evidence (e.g. AlphaMissense -> OP1 / SBP1).
    """
    # Oncogenic — Very Strong / Strong / Moderate / Supporting
    OVS1 = "OVS1"
    OS1 = "OS1"
    OS2 = "OS2"
    OS3 = "OS3"
    OM1 = "OM1"
    OM2 = "OM2"
    OM3 = "OM3"
    OM4 = "OM4"
    OP1 = "OP1"  # computational evidence predicts oncogenic impact
    OP2 = "OP2"
    OP3 = "OP3"
    OP4 = "OP4"
    # Benign — Very Strong / Strong / Supporting
    SBVS1 = "SBVS1"
    SBS1 = "SBS1"
    SBS2 = "SBS2"
    SBP1 = "SBP1"  # computational evidence predicts benign / no impact
    SBP2 = "SBP2"


class AMPTier(str, Enum):
    """AMP/ASCO/CAP 2017 clinical significance tiers."""
    TIER_I = "Tier I"      # Variants of Strong Clinical Significance
    TIER_II = "Tier II"    # Variants of Potential Clinical Significance
    TIER_III = "Tier III"  # Variants of Unknown Clinical Significance (VUS)
    TIER_IV = "Tier IV"    # Benign or Likely Benign


class AMPLevel(str, Enum):
    """AMP/ASCO/CAP evidence levels (apply within Tier I / Tier II)."""
    A = "Level A"  # FDA-approved / professional guidelines, same tumor type
    B = "Level B"  # well-powered studies with consensus
    C = "Level C"  # FDA-approved for a different tumor type / clinical trials
    D = "Level D"  # preclinical / case reports / biological plausibility


# Convenience groupings used across the classifier and tests.
ONCOGENIC_CLASSES = {VICCOncogenicity.ONCOGENIC, VICCOncogenicity.LIKELY_ONCOGENIC}
BENIGN_CLASSES = {VICCOncogenicity.LIKELY_BENIGN, VICCOncogenicity.BENIGN}
