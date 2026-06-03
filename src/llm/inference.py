import os
import pandas as pd
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.parser.models import SampleInterpretation, VariantInterpretation
from src.rag.database import get_rag_context

def run_inference(
    df_candidates: pd.DataFrame, 
    mode: str, 
    cancer_context: str, 
    sample_id: str
) -> Dict[str, Any]:
    """
    Runs LLM inference for somatic variant interpretation.
    
    Args:
        df_candidates: DataFrame containing variants.
        mode: "llm" (LLM determines tier) or "rule" (LLM explains rule-based tier).
        cancer_context: Cancer type (e.g., "Non-Small Cell Lung Cancer (NSCLC)").
        sample_id: ID of the sample.
        
    Returns:
        Dictionary representation of SampleInterpretation.
    """
    # Default to a mock if OPENAI_API_KEY is not set to allow the pipeline to run
    if not os.environ.get("OPENAI_API_KEY"):
        print("[!] OPENAI_API_KEY not found. Using mock LLM response.")
        return _mock_inference(df_candidates, mode, cancer_context, sample_id)

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)
    structured_llm = llm.with_structured_output(SampleInterpretation)

    # Format variants for the prompt
    variants_str = ""
    for _, row in df_candidates.iterrows():
        gene = row.get('gene', 'Unknown')
        variant = row.get('hgvsp', row.get('alt', ''))
        tier_info = f"Rule-based Tier: {row.get('rule_based_tier', 'Unknown')}" if mode == "rule" else ""
        
        # Fetch RAG Context
        rag_info = get_rag_context(gene, variant, cancer_context)
        
        variants_str += f"- Gene: {gene}, Variant: {variant}, VAF: {row.get('vaf', 'N/A')}, {tier_info}\n"
        variants_str += f"  {rag_info}\n"

    system_prompt = (
        "You are an expert molecular pathologist analyzing somatic variants for cancer context: {cancer_context}.\n"
        "Mode: {mode}. If mode is 'rule', rely heavily on the provided Rule-based Tier for your final tier assignment, "
        "but provide clinical explanation. If mode is 'llm', independently evaluate the AMP/ASCO/CAP tier.\n"
        "Use the provided RAG Context (Literature and Clinical Trials) to support your oncogenic evidence and tier basis.\n"
        "Provide a comprehensive interpretation of the variants."
    )
    
    human_prompt = "Sample ID: {sample_id}\n\nVariants and Context:\n{variants_str}"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_prompt)
    ])
    
    chain = prompt | structured_llm
    
    result: SampleInterpretation = chain.invoke({
        "cancer_context": cancer_context,
        "mode": mode,
        "sample_id": sample_id,
        "variants_str": variants_str
    })
    
    if isinstance(result, dict):
        return result
    return result.model_dump()


def _mock_inference(
    df_candidates: pd.DataFrame, 
    mode: str, 
    cancer_context: str, 
    sample_id: str
) -> Dict[str, Any]:
    """Provides a mock response when API key is missing."""
    
    mock_variants: List[VariantInterpretation] = []
    
    for _, row in df_candidates.iterrows():
        gene = row.get("gene", "Unknown")
        variant = row.get("hgvsp", row.get("alt", ""))
        tier = row.get("rule_based_tier", "Tier III") if mode == "rule" else "Tier I" if gene in ["EGFR", "KRAS"] else "Tier III"
        
        # Simulate fetching RAG context in mock
        rag_info = get_rag_context(gene, variant, cancer_context)
        
        mock_variants.append(
            VariantInterpretation(
                gene=gene,
                variant=variant,
                variant_type="SNV/Indel",
                vaf=row.get("vaf", 0.0),
                oncogenic_evidence=f"Mock evidence of oncogenicity based on: {rag_info[:50]}...",
                potential_tier=tier,
                tier_basis="Mock explanation for tier assignment.",
                requires_additional_validation=False,
                recommended_experiments=[],
                notes=f"Processed in {mode} mode."
            )
        )
        
    sample_interp = SampleInterpretation(
        sample_id=sample_id,
        cancer_context=cancer_context,
        rna_expression_level=None,
        tme_context=None,
        variants=mock_variants,
        overall_summary=f"Mock summary for {sample_id} in {cancer_context}. Mode: {mode}.",
        limitations="This is a mock report because the OPENAI_API_KEY was not provided."
    )
    
    return sample_interp.model_dump()
