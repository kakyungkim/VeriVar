"""Golden-set regression and run-provenance tests (offline, no API key needed).

These cover the parts of the change-control machinery that can be checked
without calling the model: that the committed snapshot is well-formed and was
produced live, that the prompts and guardrail version in the tree still match
the ones the snapshot was built under, and that the comparison logic actually
reports a difference when one exists.

The live half of the check (re-classifying the pinned variants against the API)
is deliberately not run here — it costs money and needs a key. Run
``python -m scripts.run_golden_regression`` for that.
"""
import json
from pathlib import Path

import pytest

from scripts.run_golden_regression import (
    GOLDEN_VARIANTS, SNAPSHOT, compare, config_drift,
)
from src.provenance import (
    GUARDRAIL_VERSION, build_provenance, prompt_hash, prompt_hashes, prompt_registry,
)


@pytest.fixture(scope="module")
def snapshot() -> dict:
    if not SNAPSHOT.exists():
        pytest.skip(f"no golden snapshot at {SNAPSHOT}")
    return json.loads(SNAPSHOT.read_text())


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #
def test_prompt_registry_covers_every_call_type():
    reg = prompt_registry()
    assert set(reg) == {"classify", "parametric", "explain_rule", "qa", "verify"}
    assert all(isinstance(v, str) and v.strip() for v in reg.values())


def test_prompt_hash_is_stable_and_distinguishes_prompts():
    assert prompt_hash() == prompt_hash()
    hashes = prompt_hashes()
    # Distinct prompts must not collide, or a change could hide behind a match.
    assert len(set(hashes.values())) == len(hashes)


def test_provenance_records_the_behaviour_fixing_configuration():
    prov = build_provenance(live=True, model_name="gpt-4o-mini", n_variants=3,
                            techniques=["dense-RAG"], n_votes=3)
    assert prov.mode_used == "live"
    assert prov.prompt_hash == prompt_hash()
    assert prov.prompt_hashes == prompt_hashes()
    assert prov.guardrail_version == GUARDRAIL_VERSION
    assert prov.temperatures  # sampling parameters recorded, not implied
    assert prov.n_votes == 3


def test_provenance_records_the_dense_index_identity():
    """embedding_model is derived from the index, so the two cannot disagree."""
    from src.retrieval.corpus import RetrievalDoc
    from src.retrieval.embedders import HashingEmbedder
    from src.retrieval.hybrid import HybridRetriever
    from src.retrieval.orchestrator import HybridEvidenceRetriever

    docs = [RetrievalDoc(id="CIViC:EID1", text="BRAF V600E melanoma", gene="BRAF",
                         variant="V600E", disease="Melanoma")]
    retriever = HybridEvidenceRetriever(aggregator=None,
                                        dense=HybridRetriever(docs, embedder=HashingEmbedder()))
    fp = retriever.index_fingerprint()
    assert fp["n_docs"] == 1 and fp["corpus_digest"] and fp["dense_k"] == 5

    prov = build_provenance(live=True, model_name="gpt-4o-mini", retrieval_index=fp)
    assert prov.embedding_model == fp["embedder"]
    assert prov.retrieval_index["corpus_digest"] == fp["corpus_digest"]


def test_index_fingerprint_is_none_without_a_dense_arm():
    from src.retrieval.orchestrator import HybridEvidenceRetriever

    assert HybridEvidenceRetriever(aggregator=None, dense=None).index_fingerprint() is None
    prov = build_provenance(live=True, model_name="gpt-4o-mini", retrieval_index=None)
    assert prov.embedding_model is None and prov.retrieval_index == {}


def test_provenance_marks_the_offline_fallback_as_such():
    """An offline run must never be recorded as a live result."""
    prov = build_provenance(live=False, model_name=None)
    assert prov.mode_used == "offline"
    assert prov.model_name is None


def test_provenance_serialises_to_the_keys_downstream_readers_use():
    """The dashboard, HTML report, and eval scripts read these keys by name."""
    payload = build_provenance(live=True, model_name="gpt-4o-mini",
                               timestamp="2026-08-08T00:00:00Z",
                               techniques=["dense-RAG"]).model_dump(mode="json")
    for key in ("mode_used", "model_name", "timestamp", "techniques", "data_sources"):
        assert key in payload


