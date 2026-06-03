"""Evidence model — the citable substrate for faithfulness/hallucination control.

Every retrieved fact is an :class:`Evidence` with a stable ``id``. LLM outputs
must cite these ids (see ``ClassificationResult.citations``); the NL chat layer
inherits the same rule. An empty :class:`EvidenceBundle` (``has_evidence`` is
False) drives abstention — e.g. a pseudogene with no oncogenic support is
classified VUS rather than fabricated as actionable.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Modality(str, Enum):
    """Omics modality an evidence/feature originates from.

    Only GENOMIC_SNV_INDEL is populated initially; the rest are reserved so the
    evidence layer extends to multi-omics (Phase 9) without schema changes.
    """
    GENOMIC_SNV_INDEL = "genomic_snv_indel"
    GENOMIC_CNV = "genomic_cnv"
    GENOMIC_SV_FUSION = "genomic_sv_fusion"
    TRANSCRIPTOMIC = "transcriptomic"
    EPIGENOMIC = "epigenomic"
    PROTEOMIC = "proteomic"
    IMMUNE = "immune"
    CLINICAL = "clinical"


class Evidence(BaseModel):
    """A single citable piece of retrieved evidence."""
    id: str = Field(..., description="Stable citation id, e.g. 'CIViC:EID1234'")
    source: str = Field(..., description="Knowledgebase, e.g. CIViC/ClinVar/DGIdb/AlphaMissense")
    modality: Modality = Modality.GENOMIC_SNV_INDEL
    gene: Optional[str] = None
    variant: Optional[str] = None
    disease: Optional[str] = None
    statement: str = Field("", description="Free-text evidence statement (RAG corpus unit)")
    evidence_level: Optional[str] = Field(None, description="Source-native level, e.g. CIViC 'B'")
    direction: Optional[str] = Field(None, description="Supports / Does Not Support, etc.")
    evidence_type: Optional[str] = Field(None, description="Predictive / Prognostic / Functional / Oncogenic, etc.")
    significance: Optional[str] = Field(None, description="e.g. Sensitivity/Response, Resistance, Unaltered Function")
    score: Optional[float] = Field(None, description="Numeric score where applicable (e.g. AlphaMissense)")
    pmids: List[str] = Field(default_factory=list)
    url: Optional[str] = None


class DrugAssociation(BaseModel):
    """A drug linked to a variant/gene by a knowledgebase."""
    drug: str
    source: str
    interaction_type: Optional[str] = None
    evidence_level: Optional[str] = None
    disease: Optional[str] = None
    citations: List[str] = Field(default_factory=list, description="Evidence ids supporting this drug link")


class ClinicalTrial(BaseModel):
    """A clinical trial record (e.g. from ClinicalTrials.gov API v2)."""
    nct_id: str
    title: str = ""
    status: Optional[str] = None
    phase: Optional[str] = None
    conditions: List[str] = Field(default_factory=list)
    interventions: List[str] = Field(default_factory=list)
    url: Optional[str] = None


class EvidenceBundle(BaseModel):
    """All evidence gathered for one variant by the hybrid retrieval layer."""
    variant_key: str = Field(..., description="gene + protein change key, e.g. 'BRAF p.V600E'")
    evidences: List[Evidence] = Field(default_factory=list)
    drugs: List[DrugAssociation] = Field(default_factory=list)
    trials: List[ClinicalTrial] = Field(default_factory=list)

    @property
    def has_evidence(self) -> bool:
        """True if ANY evidence/drug/trial was retrieved (useful for display)."""
        return bool(self.evidences or self.drugs or self.trials)

    @property
    def has_variant_evidence(self) -> bool:
        """True if VARIANT-SPECIFIC evidence exists (the abstention signal).

        Gene-level context (e.g. DGIdb drugs that target the gene regardless of
        the specific change) does NOT count: a random passenger variant in a
        druggable gene must still abstain. Only variant-keyed ``Evidence``
        statements (e.g. CIViC EIDs for this exact change) count here.
        """
        return bool(self.evidences)

    def citation_ids(self) -> List[str]:
        """Valid citation ids an LLM is allowed to reference for this variant."""
        return [e.id for e in self.evidences]
