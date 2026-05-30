import pandas as pd

def assign_guideline_tier(row: pd.Series) -> str:
    """
    Deterministically assigns an AMP/ASCO/CAP guideline tier based on gene and variant.
    This is a simplified mock-up for demonstration purposes.
    
    Tiers:
    - Tier I: Variants of Strong Clinical Significance
    - Tier II: Variants of Potential Clinical Significance
    - Tier III: Variants of Unknown Clinical Significance (VUS)
    - Tier IV: Benign or Likely Benign
    """
    gene = row.get("gene", "")
    hgvsp = row.get("hgvsp", "")
    
    # Tier I: FDA approved therapies or included in professional guidelines
    tier_1_variants = {
        "EGFR": ["p.L858R", "p.T790M", "p.Exon19del"],
        "KRAS": ["p.G12C"],
        "BRAF": ["p.V600E"],
        "ALK": ["Fusion"],
        "ROS1": ["Fusion"]
    }
    
    # Tier II: Potential clinical significance (e.g., targeted therapy available but not standard of care)
    tier_2_genes = ["MET", "RET", "ERBB2"]
    
    # Tier III: VUS
    tier_3_genes = ["TP53", "PIK3CA", "PTEN"] # Simplified, TP53 is often considered functionally important but not directly actionable, thus Tier II or III depending on context. Let's map it to Tier III for now.
    
    if gene in tier_1_variants:
        if any(v in hgvsp for v in tier_1_variants[gene]):
            return "Tier I"
            
    if gene in tier_2_genes:
        return "Tier II"
        
    if gene in tier_3_genes:
        return "Tier III"
        
    # Default to Tier III for somatic, or Tier IV if known benign (skipped here)
    return "Tier III"
