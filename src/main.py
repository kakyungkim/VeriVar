import os
from pathlib import Path
import json
from dotenv import load_dotenv

from src.parser.vcf_parser import parse_vcf_to_df
from src.rules.amp_asco_cap import assign_guideline_tier
from src.llm.inference import run_inference
from src.report.pdf_export import generate_pdf_report

def main():
    """
    Main entry point for the LLM-Assisted Somatic Variant Interpretation Pipeline.

    Orchestrates the complete workflow:
    1. Parses the input VCF file to extract variants.
    2. Applies deterministic rule-based pre-tiering (AMP/ASCO/CAP guidelines).
    3. Executes Mode A (LLM-driven interpretation without predefined tiers).
    4. Executes Mode B (Rule-based interpretation with LLM explanations).
    5. Aggregates results into a structured JSON file.
    6. Generates a formatted PDF clinical report.
    """
    load_dotenv(override=True)  # Load environment variables from .env file

    print("[*] Starting LLM-Assisted Somatic Variant Interpretation Pipeline...")

    vcf_path = Path("data/synthetic_sample.vcf")
    if not vcf_path.exists():
        print(f"[!] VCF file not found at {vcf_path}. Please acquire data first.")
        return

    sample_id = vcf_path.stem

    # 1. Parsing
    print("[*] Parsing VCF...")
    df_variants = parse_vcf_to_df(vcf_path, variant_type="mixed", vaf_threshold=0.0)
    print(f"    Found {len(df_variants)} variants.")

    # 2. Rule-based Pre-tiering (Mode B setup)
    print("[*] Applying rule-based guideline tiers...")
    df_variants["rule_based_tier"] = df_variants.apply(assign_guideline_tier, axis=1)

    cancer_context = "Non-Small Cell Lung Cancer (NSCLC)"

    # 3. LLM Mode (Mode A)
    print("[*] Running Mode A (LLM-driven)...")
    llm_result = run_inference(
        df_candidates=df_variants,
        mode="llm",
        cancer_context=cancer_context,
        sample_id=sample_id
    )

    # 4. Rule Mode (Mode B)
    print("[*] Running Mode B (Rule-based with LLM explanation)...")
    rule_result = run_inference(
        df_candidates=df_variants,
        mode="rule",
        cancer_context=cancer_context,
        sample_id=sample_id
    )

    # 5. Output structure
    output = {
        "sample_id": sample_id,
        "cancer_context": cancer_context,
        "llm_mode": llm_result,
        "rule_mode": rule_result
    }

    # Save to JSON
    output_dir = Path("data/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{sample_id}_interpretation.json"

    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)

    print("[*] Generating PDF Report...")
    generate_pdf_report(sample_id, output, output_dir)

    print(f"[+] Pipeline complete. Results saved to {output_dir}")

if __name__ == "__main__":
    main()
