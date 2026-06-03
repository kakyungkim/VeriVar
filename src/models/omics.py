"""Variant + multi-omics context.

The pipeline is variant-level today. ``MultiOmicsContext`` reserves typed slots
for other modalities (CNV, expression, methylation, TME) and ``OmicsAnnotator``
defines the plug-in contract, so Phase 9 multi-omics integration (e.g. feeding
SCODA scRNA-seq h5ad outputs) adds annotators without reshaping the schema.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.models.evidence import Evidence, Modality


class Variant(BaseModel):
    """A single somatic variant (SNV/INDEL today; SV/fusion reserved)."""
    chrom: str
    pos: int
    ref: str
    alt: str
    gene: str = "Unknown"
    hgvsc: str = ""
    hgvsp: str = ""
    vaf: Optional[float] = None
    dp: Optional[int] = None
    variant_type: str = "SNV"
    sample_id: Optional[str] = None
    cancer_type: Optional[str] = None

    @property
    def key(self) -> str:
        """Canonical gene + protein-change retrieval key, e.g. 'BRAF p.V600E'."""
        change = self.hgvsp or self.hgvsc or self.alt
        return f"{self.gene} {change}".strip()


class MultiOmicsContext(BaseModel):
    """Per-sample omics context. Only ``genomic_variants`` is populated now;
    the remaining slots are reserved for Phase 9 (typed loosely as optional
    payloads until their own models land)."""
    sample_id: str
    cancer_type: Optional[str] = None
    genomic_variants: List[Variant] = Field(default_factory=list)
    # Reserved multi-omics slots (None until implemented):
    cnv: Optional[Dict[str, Any]] = Field(None, description="Copy-number state per gene")
    expression: Optional[Dict[str, Any]] = Field(None, description="mRNA expression / z-scores")
    methylation: Optional[Dict[str, Any]] = Field(None, description="e.g. MGMT promoter methylation")
    tme: Optional[Dict[str, Any]] = Field(None, description="Tumor microenvironment (scRNA-seq)")


class OmicsAnnotator(ABC):
    """Plug-in that contributes modality-tagged evidence for a sample.

    Phase 9 implements concrete annotators (ExpressionAnnotator, CnvAnnotator,
    ...). Each declares its modality and returns :class:`Evidence` items.
    """

    @property
    @abstractmethod
    def modality(self) -> Modality:  # pragma: no cover - interface
        ...

    @abstractmethod
    def annotate(self, context: MultiOmicsContext) -> List[Evidence]:  # pragma: no cover - interface
        ...
