"""Tests for the AlphaMissense annotator (offline; cache fixture, no network)."""
import json

import src.knowledge.alphamissense as am_mod
from src.models import Variant
from src.knowledge.alphamissense import AlphaMissenseAnnotator, vicc_code


def test_vicc_code_thresholds():
    assert vicc_code(0.99) == "OP1"     # pathogenic -> supporting oncogenic
    assert vicc_code(0.10) == "SBP1"    # benign -> supporting benign
    assert vicc_code(0.45) is None      # ambiguous -> no code


def _variant(**kw):
    base = dict(chrom="7", pos=140453136, ref="A", alt="T", gene="BRAF",
                hgvsp="p.V600E", variant_type="SNV")
    base.update(kw)
    return Variant(**base)


def test_annotator_emits_evidence_from_cache(tmp_path):
    cache = {"7:140453136:A>T": {"am_pathogenicity": 0.9927, "am_class": "pathogenic"}}
    p = tmp_path / "vep_cache.json"
    p.write_text(json.dumps(cache))

    ann = AlphaMissenseAnnotator(cache_path=p, offline=True)
    ev = ann.evidence_for_variant(_variant())
    assert len(ev) == 1
    assert ev[0].id == "AlphaMissense:7:140453136A>T"
    assert ev[0].score == 0.9927
    assert "pathogenic" in ev[0].statement and "OP1" in ev[0].statement


def test_annotator_skips_non_missense_and_unknown(tmp_path):
    ann = AlphaMissenseAnnotator(cache_path=tmp_path / "none.json", offline=True)
    # Indel -> skipped (AlphaMissense is missense-only).
    assert ann.evidence_for_variant(_variant(ref="ATG", alt="A", variant_type="INDEL")) == []
    # Missense SNV not in cache, offline -> no evidence (no fabrication).
    assert ann.evidence_for_variant(_variant(pos=999, ref="C", alt="G")) == []


def test_grch37_variant_hits_legacy_bare_cache_key(tmp_path):
    """Committed GRCh37 cache uses bare keys; a GRCh37 Variant must still hit them."""
    cache = {"7:140453136:A>T": {"am_pathogenicity": 0.9927, "am_class": "pathogenic"}}
    p = tmp_path / "vep_cache.json"
    p.write_text(json.dumps(cache))
    ann = AlphaMissenseAnnotator(cache_path=p, offline=True)
    # default assembly is GRCh37 -> legacy bare-key fallback resolves the entry
    ev = ann.evidence_for_variant(_variant())
    assert len(ev) == 1 and ev[0].score == 0.9927


def test_grch38_variant_does_not_use_legacy_bare_key(tmp_path):
    """GRCh38 must NOT read the bare GRCh37 key (coords mean different residues)."""
    cache = {"7:140453136:A>T": {"am_pathogenicity": 0.9927, "am_class": "pathogenic"}}
    p = tmp_path / "vep_cache.json"
    p.write_text(json.dumps(cache))
    ann = AlphaMissenseAnnotator(cache_path=p, offline=True)
    v38 = _variant(assembly="GRCh38")
    # offline + no GRCh38-prefixed entry -> no fallback to the bare key, no result
    assert ann.evidence_for_variant(v38) == []


def test_grch38_targets_grch38_mirror_and_writes_prefixed_key(tmp_path, monkeypatch):
    """A GRCh38 lookup hits the rest.ensembl.org mirror and caches under GRCh38|."""
    captured = {}

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
        captured["url"] = req.full_url
        payload = [{"transcript_consequences": [
            {"alphamissense": {"am_pathogenicity": 0.88, "am_class": "pathogenic"}}]}]
        return _Resp(payload)

    monkeypatch.setattr(am_mod.urllib.request, "urlopen", fake_urlopen)
    p = tmp_path / "vep_cache.json"
    ann = AlphaMissenseAnnotator(cache_path=p, offline=False)
    v38 = _variant(assembly="GRCh38")
    ev = ann.evidence_for_variant(v38)

    assert len(ev) == 1
    # mirror selected by assembly
    assert captured["url"].startswith("https://rest.ensembl.org/")
    assert "grch37" not in captured["url"]
    # new entry written under the assembly-prefixed key, not the bare key
    saved = json.loads(p.read_text())
    assert "GRCh38|7:140453136:A>T" in saved
    assert "7:140453136:A>T" not in saved


def test_factory_am_online_flag_controls_annotator_offline():
    """``build_aggregator(am_online=...)`` flips ONLY the AlphaMissense annotator.

    Default stays offline (cohort/reproducibility); ``am_online=True`` builds a
    LIVE AlphaMissense annotator while CIViC/DGIdb/trials stay on the committed
    snapshots. No network: we only inspect the constructed annotator's flag.
    """
    from src.knowledge.factory import build_aggregator

    def _am(agg):
        return [a for a in agg.variant_annotators
                if isinstance(a, AlphaMissenseAnnotator)][0]

    # Default: AM offline.
    assert _am(build_aggregator()).offline is True
    assert _am(build_aggregator(offline=True)).offline is True
    # am_online=True: AM online even with the rest of the aggregator offline.
    assert _am(build_aggregator(offline=True, am_online=True)).offline is False


def test_am_online_would_fetch_on_cache_miss_not_return_none(tmp_path, monkeypatch):
    """An online annotator FETCHES on a cache miss instead of abstaining.

    Mocks ``urlopen`` so no real network is hit; asserts the fetch was attempted
    and produced evidence, where an offline annotator returns ``[]``.
    """
    fetched = {}

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
        fetched["called"] = True
        return _Resp([{"transcript_consequences": [
            {"alphamissense": {"am_pathogenicity": 0.97, "am_class": "likely_pathogenic"}}]}])

    monkeypatch.setattr(am_mod.urllib.request, "urlopen", fake_urlopen)
    p = tmp_path / "vep_cache.json"  # empty -> guaranteed cache miss
    v38 = _variant(assembly="GRCh38", pos=12345)

    # Offline annotator: cache miss -> abstain, no fetch.
    off = AlphaMissenseAnnotator(cache_path=p, offline=True)
    assert off.evidence_for_variant(v38) == []
    assert "called" not in fetched

    # Online annotator: cache miss -> fetch, evidence emitted.
    on = AlphaMissenseAnnotator(cache_path=p, offline=False)
    ev = on.evidence_for_variant(v38)
    assert fetched.get("called") is True
    assert len(ev) == 1 and ev[0].score == 0.97


def test_grch37_online_writes_prefixed_key(tmp_path, monkeypatch):
    """GRCh37 online lookup targets the grch37 mirror; new key is prefixed."""
    captured = {}

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
        captured["url"] = req.full_url
        return _Resp([{"transcript_consequences": [
            {"alphamissense": {"am_pathogenicity": 0.91, "am_class": "pathogenic"}}]}])

    monkeypatch.setattr(am_mod.urllib.request, "urlopen", fake_urlopen)
    p = tmp_path / "vep_cache.json"
    ann = AlphaMissenseAnnotator(cache_path=p, offline=False)
    ann.evidence_for_variant(_variant())  # default GRCh37
    assert "grch37.rest.ensembl.org" in captured["url"]
    saved = json.loads(p.read_text())
    assert "GRCh37|7:140453136:A>T" in saved