# --------------------------------------------------------------------------- #
# The committed snapshot
# --------------------------------------------------------------------------- #
def test_snapshot_was_built_from_a_live_run(snapshot):
    """A snapshot built on the offline mock would certify nothing."""
    assert snapshot["provenance"]["mode_used"] == "live"
    assert snapshot["provenance"]["model_name"]


def test_snapshot_covers_every_pinned_variant(snapshot):
    assert len(snapshot["entries"]) == len(GOLDEN_VARIANTS)
    assert not snapshot["missing_from_cohort"]


def test_snapshot_entries_are_well_formed(snapshot):
    for key, entry in snapshot["entries"].items():
        for mode in ("mode_a", "mode_b"):
            fp = entry[mode]
            assert fp["oncogenicity"] and fp["tier"], key
            assert isinstance(fp["abstained"], bool), key
            assert isinstance(fp["citations"], list), key
            # Citations must be sorted, or set comparison would report phantom diffs.
            assert fp["citations"] == sorted(fp["citations"]), key


def test_abstention_entries_cite_nothing(snapshot):
    """The abstention contract: no evidence retrieved means no citation made."""
    for key, entry in snapshot["entries"].items():
        if entry["mode_a"]["abstained"] and entry["n_evidence"] == 0:
            assert entry["mode_a"]["citations"] == [], key


def test_tree_configuration_still_matches_the_snapshot(snapshot):
    """Prompts or guardrails changing without a rebuild is the failure this catches."""
    current = {
        "model_name": snapshot["provenance"]["model_name"],
        "prompt_hash": prompt_hash(),
        "prompt_hashes": prompt_hashes(),
        "guardrail_version": GUARDRAIL_VERSION,
    }
    assert config_drift(snapshot, current) == []


# --------------------------------------------------------------------------- #
# The comparison logic itself
# --------------------------------------------------------------------------- #
def _entry(onco="Oncogenic", tier="Tier I", abstained=False, citations=("EID1",)):
    fp = {"oncogenicity": onco, "tier": tier, "tier_level": None,
          "abstained": abstained, "citations": sorted(citations)}
    return {"gene": "BRAF", "hgvsp": "p.V600E", "cancer_type": "Cutaneous Melanoma",
            "n_evidence": 1, "mode_a": dict(fp), "mode_b": dict(fp)}


def test_compare_is_silent_on_an_identical_run():
    snap = {"entries": {"K": _entry()}}
    assert compare(snap, {"entries": {"K": _entry()}}) == []


def test_compare_reports_a_changed_label():
    snap = {"entries": {"K": _entry()}}
    cur = {"entries": {"K": _entry(onco="VUS", tier="Tier III")}}
    diffs = compare(snap, cur)
    assert any("oncogenicity" in d for d in diffs)
    assert any("tier" in d for d in diffs)


def test_compare_reports_dropped_and_added_citations():
    snap = {"entries": {"K": _entry(citations=("EID1", "EID2"))}}
    cur = {"entries": {"K": _entry(citations=("EID2", "EID9"))}}
    diffs = compare(snap, cur)
    assert any("citations" in d and "EID1" in d and "EID9" in d for d in diffs)


def test_compare_reports_a_missing_variant():
    snap = {"entries": {"K": _entry(), "GONE": _entry()}}
    diffs = compare(snap, {"entries": {"K": _entry()}})
    assert any("GONE" in d for d in diffs)


# --------------------------------------------------------------------------- #
# Replicate tolerance on Mode A
#
# The model does not reproduce itself exactly at temperature 0, so a pinned
# value counts as reproduced when any draw matches it. Mode B is rule code and
# stays strict.
# --------------------------------------------------------------------------- #
def _fp(onco="Oncogenic", tier="Tier I", abstained=False, citations=("EID1",)):
    return {"oncogenicity": onco, "tier": tier, "tier_level": None,
            "abstained": abstained, "citations": sorted(citations)}


