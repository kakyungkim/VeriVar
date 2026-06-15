"""Tests for bring-your-own-VCF ingestion + dual-mode interpretation.

All tests run WITHOUT network and WITHOUT an API key:
  * ``parse_vcf`` is pure text parsing.
  * ``annotate_variants`` is driven through an injected ``_fetcher`` (or a
    monkeypatched ``urlopen``) returning a canned VEP response — no real HTTP.
  * ``interpret_variants(use_llm=False)`` runs the offline aggregator + rule arm
    only — no OpenAI call.
"""
import json
import io

import pytest

from src.cohort.vcf_loader import (
    parse_vcf,
    annotate_variants,
    detect_assembly,
    _pick_consequence,
    load_panel_bed,
    _in_panel,
)
from src.interpret import interpret_variants, MODE_A_NOT_RUN
from src.models import Variant


# --------------------------------------------------------------------------- #
# parse_vcf
# --------------------------------------------------------------------------- #
SMALL_VCF = """##fileformat=VCFv4.2
##source=test
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
7\t140453136\t.\tA\tT\t.\tPASS\t.
17\t7577120\trs1\tC\tG,A\t.\tPASS\t.
10\t89000000\t.\tC\tT\t.\tq10\t.
3\tNOTANUMBER\t.\tA\tG\t.\tPASS\t.
"""


def test_parse_vcf_skips_headers_and_parses_records():
    records = parse_vcf(SMALL_VCF)
    # 1 (chr7) + 2 (multiallelic chr17) + 1 (chr10) = 4; the bad-POS row is dropped.
    assert len(records) == 4
    first = records[0]
    assert first == {"chrom": "7", "pos": 140453136, "ref": "A", "alt": "T"}


def test_parse_vcf_splits_multiallelic():
    records = parse_vcf(SMALL_VCF)
    chr17 = [r for r in records if r["chrom"] == "17"]
    assert len(chr17) == 2
    assert {r["alt"] for r in chr17} == {"G", "A"}
    assert all(r["pos"] == 7577120 and r["ref"] == "C" for r in chr17)


def test_parse_vcf_drop_non_pass():
    # The chr10 row has FILTER=q10 -> dropped when drop_non_pass=True.
    records = parse_vcf(SMALL_VCF, drop_non_pass=True)
    assert all(r["chrom"] != "10" for r in records)
    assert len(records) == 3


def test_parse_vcf_strips_chr_prefix_and_symbolic_alts():
    vcf = "chr1\t100\t.\tA\t<DEL>\t.\tPASS\t.\nchrX\t200\t.\tG\tC\t.\tPASS\t."
    records = parse_vcf(vcf)
    assert len(records) == 1  # symbolic <DEL> skipped
    assert records[0]["chrom"] == "X"


# --------------------------------------------------------------------------- #
# annotate_variants (VEP mocked)
# --------------------------------------------------------------------------- #
def _canned_vep_missense():
    """A minimal VEP region response: BRAF V600E missense, canonical transcript.

    Carries the enrichment fields the loader now requests (``af=1&af_gnomad=1&
    sift=1&polyphen=1&mane=1&numbers=1&variant_class=1``): IMPACT, transcript id +
    MANE flag, protein_start/amino_acids, SIFT/PolyPhen prediction+score, a
    record-level ``variant_class`` and ``colocated_variants`` carrying an rsID,
    a COSMIC id, and a gnomAD allele frequency.
    """
    return [{
        "input": "7 140453136 . A T",
        "variant_class": "SNV",
        "colocated_variants": [
            {"id": "rs113488022",
             "frequencies": {"T": {"gnomad": 0.00001234, "afr": 0.0}}},
            {"id": "COSV56056643"},
        ],
        "transcript_consequences": [
            {"gene_symbol": "BRAF", "canonical": 1, "mane_select": "NM_004333.6",
             "transcript_id": "ENST00000288602",
             "impact": "MODERATE",
             "consequence_terms": ["missense_variant"],
             "hgvsp": "ENSP00000288602.6:p.Val600Glu",
             "hgvsc": "ENST00000288602.6:c.1799T>A",
             "protein_start": 600, "protein_end": 600, "amino_acids": "V/E",
             "sift_prediction": "deleterious", "sift_score": 0.0,
             "polyphen_prediction": "probably_damaging", "polyphen_score": 0.971},
            {"gene_symbol": "BRAF",
             "consequence_terms": ["intron_variant"]},
        ],
    }]


