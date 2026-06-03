"""Canonical domain models for the somatic variant interpretation pipeline.

This package is the single source of truth for the 2-axis classification
standard and the evidence/interpretation schema. (The legacy
``src/parser/models.py`` is retained only until the LLM/rule layers migrate in
Phases 2-4, then removed.)
"""
from src.models.standards import (
    AMPLevel,
    AMPTier,
    VICCEvidenceCode,
    VICCOncogenicity,
    ONCOGENIC_CLASSES,
    BENIGN_CLASSES,
)
from src.models.evidence import (
    Modality,
    Evidence,
    DrugAssociation,
    ClinicalTrial,
    EvidenceBundle,
)
from src.models.omics import Variant, MultiOmicsContext, OmicsAnnotator
from src.models.interpretation import (
    InterpretationMode,
    ClassificationResult,
    VariantInterpretation,
    SampleInterpretation,
    Provenance,
    VariantModeComparison,
    CohortInterpretation,
)

__all__ = [
    "AMPLevel",
    "AMPTier",
    "VICCEvidenceCode",
    "VICCOncogenicity",
    "ONCOGENIC_CLASSES",
    "BENIGN_CLASSES",
    "Modality",
    "Evidence",
    "DrugAssociation",
    "ClinicalTrial",
    "EvidenceBundle",
    "Variant",
    "MultiOmicsContext",
    "OmicsAnnotator",
    "InterpretationMode",
    "ClassificationResult",
    "VariantInterpretation",
    "SampleInterpretation",
    "Provenance",
    "VariantModeComparison",
    "CohortInterpretation",
]
