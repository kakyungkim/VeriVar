"""Interpretation results: 2-axis classification, dual-mode comparison, provenance.

``ClassificationResult`` is the unit every classifier (rule or LLM, Mode A or B)
produces. Its ``citations`` / ``abstained`` / ``confidence`` fields are the
faithfulness + abstention contract: an LLM claim must cite evidence ids, and an
unsupported call abstains (VUS) rather than hallucinating.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.standards import AMPLevel, AMPTier, VICCEvidenceCode, VICCOncogenicity
from src.models.evidence import EvidenceBundle
from src.models.omics import Variant


class InterpretationMode(str, Enum):
    """Dual-mode design (README)."""
    LLM = "llm"    # Mode A: LLM assigns the classification
    RULE = "rule"  # Mode B: rules fix the classification, LLM explains


class ClassificationResult(BaseModel):
    """2-axis classification for one variant under one mode."""
    # Axis 1 — oncogenicity (VICC)
    oncogenicity: VICCOncogenicity
    oncogenicity_codes: List[VICCEvidenceCode] = Field(default_factory=list)
    # Axis 2 — clinical actionability (AMP/ASCO/CAP)
    tier: AMPTier
    tier_level: Optional[AMPLevel] = None
    # Reasoning + faithfulness contract
    rationale: str = ""
    citations: List[str] = Field(
        default_factory=list,
        description="Evidence ids supporting this call (must be valid bundle ids)",
    )
    # Uncertainty / abstention (conformal abstention in Phase 5)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    abstained: bool = Field(False, description="True when evidence was insufficient to classify")


class VariantInterpretation(BaseModel):
    """One variant interpreted under one mode, with its evidence."""
    variant: Variant
    mode: InterpretationMode
    classification: ClassificationResult
    evidence_bundle: Optional[EvidenceBundle] = None

    def unsupported_citations(self) -> List[str]:
        """Cited ids that are NOT backed by the evidence bundle (hallucination signal)."""
        if self.evidence_bundle is None:
            return list(self.classification.citations)
        valid = set(self.evidence_bundle.citation_ids())
        return [c for c in self.classification.citations if c not in valid]


class Provenance(BaseModel):
    """Run metadata for reproducibility/auditability (recorded on every output)."""
    model_config = {"protected_namespaces": ()}  # allow 'model_name' field

    mode_used: str = Field("live", description="'live' or 'mock' (no API key)")
    model_name: Optional[str] = None
    embedding_model: Optional[str] = None
    data_sources: dict = Field(default_factory=dict, description="source -> version/date")
    timestamp: Optional[str] = None
    seed: Optional[int] = None


class SampleInterpretation(BaseModel):
    """All variant interpretations for one sample (one mode)."""
    sample_id: str
    cancer_type: Optional[str] = None
    mode: InterpretationMode
    variant_interpretations: List[VariantInterpretation] = Field(default_factory=list)
    summary: str = ""
    provenance: Optional[Provenance] = None


class VariantModeComparison(BaseModel):
    """Per-variant agreement between Mode A (LLM) and Mode B (rule)."""
    variant_key: str
    cancer_type: Optional[str] = None
    llm_oncogenicity: Optional[VICCOncogenicity] = None
    rule_oncogenicity: Optional[VICCOncogenicity] = None
    llm_tier: Optional[AMPTier] = None
    rule_tier: Optional[AMPTier] = None
    oncogenicity_concordant: bool = True
    tier_concordant: bool = True

    @property
    def discordant(self) -> bool:
        return not (self.oncogenicity_concordant and self.tier_concordant)


class CohortInterpretation(BaseModel):
    """Top-level artifact across samples/cancer types (the single output object)."""
    cancer_types: List[str] = Field(default_factory=list)
    samples: List[SampleInterpretation] = Field(default_factory=list)
    comparisons: List[VariantModeComparison] = Field(default_factory=list)
    provenance: Optional[Provenance] = None

    @property
    def discordance_rate(self) -> Optional[float]:
        if not self.comparisons:
            return None
        return sum(c.discordant for c in self.comparisons) / len(self.comparisons)