def _canned_vep_silent():
    return [{
        "transcript_consequences": [
            {"gene_symbol": "FOO", "canonical": 1,
             "consequence_terms": ["synonymous_variant"]},
        ],
    }]


def _batch_missense(host, recs, timeout):
    """Batch fetcher mock: echo a BRAF V600E hit for chr7, silent for others.

    Returns VEP-batch-shaped items with the ``input`` echo so the loader can match
    each item back to its record by coordinate key.
    """
    out = []
    for r in recs:
        if r["chrom"] == "7":
            item = dict(_canned_vep_missense()[0])
        else:
            item = dict(_canned_vep_silent()[0])
        item["input"] = f"{r['chrom']} {r['pos']} . {r['ref']} {r['alt']} . . ."
        out.append(item)
    return out


def test_annotate_variants_builds_variant_from_vep(monkeypatch):
    records = [{"chrom": "7", "pos": 140453136, "ref": "A", "alt": "T"}]

    def fake_fetch(host, chrom, pos, ref, alt, timeout):
        assert "grch37" in host  # GRCh37 host selected
        return _canned_vep_missense()

    result = annotate_variants(records, assembly="GRCh37", cancer_type="Melanoma",
                               _fetcher=fake_fetch, use_cache=False)
    assert len(result.variants) == 1
    assert not result.skipped
    v = result.variants[0]
    assert v.gene == "BRAF"
    # VEP returns 3-letter (p.Val600Glu); annotate_variants normalizes to the
    # 1-letter form the knowledge bases key on, so evidence/trials actually match.
    assert v.hgvsp == "p.V600E"
    assert v.variant_type == "SNV"
    assert v.cancer_type == "Melanoma"
    assert v.key == "BRAF p.V600E"


def test_annotate_variants_populates_vep_enrichment(monkeypatch):
    """v.vep carries the enriched fields parsed from the SAME VEP response."""
    records = [{"chrom": "7", "pos": 140453136, "ref": "A", "alt": "T"}]
    result = annotate_variants(records, assembly="GRCh37",
                               _fetcher=lambda *a: _canned_vep_missense(),
                               use_cache=False)
    v = result.variants[0]
    assert isinstance(v.vep, dict)
    vep = v.vep
    # transcript-level fields
    assert vep["consequence"] == "missense_variant"
    assert vep["impact"] == "MODERATE"
    assert vep["transcript_id"] == "ENST00000288602"
    assert vep["canonical"] is True
    assert vep["mane"] == "NM_004333.6"
    assert vep["hgvsc"] == "c.1799T>A"          # ENST...: prefix stripped
    assert vep["protein_position"] == "600"
    assert vep["amino_acids"] == "V/E"
    # predictors: prediction + numeric score
    assert vep["sift"] == {"prediction": "deleterious", "score": 0.0}
    assert vep["polyphen"] == {"prediction": "probably_damaging", "score": 0.971}
    # colocated variants: rsID, COSMIC id, gnomAD AF
    assert vep["rsid"] == "rs113488022"
    assert vep["cosmic"] == "COSV56056643"
    assert vep["existing_variation"] == "rs113488022"
    assert vep["gnomad_af"] == pytest.approx(0.00001234)
    assert vep["variant_class"] == "SNV"


