from pydantic import BaseModel, Field
from typing import List

class VariantInterpretation(BaseModel):
    gene: str = ""
    variant: str
    variant_type: str
    vaf: float = Field(0.0, description="Variant Allele Frequency")
    
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
    
    # Omics Context
    rna_expression_level: str = Field("", description="e.g. 'high', 'low', 'normal'")
    tme_context: str = Field("", description="Tumor microenvironment context from scRNA-seq")
    
    variants: List[VariantInterpretation]
    
    overall_summary: str
    limitations: str
