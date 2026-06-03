"""Tests for the AlphaMissense annotator (offline; cache fixture, no network)."""
import json

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