def test_annotate_variants_vep_missing_fields_stay_none(monkeypatch):
    """A bare VEP response (no predictors/colocated/AF) leaves those keys None."""
    bare = [{
        "input": "7 1 . A T",
        "transcript_consequences": [
            {"gene_symbol": "BRAF", "canonical": 1,
             "consequence_terms": ["missense_variant"],
             "hgvsp": "ENSP:p.Val600Glu"},
        ],
    }]
    result = annotate_variants([{"chrom": "7", "pos": 1, "ref": "A", "alt": "T"}],
                               _fetcher=lambda *a: bare, use_cache=False)
    vep = result.variants[0].vep
    assert vep["consequence"] == "missense_variant"
    assert vep["impact"] is None
    assert vep["hgvsc"] is None
    assert vep["protein_position"] is None
    assert vep["amino_acids"] is None
    assert vep["rsid"] is None
    assert vep["cosmic"] is None
    assert vep["gnomad_af"] is None
    assert vep["sift"] is None
    assert vep["polyphen"] is None


def test_annotate_variants_batch_fetcher_shape():
    """The batch POST seam: one call carries many variants, matched by input echo."""
    records = [
        {"chrom": "7", "pos": 140453136, "ref": "A", "alt": "T"},  # BRAF hit
        {"chrom": "1", "pos": 100, "ref": "A", "alt": "G"},        # silent -> skip
    ]
    calls = {"n": 0}

    def batch(host, recs, timeout):
        calls["n"] += 1
        assert "grch37" in host
        return _batch_missense(host, recs, timeout)

    result = annotate_variants(records, _batch_fetcher=batch, use_cache=False)
    assert calls["n"] == 1  # both variants in a single POST
    assert len(result.variants) == 1 and result.variants[0].gene == "BRAF"
    assert len(result.skipped) == 1


def test_annotate_variants_batch_chunking():
    """batch_size splits the misses across multiple POSTs."""
    records = [{"chrom": "7", "pos": 100 + i, "ref": "A", "alt": "T"} for i in range(5)]
    chunks = []

    def batch(host, recs, timeout):
        chunks.append(len(recs))
        return _batch_missense(host, recs, timeout)

    annotate_variants(records, _batch_fetcher=batch, use_cache=False, batch_size=2)
    assert chunks == [2, 2, 1]


def test_annotate_variants_skips_silent():
    records = [{"chrom": "1", "pos": 100, "ref": "A", "alt": "G"}]
    result = annotate_variants(records, _fetcher=lambda *a: _canned_vep_silent(),
                               use_cache=False)
    assert not result.variants
    assert len(result.skipped) == 1
    assert "non-coding" in result.skipped[0].reason or "silent" in result.skipped[0].reason


def test_annotate_variants_one_failure_does_not_kill_batch():
    records = [
        {"chrom": "7", "pos": 140453136, "ref": "A", "alt": "T"},
        {"chrom": "9", "pos": 999, "ref": "C", "alt": "T"},
    ]

    def flaky_fetch(host, chrom, pos, ref, alt, timeout):
        if chrom == "9":
            raise OSError("boom")
        return _canned_vep_missense()

    # Legacy per-variant seam keeps true per-record failure isolation.
    result = annotate_variants(records, _fetcher=flaky_fetch, use_cache=False)
    assert len(result.variants) == 1
    assert len(result.skipped) == 1
    assert "failed" in result.skipped[0].reason or "error" in result.skipped[0].reason


def test_annotate_variants_batch_chunk_failure_isolated():
    """A failed chunk skips only its own records; other chunks still annotate."""
    records = [{"chrom": "7", "pos": 100 + i, "ref": "A", "alt": "T"} for i in range(4)]

    def batch(host, recs, timeout):
        if any(r["pos"] >= 102 for r in recs):  # second chunk explodes
            raise OSError("boom")
        return _batch_missense(host, recs, timeout)

    result = annotate_variants(records, _batch_fetcher=batch, use_cache=False, batch_size=2)
    assert len(result.variants) == 2
    assert len(result.skipped) == 2
    assert all("failed" in s.reason for s in result.skipped)


