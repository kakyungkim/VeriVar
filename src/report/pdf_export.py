import json
import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

def generate_pdf_report(sample_id: str, dual_mode_result: dict, output_dir: Path) -> Path:
    """
    Generate a formatted PDF report from the pipeline's JSON output.
    
    This function uses Jinja2 to render an HTML template with the analysis
    results (both LLM-driven and Rule-based modes) and then converts the
    HTML to a PDF using xhtml2pdf.
    
    Args:
        sample_id (str): The unique identifier for the processed sample.
        dual_mode_result (dict): The complete results dictionary from the pipeline,
            containing both 'llm_mode' and 'rule_mode' interpretations.
        output_dir (Path): The directory path where the generated HTML and
            PDF reports will be saved.
            
    Returns:
        Path: The file path to the generated PDF (or the HTML file if PDF
            generation fails).
    """
    
    # Render HTML template
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("report.html")
    
    context = {
        "sample_id": sample_id,
        "cancer_context": dual_mode_result.get("cancer_context", "Unknown"),
        "llm_mode": dual_mode_result.get("llm_mode", {}),
        "rule_mode": dual_mode_result.get("rule_mode", {})
    }
    
    html_content = template.render(context)
    
    # Save intermediate HTML for debugging
    html_path = output_dir / f"{sample_id}_clinical_report.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    # Generate PDF
    pdf_path = output_dir / f"{sample_id}_clinical_report.pdf"
    
    # Silence xhtml2pdf logging
    logging.getLogger("xhtml2pdf").setLevel(logging.ERROR)
    
    with open(pdf_path, "w+b") as result_file:
        pisa_status = pisa.CreatePDF(
            html_content,
            dest=result_file
        )
        
    if pisa_status.err:
        print(f"âŒ Error generating PDF: {pisa_status.err}")
        return html_path
    
    print(f"ðŸ“„ PDF Report generated: {pdf_path}")
    return pdf_path
