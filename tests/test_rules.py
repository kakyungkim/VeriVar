"""Unit tests for deterministic AMP/ASCO/CAP rule-based tiering (Phase 0).

NOTE: This guards the *current* simplified rule engine. The known limitation
that fusion / exon-level keys (e.g. ALK 'Fusion', EGFR 'p.Exon19del') never
appear in SNV-derived HGVSp is documented in the devlog and addressed when the
classifier is rebuilt to the 2-axis VICC + AMP/ASCO/CAP model in Phase 1.
"""
import pandas as pd

from src.rules.amp_asco_cap import assign_guideline_tier


def _row(gene="", hgvsp=""):
    return pd.Series({"gene": gene, "hgvsp": hgvsp})


def test_tier_i_known_hotspot():
    assert assign_guideline_tier(_row("EGFR", "p.L858R")) == "Tier I"
    assert assign_guideline_tier(_row("KRAS", "p.G12C")) == "Tier I"
    assert assign_guideline_tier(_row("BRAF", "p.V600E")) == "Tier I"


def test_tier_ii_gene_level():
    assert assign_guideline_tier(_row("MET", "p.X")) == "Tier II"
    assert assign_guideline_tier(_row("RET", "")) == "Tier II"


def test_tier_iii_vus_genes_and_default():
    assert assign_guideline_tier(_row("TP53", "p.R175H")) == "Tier III"
    assert assign_guideline_tier(_row("UNKNOWNGENE", "p.A1B")) == "Tier III"


def test_tier_i_gene_without_matching_variant_falls_through():
    # EGFR is a Tier-I gene but a non-listed variant should not be Tier I.
    assert assign_guideline_tier(_row("EGFR", "p.R776H")) == "Tier III"
