"""Production cohort report (HTML + PDF) from the dual-mode pipeline output.

Renders the new cohort_interpretation.json (summary + per-variant dual-mode
results + evidence) into a clean clinical-style report. HTML is the rich
artifact; PDF is produced via xhtml2pdf with print-simple CSS.
"""
import json
import logging
from pathlib import Path
from typing import Union

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path("templates")
DEFAULT_INPUT = Path("data/outputs/cohort_interpretation.json")


def _prepare(output: dict) -> dict:
    """Derive display-friendly structures (discordant first, grouped)."""
    variants = output.get("variants", [])
    discordant = [v for v in variants if v.get("discordant")]
    concordant = [v for v in variants if not v.get("discordant")]
    # Sort discordant by cancer then gene for a readable table.
    discordant.sort(key=lambda v: (v.get("cancer_type") or "", v.get("gene") or ""))
    return {
        "provenance": output.get("provenance", {}),
        "summary": output.get("discordance_summary", {}),
        "discordant": discordant,
        "concordant": concordant,
        "all_variants": sorted(variants, key=lambda v: (v.get("cancer_type") or "", v.get("gene") or "")),
        "n_total": len(variants),
        "n_discordant": len(discordant),
    }


def generate_report(source: Union[dict, str, Path] = DEFAULT_INPUT,
                    out_dir: Union[str, Path] = "data/outputs",
                    basename: str = "cohort_report") -> Path:
    output = source if isinstance(source, dict) else json.loads(Path(source).read_text())
    ctx = _prepare(output)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("cohort_report.html")
    # Interactive (search/sort/filter JS) for the HTML artifact; a compact
    # static table for the PDF (xhtml2pdf can't run JS and chokes on the wide table).
    html = template.render(interactive=True, **ctx)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{basename}.html"
    html_path.write_text(html, encoding="utf-8")

    pdf_path = out_dir / f"{basename}.pdf"
    try:
        from xhtml2pdf import pisa
        logging.getLogger("xhtml2pdf").setLevel(logging.ERROR)
        pdf_html = template.render(interactive=False, **ctx)
        with pdf_path.open("w+b") as f:
            status = pisa.CreatePDF(pdf_html, dest=f)
        if status.err:
            print(f"[!] PDF generation had errors; HTML is at {html_path}")
            return html_path
        print(f"[+] report: {html_path} + {pdf_path}")
        return pdf_path
    except Exception as e:  # noqa: BLE001 - PDF is best-effort; HTML always written
        print(f"[!] PDF skipped ({e}); HTML at {html_path}")
        return html_path


if __name__ == "__main__":
    generate_report()
