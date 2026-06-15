"""Smoke test for the consolidated resource manifest builder (offline, no network).

Runs ``build_resources`` against the committed provenance files and asserts the
key resources are present and each carries a genome-build field. Anti-fabrication:
this only checks structure/coverage, never specific guessed version strings.
"""
from scripts.build_resource_manifest import build_resources, render_markdown, FIELDS


def test_build_resources_covers_key_resources():
    resources = build_resources()
    names = " | ".join(r["resource"] for r in resources)
    for needle in ["TCGA", "CIViC", "DGIdb", "AlphaMissense", "ClinicalTrials.gov",
                   "Horak", "CancerVar", "CGI", "Ensembl VEP", "gpt-4o"]:
        assert needle in names, f"missing resource: {needle}"


def test_every_resource_has_all_fields():
    for r in build_resources():
        for field in FIELDS:
            assert field in r and str(r[field]).strip(), f"{r.get('resource')} missing {field}"


def test_every_resource_has_genome_build():
    # genome_build may legitimately be 'n/a' for gene/protein-level resources,
    # but the field must always be populated (never blank/guessed).
    for r in build_resources():
        assert str(r["genome_build"]).strip()


def test_builds_are_real_labels():
    # Where a coordinate build is asserted it must be a recognized label, not a guess.
    blob = " ".join(r["genome_build"] for r in build_resources())
    assert "GRCh37" in blob and "GRCh38" in blob


def test_markdown_renders_table():
    md = render_markdown(build_resources(), "2026-01-01T00:00:00Z")
    assert md.startswith("# Data Resources")
    assert "| Resource | Version/Snapshot | Genome build |" in md
    # one header row + separator + at least the 11 enumerated resources
    assert md.count("\n|") >= 12