def _replicated(draws, mode_b=None):
    return {"gene": "BRAF", "hgvsp": "p.V600E", "cancer_type": "Cutaneous Melanoma",
            "n_evidence": 1, "mode_a": dict(draws[0]),
            "mode_a_replicates": [dict(d) for d in draws],
            "mode_b": dict(mode_b or _fp())}


def test_a_label_reproduced_in_any_draw_is_not_a_difference():
    snap = {"entries": {"K": _entry()}}
    cur = {"entries": {"K": _replicated([_fp(onco="VUS"), _fp(), _fp(onco="VUS")])}}
    assert compare(snap, cur) == []


def test_a_label_absent_from_every_draw_is_reported():
    snap = {"entries": {"K": _entry()}}
    cur = {"entries": {"K": _replicated([_fp(onco="VUS")] * 3)}}
    diffs = compare(snap, cur)
    assert any("oncogenicity" in d and "not reproduced in 3 draws" in d for d in diffs)


def test_pinned_citations_spread_across_draws_are_not_a_difference():
    """No single draw reproduces the exact set, but every pinned id is reachable."""
    pinned = ("EID1", "EID2")
    snap = {"entries": {"K": _entry(citations=pinned)}}
    cur = {"entries": {"K": _replicated([
        _fp(citations=("EID1",)), _fp(citations=("EID2", "EID9")),
    ], mode_b=_fp(citations=pinned))}}
    assert compare(snap, cur) == []


def test_extra_citations_alone_never_fail_the_check():
    pinned = ("EID1",)
    snap = {"entries": {"K": _entry(citations=pinned)}}
    cur = {"entries": {"K": _replicated([
        _fp(citations=("EID1", "EID9", "EID7")),
    ], mode_b=_fp(citations=pinned))}}
    assert compare(snap, cur) == []


def test_a_pinned_citation_absent_from_every_draw_is_reported():
    pinned = ("EID1", "EID2")
    snap = {"entries": {"K": _entry(citations=pinned)}}
    cur = {"entries": {"K": _replicated([
        _fp(citations=("EID1", "EID9")), _fp(citations=("EID1", "EID7")),
    ], mode_b=_fp(citations=pinned))}}
    diffs = compare(snap, cur)
    assert len(diffs) == 1
    assert "EID2" in diffs[0] and "absent from all 2 draws" in diffs[0]


def test_mode_b_stays_strict_when_mode_a_is_replicated():
    snap = {"entries": {"K": _entry()}}
    cur = {"entries": {"K": _replicated([_fp()], mode_b=_fp(onco="VUS"))}}
    diffs = compare(snap, cur)
    assert any("mode_b" in d and "oncogenicity" in d for d in diffs)
    assert not any("mode_a" in d for d in diffs)


def test_a_run_without_replicates_is_still_compared_strictly():
    snap = {"entries": {"K": _entry()}}
    cur = {"entries": {"K": _entry(onco="VUS")}}
    diffs = compare(snap, cur)
    assert any("mode_a" in d and "oncogenicity" in d for d in diffs)


def test_config_drift_names_the_prompt_that_moved():
    snap = {"provenance": {"model_name": "gpt-4o-mini", "prompt_hash": "aaa",
                           "guardrail_version": "1.0",
                           "prompt_hashes": {"classify": "c1", "verify": "v1"}}}
    cur = {"model_name": "gpt-4o-mini", "prompt_hash": "bbb", "guardrail_version": "1.0",
           "prompt_hashes": {"classify": "c2", "verify": "v1"}}
    notes = config_drift(snap, cur)
    assert any("prompt[classify]" in n for n in notes)
    assert not any("prompt[verify]" in n for n in notes)


def test_config_drift_flags_a_model_substitution():
    snap = {"provenance": {"model_name": "gpt-4o-mini", "prompt_hash": "aaa",
                           "guardrail_version": "1.0", "prompt_hashes": {}}}
    cur = {"model_name": "gpt-4o", "prompt_hash": "aaa", "guardrail_version": "1.0",
           "prompt_hashes": {}}
    assert any("model_name" in n for n in config_drift(snap, cur))
