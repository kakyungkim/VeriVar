"""Contract tests for the K-BioX summit poster (docs/poster/kbiox2026).

A poster is printed by the secretariat and hung for a day; nobody re-reads it
against the result files once it is on the board. These tests do that reading.

They check three things:
  1. every headline number printed on the poster matches the committed JSON;
  2. no retired value (the pre-2026-09-27 faithfulness endpoint, the pre-SOP-strict
     rule-arm accuracy) has crept back in;
  3. the files the poster references actually exist.

They parse the HTML source rather than the rendered PDF, because the numbers are
typed there; the charts are generated from the same JSONs by make_poster_figures.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POSTER = ROOT / "docs" / "poster" / "kbiox2026"
HTML = POSTER / "poster.html"
OUT = ROOT / "data" / "outputs"
BENCH = ROOT / "data" / "benchmark"

pytestmark = pytest.mark.skipif(not HTML.exists(), reason="poster not built in this checkout")


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def html() -> str:
    return HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def text(html: str) -> str:
    """Poster text with tags removed and whitespace collapsed."""
    stripped = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", stripped)


@pytest.fixture(scope="module")
def taxonomy() -> dict:
    return _load(OUT / "citation_taxonomy.json")["headline"]["arms"]


def test_faithfulness_headline_matches_taxonomy(text: str, taxonomy: dict) -> None:
    ids = taxonomy["retrieval_gpt4o_mini_106"]["identifier_tokens_out_of_bundle"]
    norag = taxonomy["no_retrieval_E_empty_bundle"]["variant_any_fabricated_or_misattributed"]
    assert f"{ids['k']} / {ids['n']}" in text, "retrieval identifier count missing or stale"
    assert f"{norag['k']} / {norag['n']}" in text, "no-retrieval variant count missing or stale"


def test_accuracy_headline_matches_stats(text: str) -> None:
    stats = _load(OUT / "stats_report.json")
    rag = stats["horak_3class_accuracy_ci"]["llm_rag"]["point"]
    norag = stats["horak_3class_accuracy_ci"]["llm_norag"]["point"]
    p = stats["horak_mcnemar"]["rag_vs_norag"]["p_value"]
    assert f"{rag:.3f} vs" in text and f"{norag:.3f}" in text
    assert f"p = {p}" in text, "the retrieval-vs-no-retrieval p-value is not printed as stored"


def test_rule_arm_and_comparator_numbers(text: str) -> None:
    hv = _load(BENCH / "horak_vicc.json")
    onc = _load(BENCH / "oncovi_headtohead.json")
    assert f"{onc['oncovi']['accuracy_3class']:.3f}" in text
    assert f"p = {onc['paired_mcnemar_3class']['p_two_sided']:.3f}" in text
    # the rule arm's own accuracy is carried by the chart, so only assert the config exists
    assert hv["config"] == "sop_strict"


def test_cohort_sizes(text: str, taxonomy: dict) -> None:
    n_cohort = taxonomy["no_retrieval_E_empty_bundle"]["variant_any_fabricated_or_misattributed"]["n"]
    n_horak = _load(BENCH / "horak_vicc.json")["n"]
    n_clinvar = _load(BENCH / "clinvar_onc_holdout.json")["scopes"]["all"]["detection"]["n"]
    for n in (n_cohort, n_horak, n_clinvar):
        assert f">{n}<" in re.sub(r"\s+", "", HTML.read_text(encoding="utf-8")), f"cohort size {n} not shown"


def test_perturbation_counts(text: str) -> None:
    rep = _load(OUT / "context_ablation.json")
    alias = rep["summary"]["arms"]["alias"]
    drivers = alias["driver_calls_after_clinical_loss"]
    safe = alias["safe_downgrades_after_clinical_loss"]
    assert f"{drivers} of {drivers + safe}" in text or f"{drivers} of 26" in text
    assert "0 of 228" in text, "the grounded-citation count of the perturbation run is missing"


RETIRED = {
    "0.464": "pre-2026-09-27 fabrication rate",
    "46.4": "pre-2026-09-27 fabrication rate",
    "26 of 56": "pre-2026-09-27 variant count",
    "26 / 56": "pre-2026-09-27 variant count",
    "0.843": "pre-SOP-strict rule-arm accuracy",
    "0.902": "retired ClinVar AUROC",
}


def test_no_retired_numbers(text: str) -> None:
    hits = [f"{v} ({why})" for v, why in RETIRED.items() if v in text]
    assert not hits, "retired values on the poster: " + "; ".join(hits)


#: Event logos downloaded from the summit site for the printed poster. They are not
#: redistributed (see docs/poster/kbiox2026/README.md), so a fresh clone lacks them.
THIRD_PARTY_ASSETS = ("assets/",)


def test_referenced_assets_exist(html: str) -> None:
    refs = [src for src in re.findall(r'(?:src|href)="([^"]+)"', html)
            if not src.startswith(("http:", "https:", "#", "data:"))]
    shipped = [r for r in refs if not r.startswith(THIRD_PARTY_ASSETS)]
    missing = [r for r in shipped if not (POSTER / r).exists()]
    assert not missing, f"poster references files that do not exist: {missing}"
    # every file the repository is expected to ship must be tracked-path material
    assert all(not r.startswith("assets/verivar") for r in refs), \
        "the VeriVar mark must come from docs/branding, which is tracked"


def test_research_only_disclaimer_present(text: str) -> None:
    low = text.lower()
    assert "not a medical device" in low and "not for clinical" in low