def test_annotate_variants_assembly_selection():
    seen = {}

    def capture(host, *a):
        seen["host"] = host
        return _canned_vep_missense()

    annotate_variants([{"chrom": "7", "pos": 1, "ref": "A", "alt": "T"}],
                      assembly="GRCh38", _fetcher=capture, use_cache=False)
    assert seen["host"] == "https://rest.ensembl.org"


def test_annotate_variants_rejects_unknown_assembly():
    with pytest.raises(ValueError):
        annotate_variants([], assembly="hg00")


def test_annotate_variants_cache_hit_miss(tmp_path):
    """First run POSTs misses + writes cache; second run hits cache, zero network."""
    cache = tmp_path / "vep_cache.json"
    records = [{"chrom": "7", "pos": 140453136, "ref": "A", "alt": "T"}]
    calls = {"n": 0}

    def batch(host, recs, timeout):
        calls["n"] += 1
        return _batch_missense(host, recs, timeout)

    r1 = annotate_variants(records, _batch_fetcher=batch, cache_path=cache)
    assert calls["n"] == 1 and r1.variants[0].gene == "BRAF"
    assert cache.exists()  # cache written

    def boom(host, recs, timeout):
        raise AssertionError("network must not be hit on a cache hit")

    r2 = annotate_variants(records, _batch_fetcher=boom, cache_path=cache)
    assert calls["n"] == 1  # unchanged: no new fetch
    assert r2.variants[0].gene == "BRAF"


def test_annotate_variants_max_variants_cap():
    """Records beyond the cap are skipped (before any network) with a clear reason."""
    records = [{"chrom": "7", "pos": 100 + i, "ref": "A", "alt": "T"} for i in range(5)]
    seen = {"n": 0}

    def batch(host, recs, timeout):
        seen["n"] += len(recs)
        return _batch_missense(host, recs, timeout)

    result = annotate_variants(records, _batch_fetcher=batch, use_cache=False,
                               max_variants=3)
    assert seen["n"] == 3  # only the first 3 were annotated
    assert len(result.variants) == 3
    assert len(result.skipped) == 2
    assert all(s.reason == "exceeded max_variants cap" for s in result.skipped)


def test_annotate_variants_panel_filter_post_vep():
    """panel_genes drops VEP-resolved genes outside the panel (post-VEP, by symbol)."""
    records = [
        {"chrom": "7", "pos": 140453136, "ref": "A", "alt": "T"},  # BRAF -> in panel
        {"chrom": "1", "pos": 200, "ref": "A", "alt": "T"},        # FOO_NS -> off panel
    ]

    def batch(host, recs, timeout):
        out = []
        for r in recs:
            if r["chrom"] == "7":
                item = dict(_canned_vep_missense()[0])
            else:  # a non-silent gene that is simply outside the panel
                item = {"transcript_consequences": [
                    {"gene_symbol": "FOO_NS", "canonical": 1,
                     "consequence_terms": ["missense_variant"],
                     "hgvsp": "ENSP:p.Ala1Thr"}]}
            item["input"] = f"{r['chrom']} {r['pos']} . {r['ref']} {r['alt']} . . ."
            out.append(item)
        return out

    result = annotate_variants(records, _batch_fetcher=batch, use_cache=False,
                               panel_genes=["BRAF", "KRAS"])
    assert len(result.variants) == 1 and result.variants[0].gene == "BRAF"
    assert len(result.skipped) == 1
    assert result.skipped[0].reason == "outside panel_genes"


def test_annotate_variants_monkeypatched_urlopen(monkeypatch):
    """Exercise the real batch fetch path with urlopen monkeypatched (no network)."""
    import src.cohort.vcf_loader as mod

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            # VEP batch echoes the input; supply it so matching succeeds.
            item = dict(_canned_vep_missense()[0])
            item["input"] = "7 140453136 . A T . . ."
            return json.dumps([item]).encode()

    monkeypatch.setattr(mod.urllib.request, "urlopen",
                        lambda req, timeout=0: FakeResp())
    # json.load reads from a file-like; FakeResp.read returns bytes -> wrap.
    monkeypatch.setattr(mod.json, "load", lambda r: json.loads(r.read().decode()))

    result = annotate_variants([{"chrom": "7", "pos": 140453136, "ref": "A", "alt": "T"}],
                               use_cache=False)
    assert result.variants and result.variants[0].gene == "BRAF"


