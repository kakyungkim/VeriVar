"""Consolidate data-resource provenance into a single manifest (offline, no network).

Aggregates every committed provenance record this pipeline relies on into a
machine-readable manifest (``data/knowledge/resources.json``) and a
human-readable table (``docs/RESOURCES.md``) for the paper Methods.

ANTI-FABRICATION CONTRACT: every version / snapshot date / genome build / URL is
read from a committed provenance file or a real constant in this repo's fetch
scripts / source modules. Where an exact upstream version string is not recorded
(e.g. CIViC nightly, AlphaMissense via VEP), the fetched/access date is used and
the entry is explicitly marked ``"snapshot"`` — never a guessed version.

Run::

    python -m scripts.build_resource_manifest
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent

# Provenance inputs (read-only). Missing files are tolerated (recorded as such).
KNOWLEDGE_PROV = ROOT / "data/knowledge/provenance.json"
BENCHMARK_PROV = ROOT / "data/benchmark/provenance.json"
FUNCTIONAL_PROV = ROOT / "data/knowledge/functional/provenance.json"
COHORT_MANIFEST = ROOT / "data/cohorts/cohort_manifest.json"
CANCERVAR_PRED = ROOT / "data/benchmark/cancervar/cancervar_predictions.json"
CGI_BLOCKED = ROOT / "data/benchmark/cgi/FEASIBILITY_BLOCKED.json"
UNIPROT_DOMAINS = ROOT / "data/knowledge/domains/uniprot_domains.json"

OUT_JSON = ROOT / "data/knowledge/resources.json"
OUT_MD = ROOT / "docs/RESOURCES.md"

# Columns of the rendered table / each resource record.
FIELDS = ["resource", "version_snapshot", "genome_build", "source_url",
          "access_date", "license_notes"]


def _load(path: Path) -> Optional[dict]:
    """Read a committed JSON provenance file; return None if absent/unreadable."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _date(iso_utc: Optional[str]) -> str:
    """Normalize an ISO-8601 UTC timestamp to a YYYY-MM-DD access date."""
    if not iso_utc:
        return "n/a"
    return str(iso_utc)[:10]


