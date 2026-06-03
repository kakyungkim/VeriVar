"""Deterministic 2-axis classifier (Mode B) — evidence-driven, not gene-lookup.

Unlike the old gene-name table, this reads the retrieved EvidenceBundle and
applies transparent rules to produce both axes:
  * VICC oncogenicity  (Oncogenic / Likely Oncogenic / VUS / Likely Benign / Benign)
  * AMP/ASCO/CAP tier   (I-IV) with an evidence Level (A-D) for Tier I/II

When no variant-specific evidence exists, it abstains (VUS / Tier III) rather
than guessing — the same honest-abstention contract the LLM mode follows.
"""
from typing import List, Optional, Tuple

from src.models import (
    AMPLevel, AMPTier, ClassificationResult, EvidenceBundle, Variant,
    VICCEvidenceCode, VICCOncogenicity,
)

_LEVEL_RANK = {"A": 3, "B": 2, "C": 1, "D": 0}

# Significance values (CIViC) that REFUTE an oncogenic role rather than support it.
_BENIGN_SIG = {"unaltered function", "benign", "likely benign", "neutral"}
_SENSITIVITY_SIG = {"sensitivity/response", "reduced sensitivity"}


def _supports(e) -> bool:
    return (e.direction or "").strip().lower() == "supports"


def _is_actionable_sensitivity(e) -> bool:
    """A predictive evidence that the variant confers drug sensitivity (Supports)."""
    return (e.source == "CIViC" and _supports(e)
            and (e.significance or "").strip().lower() in _SENSITIVITY_SIG)


def _best_civic_level(evidences) -> Optional[str]:
    levels = [e.evidence_level for e in evidences
              if e.source == "CIViC" and e.evidence_level in _LEVEL_RANK]
    return max(levels, key=lambda l: _LEVEL_RANK[l]) if levels else None


def _alphamissense_code(bundle: EvidenceBundle) -> Optional[str]:
    for e in bundle.evidences:
        if e.source == "AlphaMissense" and e.score is not None:
            if e.score >= 0.564:
                return "OP1"
            if e.score <= 0.34:
                return "SBP1"
    return None


def _cancer_matches(evidences, cancer_type: Optional[str]) -> bool:
    if not cancer_type:
        return False
    ct = cancer_type.lower()
    keys = [w for w in ct.replace("(", " ").replace(")", " ").split() if len(w) > 3]
    for e in evidences:
        d = (e.disease or "").lower()
        if d and any(k in d for k in keys):
            return True
    return False


class RuleClassifier:
    """Transparent rule-based 2-axis classifier."""

    def classify(self, variant: Variant, bundle: EvidenceBundle) -> ClassificationResult:
        am_code = _alphamissense_code(bundle)
        codes: List[VICCEvidenceCode] = []
        if am_code:
            codes.append(VICCEvidenceCode(am_code))

        onco_n, benign_n = self._civic_signals(bundle)
        oncogenicity = self._oncogenicity(bundle, onco_n, benign_n, am_code)
        tier, level = self._tier(variant, bundle, oncogenicity)

        abstained = (not bundle.has_variant_evidence)
        rationale = self._rationale(onco_n, benign_n, am_code, bundle, oncogenicity, tier, level)
        return ClassificationResult(
            oncogenicity=oncogenicity,
            oncogenicity_codes=codes,
            tier=tier,
            tier_level=level,
            rationale=rationale,
            citations=bundle.citation_ids(),
            abstained=abstained,
        )

    @staticmethod
    def _civic_signals(bundle: EvidenceBundle) -> Tuple[int, int]:
        """Count CIViC evidence supporting vs refuting an oncogenic role.

        Direction-aware: 'Unaltered Function' (and other benign significances) and
        'Does Not Support' lines count AGAINST oncogenicity, instead of the old
        behaviour that treated any CIViC hit as support (which over-called e.g.
        EGFR E114K 'Unaltered Function' and TP53 P152L 'Does Not Support').
        """
        onco = benign = 0
        for e in bundle.evidences:
            if e.source != "CIViC":
                continue
            sig = (e.significance or "").strip().lower()
            if sig in _BENIGN_SIG or not _supports(e):
                benign += 1
            else:
                onco += 1
        return onco, benign

    def _oncogenicity(self, bundle, onco_n, benign_n, am_code) -> VICCOncogenicity:
        if onco_n > 0 and onco_n >= benign_n:
            sens = any(_is_actionable_sensitivity(e) for e in bundle.evidences)
            return (VICCOncogenicity.ONCOGENIC if (onco_n >= 2 or sens)
                    else VICCOncogenicity.LIKELY_ONCOGENIC)
        if benign_n > onco_n:
            return VICCOncogenicity.LIKELY_BENIGN
        # No net CIViC signal -> fall back to computational evidence.
        if am_code == "OP1":
            return VICCOncogenicity.LIKELY_ONCOGENIC
        if am_code == "SBP1":
            return VICCOncogenicity.LIKELY_BENIGN
        return VICCOncogenicity.VUS

    def _tier(self, variant, bundle, oncogenicity) -> Tuple[AMPTier, Optional[AMPLevel]]:
        if oncogenicity in (VICCOncogenicity.LIKELY_BENIGN, VICCOncogenicity.BENIGN):
            return AMPTier.TIER_IV, None
        # Actionability requires evidence the variant confers drug SENSITIVITY,
        # not just that the gene is druggable (gene-level DGIdb drugs don't count).
        sens_ev = [e for e in bundle.evidences if _is_actionable_sensitivity(e)]
        if sens_ev and bundle.drugs:
            best = _best_civic_level(sens_ev)
            same_cancer = _cancer_matches(sens_ev, variant.cancer_type)
            if same_cancer and best in ("A", "B"):
                return AMPTier.TIER_I, AMPLevel.A if best == "A" else AMPLevel.B
            level = {"A": AMPLevel.C, "B": AMPLevel.C, "C": AMPLevel.C}.get(best, AMPLevel.D)
            return AMPTier.TIER_II, level
        return AMPTier.TIER_III, None

    def _rationale(self, onco_n, benign_n, am_code, bundle, oncogenicity, tier, level) -> str:
        bits = []
        if onco_n or benign_n:
            bits.append(f"CIViC: {onco_n} supporting / {benign_n} refuting oncogenicity")
        sens = sum(_is_actionable_sensitivity(e) for e in bundle.evidences)
        if sens:
            bits.append(f"{sens} drug-sensitivity evidence item(s)")
        if am_code:
            bits.append(f"AlphaMissense {am_code}")
        if not bits:
            bits.append("no variant-specific evidence (abstained)")
        lvl = f" ({level.value})" if level else ""
        return (f"Rule-based: {oncogenicity.value}; {tier.value}{lvl}. "
                f"Basis: {', '.join(bits)}.")