# --------------------------------------------------------------------------- #
# driver-gene panel region filter (pre-VEP) — offline, no network
# --------------------------------------------------------------------------- #
# Tiny hand-built BED (0-based half-open [start, end)). Two genes on different
# contigs; chrom names include a 'chr' prefix to exercise normalization.
TINY_BED = """# test panel
# chrom\tstart\tend\tgene
chr7\t100\t200\tGENEA
12\t1000\t1100\tGENEB
"""


def _write_bed(tmp_path):
    p = tmp_path / "tiny_panel.bed"
    p.write_text(TINY_BED)
    return p


def test_load_panel_bed_parses_and_normalizes(tmp_path):
    bed = load_panel_bed(_write_bed(tmp_path))
    # 'chr7' normalized to '7'; comments skipped.
    assert set(bed.keys()) == {"7", "12"}
    assert bed["7"] == [(100, 200, "GENEA")]
    assert bed["12"] == [(1000, 1100, "GENEB")]


def test_in_panel_overlap_boundaries(tmp_path):
    bed = load_panel_bed(_write_bed(tmp_path))
    # BED [100,200) 0-based <-> 1-based pos in (100, 200] i.e. 101..200 inclusive.
    assert _in_panel({"chrom": "7", "pos": 150}, bed) is True
    assert _in_panel({"chrom": "chr7", "pos": 200}, bed) is True   # right edge in
    assert _in_panel({"chrom": "7", "pos": 100}, bed) is False     # left edge out
    assert _in_panel({"chrom": "7", "pos": 201}, bed) is False     # past end
    assert _in_panel({"chrom": "5", "pos": 150}, bed) is False     # other contig


def test_region_filter_drops_offpanel_before_vep(tmp_path):
    """Off-panel records are skipped pre-VEP: the batch fetcher never sees them."""
    bed_path = _write_bed(tmp_path)
    records = [
        {"chrom": "7", "pos": 150, "ref": "A", "alt": "T"},    # in GENEA  -> annotate
        {"chrom": "12", "pos": 1050, "ref": "C", "alt": "G"},  # in GENEB  -> annotate
        {"chrom": "1", "pos": 500, "ref": "A", "alt": "T"},    # off-panel -> skip
        {"chrom": "7", "pos": 50, "ref": "A", "alt": "T"},     # before GENEA -> skip
    ]
    fetched = []

    def batch(host, recs, timeout):
        fetched.extend(recs)  # record exactly which coordinates hit the network
        out = []
        for r in recs:
            item = dict(_canned_vep_missense()[0])
            item["input"] = f"{r['chrom']} {r['pos']} . {r['ref']} {r['alt']} . . ."
            out.append(item)
        return out

    result = annotate_variants(records, panel_bed=bed_path, _batch_fetcher=batch,
                               use_cache=False)
    # Only the two in-panel records reached the VEP fetcher.
    assert len(fetched) == 2
    assert {(r["chrom"], r["pos"]) for r in fetched} == {("7", 150), ("12", 1050)}
    # The two off-panel records are skipped with the region reason (pre-VEP).
    offpanel = [s for s in result.skipped if s.reason == "outside driver-gene panel"]
    assert len(offpanel) == 2
    assert {(s.record["chrom"], s.record["pos"]) for s in offpanel} == {("1", 500), ("7", 50)}