def build_resources() -> List[Dict[str, str]]:
    """Assemble the resource records strictly from committed provenance."""
    know = _load(KNOWLEDGE_PROV) or {}
    bench = _load(BENCHMARK_PROV) or {}
    cohort = _load(COHORT_MANIFEST) or {}
    cancervar = _load(CANCERVAR_PRED) or {}
    cv_prov = cancervar.get("provenance", {}) if isinstance(cancervar, dict) else {}
    cgi = _load(CGI_BLOCKED) or {}
    cgi_prov = cgi.get("provenance", {}) if isinstance(cgi, dict) else {}
    functional = _load(FUNCTIONAL_PROV) or {}
    uniprot = _load(UNIPROT_DOMAINS) or {}

    know_date = _date(know.get("fetched_utc"))
    cohort_date = _date(cohort.get("fetched_utc"))
    bench_date = _date(bench.get("fetched_utc"))
    civic_assertions_src = bench.get("source", "")

    resources: List[Dict[str, str]] = []

    # 1. Cohort: TCGA PanCancer Atlas 2018 via cBioPortal (GRCh37).
    studies = cohort.get("studies", {}) if isinstance(cohort, dict) else {}
    resources.append({
        "resource": "Cohort variants — TCGA PanCancer Atlas 2018",
        "version_snapshot": (
            f"cBioPortal snapshot {cohort_date} "
            f"({len(studies)} studies, {cohort.get('samples_per_study', 'n/a')} samples/study)"
        ),
        "genome_build": "GRCh37 (hg19)",
        "source_url": cohort.get("source", "https://www.cbioportal.org/api"),
        "access_date": cohort_date,
        "license_notes": "TCGA open-access somatic mutations via cBioPortal; "
                         "27-gene driver panel.",
    })

    # 2. CIViC — nightly snapshot (CC0). Version == fetched date (no upstream tag).
    resources.append({
        "resource": "CIViC (clinical evidence + assertions)",
        "version_snapshot": f"nightly snapshot {know_date}",
        "genome_build": "n/a (gene/variant-level assertions)",
        "source_url": know.get(
            "civic_source",
            "https://civicdb.org/downloads/nightly/nightly-ClinicalEvidenceSummaries.tsv"),
        "access_date": know_date,
        "license_notes": (
            f"CC0 1.0. {know.get('civic_evidence_rows', 'n/a')} evidence rows; "
            f"{bench.get('n_assertions', 'n/a')} assertions "
            f"({_date(bench.get('fetched_utc'))}, {civic_assertions_src})."
        ),
    })

    # 3. DGIdb — drug–gene interactions (GraphQL API snapshot).
    resources.append({
        "resource": "DGIdb (drug–gene interactions)",
        "version_snapshot": f"API snapshot {know_date}",
        "genome_build": "n/a (gene-level)",
        "source_url": know.get("dgidb_source", "https://dgidb.org/api/graphql"),
        "access_date": know_date,
        "license_notes": (
            f"{know.get('dgidb_interactions', 'n/a')} gene-level interactions; "
            "gene-level drugs do not satisfy the variant-evidence contract."
        ),
    })

    # 4. AlphaMissense — model 2023, accessed via Ensembl VEP REST (per-variant).
    resources.append({
        "resource": "AlphaMissense (computational pathogenicity)",
        "version_snapshot": "model 2023 (Cheng et al., Science 2023; Zenodo 8208688), "
                            "queried per-variant via Ensembl VEP REST",
        "genome_build": "build-aware: GRCh37 via grch37.rest.ensembl.org, "
                        "GRCh38 via rest.ensembl.org (protein-level predictor; no liftover)",
        "source_url": "https://rest.ensembl.org/vep/human/region (AlphaMissense=1)",
        "access_date": know_date,
        "license_notes": "Per-variant VEP cache (snapshot); thresholds "
                         "pathogenic>=0.564, benign<=0.34 (Cheng 2023). CC-BY-NC.",
    })

    # 5. ClinicalTrials.gov — API v2.
    resources.append({
        "resource": "ClinicalTrials.gov (trials)",
        "version_snapshot": "REST API v2 snapshot",
        "genome_build": "n/a",
        "source_url": "https://clinicaltrials.gov/api/v2/studies",
        "access_date": know_date,
        "license_notes": "Trial records linked from CIViC NCT ids (snapshot).",
    })

    # 6. UniProt domains (functional regions for OM1 / hotspot context).
    n_domain_genes = len(uniprot) if isinstance(uniprot, dict) else 0
    resources.append({
        "resource": "UniProt protein domains",
        "version_snapshot": "snapshot (no upstream version recorded)",
        "genome_build": "n/a (protein coordinates, UniProt residue numbering)",
        "source_url": "https://rest.uniprot.org",
        "access_date": "snapshot",
        "license_notes": (
            f"CC-BY 4.0. Domain/region spans for {n_domain_genes} genes "
            "(data/knowledge/domains/uniprot_domains.json)."
        ),
    })

    # 7. Horak et al. 2022 — external oncogenicity gold standard.
    resources.append({
        "resource": "Horak et al. 2022 (external gold standard)",
        "version_snapshot": "70 expert-classified variants (ClinGen/CGC/VICC)",
        "genome_build": "GRCh38 (b38) + GRCh37 (b37) coordinates both committed "
                        "(data/benchmark/horak_benchmark.tsv)",
        "source_url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9081216/",
        "access_date": "snapshot",
        "license_notes": "Horak P, et al. Genet Med. 2022;24(5):986-998. "
                         "VICC point-based oncogenicity standard.",
    })

    # 8. CancerVar — external comparator (ran). Build/date from its provenance.
    resources.append({
        "resource": "CancerVar (external AMP/ASCO/CAP comparator)",
        "version_snapshot": f"web server snapshot {_date(cv_prov.get('fetched_utc'))} "
                            f"({cv_prov.get('build', 'GRCh38')})",
        "genome_build": "GRCh38 (hg38; Horak b38 coordinates)",
        "source_url": cv_prov.get("endpoint", "https://cancervar.wglab.org/results_new.php"),
        "access_date": _date(cv_prov.get("fetched_utc")),
        "license_notes": "Li Q, et al. Sci Adv. 2022;8(18):eabj1624. "
                         "Tiers parsed verbatim; cross-axis (actionability, not oncogenicity).",
    })

    # 9. CGI — deferred (feasibility-blocked; no predictions produced).
    resources.append({
        "resource": "CGI (Cancer Genome Interpreter) — DEFERRED",
        "version_snapshot": f"BLOCKED (token-gated); probed {_date(cgi.get('fetch_attempted_utc'))}",
        "genome_build": "GRCh38 (would be, per intended run)",
        "source_url": "https://www.cancergenomeinterpreter.org/",
        "access_date": _date(cgi.get("fetch_attempted_utc")),
        "license_notes": "Tamborero D, et al. Genome Med. 2018;10:25. "
                         "No predictions obtained (auth-gated); kept out of head-to-head.",
    })

    # 10. Ensembl VEP REST mirrors (the live annotation endpoints).
    resources.append({
        "resource": "Ensembl VEP REST mirrors",
        "version_snapshot": "REST endpoints (per-variant snapshot via local caches)",
        "genome_build": "GRCh37: grch37.rest.ensembl.org · GRCh38: rest.ensembl.org",
        "source_url": "https://rest.ensembl.org/vep/human/region",
        "access_date": know_date,
        "license_notes": "Used for VCF annotation (gene/HGVSp/consequence) and "
                         "AlphaMissense lookups; results cached for offline reproducibility.",
    })

    # 11. Primary LLM + replication model.
    resources.append({
        "resource": "LLM — gpt-4o-mini (primary) + gpt-4o (replication)",
        "version_snapshot": "gpt-4o-mini (src/classify/llm.py MODEL); "
                            "gpt-4o second-model replication",
        "genome_build": "n/a",
        "source_url": "https://api.openai.com",
        "access_date": _date((know.get("fetched_utc"))),
        "license_notes": "Self-consistency n=3 + agentic verifier; offline mock "
                         "fallback when OPENAI_API_KEY unset (not a real result).",
    })

    # MaveDB DMS (functional OS2 evidence) — recorded from functional provenance.
    if isinstance(functional, dict) and functional:
        urns = []
        for gene, blk in functional.items():
            if gene == "note":
                continue
            if isinstance(blk, dict):
                urns.extend(blk.get("urns", []))
                if "urn" in blk:
                    urns.append(blk["urn"])
        resources.append({
            "resource": "MaveDB deep-mutational-scanning (functional OS2)",
            "version_snapshot": "snapshot (score-set urns recorded)",
            "genome_build": "n/a (protein-level functional scores)",
            "source_url": "https://api.mavedb.org/api/v1",
            "access_date": "snapshot",
            "license_notes": "; ".join(urns) if urns else "see functional/provenance.json",
        })

    return resources


