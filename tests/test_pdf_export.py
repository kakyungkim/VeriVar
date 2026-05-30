from pathlib import Path
from src.report.pdf_export import generate_pdf_report

def test_generate_pdf_report(tmp_path):
    sample_id = "test_sample"
    dual_mode_result = {
        "cancer_context": "NSCLC",
        "llm_mode": {
            "overall_summary": "Test LLM Summary",
            "limitations": "None",
            "variants": [
                {
                    "gene": "EGFR",
                    "variant": "p.L858R",
                    "vaf": 0.5,
                    "potential_tier": "Tier I",
                    "tier_basis": "Testing basis"
                }
            ]
        },
        "rule_mode": {
            "overall_summary": "Test Rule Summary",
            "limitations": "None",
            "variants": [
                {
                    "gene": "EGFR",
                    "variant": "p.L858R",
                    "potential_tier": "Tier I",
                    "tier_basis": "Testing basis"
                }
            ]
        }
    }
    
    # Run the PDF export
    pdf_path = generate_pdf_report(sample_id, dual_mode_result, tmp_path)
    
    assert pdf_path.exists(), "PDF file was not created"
    assert pdf_path.suffix == ".pdf", "File does not have .pdf extension"
    assert pdf_path.stat().st_size > 0, "PDF file is empty"