def test_region_filter_composes_with_panel_genes(tmp_path):
    """Region pre-filter (BED) and symbol post-filter (panel_genes) compose."""
    bed_path = _write_bed(tmp_path)
    records = [
        {"chrom": "7", "pos": 150, "ref": "A", "alt": "T"},    # in-region, BRAF
        {"chrom": "12", "pos": 1050, "ref": "C", "alt": "G"},  # in-region, off-symbol
        {"chrom": "1", "pos": 500, "ref": "A", "alt": "T"},    # off-region
    ]
    fetched = []

    def batch(host, recs, timeout):
        fetched.extend(recs)
        out = []
        for r in recs:
            if r["chrom"] == "7":
                item = dict(_canned_vep_missense()[0])  # gene_symbol BRAF
            else:
                item = {"transcript_consequences": [
                    {"gene_symbol": "OTHER", "canonical": 1,
                     "consequence_terms": ["missense_variant"],
                     "hgvsp": "ENSP:p.Ala1Thr"}]}
            item["input"] = f"{r['chrom']} {r['pos']} . {r['ref']} {r['alt']} . . ."
            out.append(item)
        return out

    result = annotate_variants(records, panel_bed=bed_path, panel_genes=["BRAF"],
                               _batch_fetcher=batch, use_cache=False)
    # off-region never fetched; both in-region fetched.
    assert len(fetched) == 2
    # Only BRAF survives the post-VEP symbol filter.
    assert len(result.variants) == 1 and result.variants[0].gene == "BRAF"
    reasons = sorted(s.reason for s in result.skipped)
    assert reasons == ["outside driver-gene panel", "outside panel_genes"]


def test_committed_panel_beds_resolve_all_27_genes():
    """The committed BEDs (Ensembl-sourced) cover the 27-gene driver panel."""
    from src.cohort.vcf_loader import PANEL_BED_FILES
    for assembly in ("GRCH37", "GRCH38"):
        bed = load_panel_bed(PANEL_BED_FILES[assembly])
        genes = {g for ivs in bed.values() for (_s, _e, g) in ivs}
        assert len(genes) == 27, f"{assembly}: {len(genes)} genes"
        assert {"BRAF", "KRAS", "TP53", "BRCA1", "BRCA2"} <= genes


def test_pick_consequence_prefers_canonical_coding():
    tc = _pick_consequence(_canned_vep_missense()[0])
    assert tc["gene_symbol"] == "BRAF"
    assert "missense_variant" in tc["consequence_terms"]


# --------------------------------------------------------------------------- #
# interpret_variants (offline, no API key)
# --------------------------------------------------------------------------- #
COHORT_KEYS = {
    "variant_key", "gene", "hgvsp", "cancer_type", "variant_type",
    "evidence_tier", "sample_ids", "n_evidence", "n_drugs", "n_trials",
    "mode_a", "mode_b", "discordant", "bundle", "related_variants",
}