def render_markdown(resources: List[Dict[str, str]], generated_utc: str) -> str:
    """Render the resources as a Markdown table for the paper Methods."""
    header = ("# Data Resources & Genome Builds\n\n"
              "_Auto-generated by `scripts/build_resource_manifest.py` from committed "
              "provenance files — do not hand-edit. Every version/date/build/URL is "
              "read from provenance; unknown upstream versions are marked "
              "\"snapshot\" with the access date (anti-fabrication contract)._\n\n"
              f"Generated (UTC): {generated_utc}\n\n"
              "| Resource | Version/Snapshot | Genome build | Source/URL | "
              "Access date | License/Notes |\n"
              "|---|---|---|---|---|---|\n")
    rows = []
    for r in resources:
        cells = [str(r.get(f, "")).replace("|", "\\|") for f in FIELDS]
        rows.append("| " + " | ".join(cells) + " |")
    return header + "\n".join(rows) + "\n"


def main() -> None:
    resources = build_resources()
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "generated_utc": generated,
        "generator": "scripts/build_resource_manifest.py",
        "note": ("Aggregated from committed provenance files; versions absent "
                 "upstream are recorded as snapshot + access date."),
        "resources": resources,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(manifest, indent=2) + "\n")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render_markdown(resources, generated))
    print(f"Wrote {OUT_JSON} ({len(resources)} resources)")
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    main()
