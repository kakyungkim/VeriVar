"""Tests for the bring-your-own-VCF interpretation backend (``src.interpret``).

No network and no API key: a stub aggregator injects a hand-built bundle so the
heavy hybrid-retriever / dense-index path is NOT exercised here (that is left to
manual verification — see the task report). These cover (a) ``related_cancers``
extraction from a bundle and (b) ``interpret_variants`` running with
``cancer_type=None`` while still returning the new ``related_cancers`` field.
"""
from __future__ import annotations

from src.interpret import _related_cancers, interpret_variants
from src.models import (
    ClinicalTrial,
    DrugAssociation,
    Evidence,
    EvidenceBundle,
    Variant,
)


def _bundle() -> EvidenceBundle:
    """Bundle whose disease/condition strings span evidences, drugs and trials,
    with duplicate casing and a blank to exercise dedup + cleaning."""
    return EvidenceBundle(
        variant_key="BRAF p.V600E",
        evidences=[
            Evidence(id="CIViC:EID1", source="CIViC", gene="BRAF",
                     variant="V600E", disease="Melanoma", statement="x"),
            Evidence(id="CIViC:EID2", source="CIViC", gene="BRAF",
                     variant="V600E", disease="melanoma", statement="y"),
            Evidence(id="CIViC:EID3", source="CIViC", gene="BRAF",
                     variant="V600E", disease="  ", statement="z"),
        ],
        drugs=[DrugAssociation(drug="Vemurafenib", source="CIViC",
                               disease="Colorectal Adenocarcinoma")],
        trials=[ClinicalTrial(nct_id="NCT001",
                              conditions=["Thyroid Cancer", "Melanoma"])],
    )


def test_related_cancers_dedup_sorted():
    out = _related_cancers(_bundle())
    # "Melanoma"/"melanoma" collapse (first casing kept); blank dropped; sorted ci.
    assert out == ["Colorectal Adenocarcinoma", "Melanoma", "Thyroid Cancer"]


def test_related_cancers_empty_bundle():
    assert _related_cancers(EvidenceBundle(variant_key="X p.Y")) == []


class _StubAggregator:
    """Returns a fixed bundle regardless of input — no network, no snapshots."""

    def __init__(self, bundle: EvidenceBundle):
        self._bundle = bundle

    def for_variant_obj(self, variant: Variant) -> EvidenceBundle:
        return self._bundle


def test_interpret_variants_cancer_type_none():
    v = Variant(chrom="7", pos=140453136, ref="A", alt="T",
                gene="BRAF", hgvsp="p.V600E", cancer_type=None)
    rows = interpret_variants(
        [v], use_llm=False,
        aggregator=_StubAggregator(_bundle()),
        graph=None,  # skip KnowledgeGraph; ctx stays None
    )
    assert len(rows) == 1
    row = rows[0]
    # Did not crash with cancer_type=None; deterministic arm ran.
    assert row["cancer_type"] is None
    assert row["mode_a"]["abstained"] is True  # Mode A not run (use_llm=False)
    assert row["mode_b"]["oncogenicity"] != "—"  # rule arm produced a real label
    # New field present and correctly extracted.
    assert row["related_cancers"] == [
        "Colorectal Adenocarcinoma", "Melanoma", "Thyroid Cancer"]
    # Existing keys unchanged / present.
    for k in ("variant_key", "gene", "hgvsp", "evidence_tier",
              "n_evidence", "n_drugs", "n_trials", "bundle", "related_variants"):
        assert k in row


def test_interpret_variants_am_online_builds_live_annotator(monkeypatch, tmp_path):
    """``interpret_variants(am_online=True)`` (no explicit aggregator) wires a LIVE
    AlphaMissense annotator into the offline fallback path.

    No real network: an empty AM cache forces a miss and ``urlopen`` is mocked,
    so we assert a fetch was attempted and AlphaMissense evidence populated for a
    GRCh38 missense variant — where the default (offline) path returns nothing.
    """
    import json
    import src.knowledge.alphamissense as am_mod

    fetched = {"n": 0}

    class _Resp:
        def __init__(self, payload):
            self._payload = payload
        def read(self):
            return json.dumps(self._payload).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=30):
        fetched["n"] += 1
        return _Resp([{"transcript_consequences": [
            {"alphamissense": {"am_pathogenicity": 0.96, "am_class": "likely_pathogenic"}}]}])

    monkeypatch.setattr(am_mod.urllib.request, "urlopen", fake_urlopen)
    # Do not pollute the committed cache file with the synthetic test entry.
    monkeypatch.setattr(am_mod.AlphaMissenseAnnotator, "_save", lambda self: None)

    # Synthetic GRCh38 missense coordinate NOT in any committed cache -> any AM
    # hit must come from a (mocked) live fetch, not the snapshot.
    v = Variant(chrom="1", pos=99999991, ref="C", alt="T", gene="TESTGENE",
                hgvsp="p.X1Y", variant_type="SNV", assembly="GRCh38",
                cancer_type=None)

    # Default (offline AM): cache miss -> no AlphaMissense evidence, no fetch.
    off = interpret_variants([v], use_llm=False, graph=None, am_online=False)
    assert fetched["n"] == 0
    assert not [e for e in off[0]["bundle"]["evidences"]
                if e["source"] == "AlphaMissense"]

    # am_online=True: cache miss -> live fetch -> AlphaMissense evidence present.
    on = interpret_variants([v], use_llm=False, graph=None, am_online=True)
    assert fetched["n"] >= 1
    am_ev = [e for e in on[0]["bundle"]["evidences"]
             if e["source"] == "AlphaMissense"]
    assert len(am_ev) == 1 and am_ev[0]["score"] == 0.96


def test_interpret_variants_zero_openai_calls_offline(monkeypatch):
    """use_llm=False must never construct/call the LLM client."""
    import src.classify.llm as llm_mod

    def _boom(*a, **k):  # pragma: no cover - should never run
        raise AssertionError("LLMClassifier must not be instantiated offline")

    monkeypatch.setattr(llm_mod.LLMClassifier, "__init__", _boom)
    v = Variant(chrom="7", pos=140453136, ref="A", alt="T",
                gene="BRAF", hgvsp="p.V600E", cancer_type="Melanoma")
    rows = interpret_variants([v], use_llm=False,
                              aggregator=_StubAggregator(_bundle()), graph=None)
    assert rows[0]["discordant"] is None