def test_interpret_variants_offline_shape_and_no_llm(monkeypatch):
    # Guarantee no API key in this test environment.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Make any accidental LLM construction explode (proves use_llm=False is inert).
    import src.classify.llm as llm_mod
    monkeypatch.setattr(llm_mod.LLMClassifier, "classify",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called")))

    variants = [
        Variant(chrom="7", pos=140453136, ref="A", alt="T", gene="BRAF",
                hgvsp="p.V600E", variant_type="SNV", cancer_type="Cutaneous Melanoma"),
        # A variant with (almost certainly) no variant-specific evidence -> abstains.
        Variant(chrom="1", pos=12345, ref="C", alt="T", gene="ZZZ9",
                hgvsp="p.A1B", variant_type="SNV", cancer_type="Glioma"),
    ]
    rows = interpret_variants(variants, use_llm=False)
    assert len(rows) == 2
    for row in rows:
        assert COHORT_KEYS.issubset(row.keys())
        # Mode A is the explicit "not run" marker when offline.
        assert row["mode_a"]["rationale"] == MODE_A_NOT_RUN["rationale"]
        assert row["mode_a"]["abstained"] is True
        assert row["discordant"] is None
        # Mode B (deterministic rule) is a real ClassificationResult dict.
        assert set(row["mode_b"]) >= {"oncogenicity", "tier", "rationale",
                                      "citations", "abstained"}


def test_interpret_variants_abstains_without_evidence(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    v = Variant(chrom="1", pos=999999, ref="C", alt="T", gene="NOTAGENE",
                hgvsp="p.X1Y", variant_type="SNV", cancer_type="Glioma")
    rows = interpret_variants([v], use_llm=False)
    row = rows[0]
    # No retrievable variant-specific evidence -> rule arm abstains (VUS).
    assert row["n_evidence"] == 0
    assert row["evidence_tier"] == "none"
    assert row["mode_b"]["oncogenicity"] == "VUS"
    assert row["mode_b"]["abstained"] is True


# --------------------------------------------------------------------------- #
# detect_assembly (pure header parsing, no network)
# --------------------------------------------------------------------------- #
def test_detect_assembly_grch37_reference():
    vcf = "##fileformat=VCFv4.2\n##reference=file:///ref/human_g1k_v37.fasta\n#CHROM\tPOS\n"
    assert detect_assembly(vcf) == "GRCh37"


def test_detect_assembly_hg19_alias():
    assert detect_assembly("##reference=hg19\n") == "GRCh37"


def test_detect_assembly_grch37_patch_via_contig():
    vcf = "##fileformat=VCFv4.2\n##contig=<ID=7,length=159138663,assembly=GRCh37.p13>\n"
    assert detect_assembly(vcf) == "GRCh37"


def test_detect_assembly_hg38_alias():
    assert detect_assembly("##reference=hg38\n") == "GRCh38"


def test_detect_assembly_grch38_assembly_line():
    assert detect_assembly("##assembly=GRCh38\n#CHROM\n") == "GRCh38"


def test_detect_assembly_grch38_contig_patch():
    vcf = "##contig=<ID=chr1,length=248956422,assembly=GRCh38.p14>\n"
    assert detect_assembly(vcf) == "GRCh38"


def test_detect_assembly_none_when_absent():
    vcf = "##fileformat=VCFv4.2\n##source=mycaller\n#CHROM\tPOS\n7\t140453136\t.\tA\tT\n"
    assert detect_assembly(vcf) is None


def test_detect_assembly_stops_at_data_lines():
    # A data line mentioning 'hg19' must NOT be picked up (only ## headers).
    vcf = "##fileformat=VCFv4.2\n7\t1\t.\tA\tT\t.\t.\thg19note\n"
    assert detect_assembly(vcf) is None


def test_annotate_variants_stamps_assembly_grch38():
    """A GRCh38 run stamps Variant.assembly so downstream lookups stay build-aware."""
    records = [{"chrom": "7", "pos": 140753336, "ref": "A", "alt": "T"}]

    def batch(host, recs, timeout):
        assert host == "https://rest.ensembl.org"  # GRCh38 mirror
        return _batch_missense(host, recs, timeout)

    result = annotate_variants(records, assembly="GRCh38",
                               _batch_fetcher=batch, use_cache=False)
    assert len(result.variants) == 1
    assert result.variants[0].assembly == "GRCh38"


def test_annotate_variants_default_assembly_grch37():
    records = [{"chrom": "7", "pos": 140453136, "ref": "A", "alt": "T"}]
    result = annotate_variants(records, _batch_fetcher=_batch_missense, use_cache=False)
    assert result.variants[0].assembly == "GRCh37"


# --------------------------------------------------------------------------- #
# to_annotated_vcf — VCF writer (pure, offline)
# --------------------------------------------------------------------------- #
from src.cohort.vcf_loader import to_annotated_vcf

# Two hand-made annotation rows (the shape the dashboard builds from ar.variants).
_ROWS = [
    {"chrom": "7", "pos": 140453136, "ref": "A", "alt": "T", "gene": "BRAF",
     "hgvsp": "p.V600E", "variant_type": "SNV", "assembly": "GRCh37"},
    {"chrom": "12", "pos": 25398284, "ref": "C", "alt": "A", "gene": "KRAS",
     "hgvsp": "p.G12C", "variant_type": "SNV", "assembly": "GRCh37"},
]

# Aligned minimal results dicts: row 0 has an AlphaMissense bundle item, row 1
# does not. mode_a/mode_b carry oncogenicity + tier (as model_dump emits them).
_RESULTS = [
    {
        "mode_a": {"oncogenicity": "Oncogenic", "tier": "Tier I"},
        "mode_b": {"oncogenicity": "Oncogenic", "tier": "Tier I"},
        "n_evidence": 5, "n_drugs": 3, "n_trials": 2,
        "bundle": {"evidences": [
            {"source": "CIViC", "score": None, "evidence_level": "B"},
            {"source": "AlphaMissense", "score": 0.987, "evidence_level": "likely_pathogenic"},
        ]},
    },
    {
        "mode_a": {"oncogenicity": "VUS", "tier": "Tier III"},
        "mode_b": {"oncogenicity": "Oncogenic", "tier": "Tier II"},
        "n_evidence": 1, "n_drugs": 0, "n_trials": 0,
        "bundle": {"evidences": [
            {"source": "DGIdb", "score": None, "evidence_level": None},
        ]},
    },
]


def _data_lines(vcf: str):
    return [ln for ln in vcf.splitlines() if ln and not ln.startswith("#")]


def test_to_annotated_vcf_full_mode_structure():
    vcf = to_annotated_vcf(_ROWS, _RESULTS)
    assert "##fileformat=VCFv4.2" in vcf
    assert "##source=VeriVar" in vcf
    assert "##INFO=<ID=VERIVAR" in vcf
    # Column header present.
    assert "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO" in vcf
    # One data line per row.
    data = _data_lines(vcf)
    assert len(data) == len(_ROWS)
    for ln in data:
        cols = ln.split("\t")
        assert len(cols) == 8                 # exactly 8 tab-columns
        assert cols[6] == "PASS"
        info = cols[7]
        assert info.startswith("VERIVAR=")
        fields = info[len("VERIVAR="):].split("|")
        assert len(fields) == 11              # full Format field count
        assert " " not in info                # spaces encoded — no raw space


def test_to_annotated_vcf_alphamissense_field():
    vcf = to_annotated_vcf(_ROWS, _RESULTS)
    data = _data_lines(vcf)
    # Row 0 has an AM item -> score formatted to 3dp; row 1 has none -> '.'.
    am0 = data[0].split("\t")[7][len("VERIVAR="):].split("|")[7]
    am1 = data[1].split("\t")[7][len("VERIVAR="):].split("|")[7]
    assert am0 == "0.987"
    assert am1 == "."


def test_to_annotated_vcf_annotate_only_three_fields():
    vcf = to_annotated_vcf(_ROWS, results=None)
    # Shorter Format in the INFO definition.
    assert "Format: Gene|HGVSp|Consequence" in vcf
    data = _data_lines(vcf)
    assert len(data) == len(_ROWS)
    for ln in data:
        cols = ln.split("\t")
        assert len(cols) == 8
        info = cols[7]
        assert info.startswith("VERIVAR=")
        assert len(info[len("VERIVAR="):].split("|")) == 3   # 3-field form
        assert " " not in info


def test_to_annotated_vcf_sanitizes_reserved_chars():
    rows = [{"chrom": "7", "pos": 1, "ref": "A", "alt": "T", "gene": "BRAF",
             "hgvsp": "p.V600E mut; weird=x,y|z", "variant_type": "missense variant",
             "assembly": "GRCh37"}]
    vcf = to_annotated_vcf(rows, results=None)
    info = _data_lines(vcf)[0].split("\t")[7]
    # No raw reserved chars survive inside the INFO column.
    body = info[len("VERIVAR="):]
    for ch in (" ", ";", "=", ","):
        assert ch not in body
    # Our own pipe delimiter only appears as the 2 field separators (3 fields).
    assert body.count("|") == 2


def test_to_annotated_vcf_assembly_in_header():
    vcf = to_annotated_vcf(_ROWS, _RESULTS, assembly="GRCh38")
    assert "##reference=GRCh38" in vcf
