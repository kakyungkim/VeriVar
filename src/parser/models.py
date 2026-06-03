from pydantic import BaseModel, Field
from typing import List, Optional

class VariantInterpretation(BaseModel):
    gene: str = ""
    variant: str
    variant_type: str
    vaf: Optional[float] = Field(None, description="Variant Allele Frequency (None if unknown)")
    
    oncogenic_evidence: str
    potential_tier: str
    tier_basis: str
    
    requires_additional_validation: bool
    recommended_experiments: List[str] = Field(
        default_factory=list, description="Experimental validation suggestions (e.g. cell line assay)"
    )
    notes: str = ""

class SampleInterpretation(BaseModel):
    sample_id: str
    cancer_context: str = ""
    
    # Omics Context (optional, often absent at the variant level — formalized
    # into a MultiOmicsContext in Phase 1; kept Optional so unset == None).
    rna_expression_level: Optional[str] = Field(None, description="e.g. 'high', 'low', 'normal'")
    tme_context: Optional[str] = Field(None, description="Tumor microenvironment context from scRNA-seq")
    
    variants: List[VariantInterpretation]
    
    overall_summary: str
    limitations: str
