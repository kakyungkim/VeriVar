"""Unit tests for the VCF parser (Phase 0 regression guards)."""
from pathlib import Path

import pandas as pd

from src.parser.vcf_parser import (
    parse_vcf_to_df,
    _classify_variant_type,
    _parse_first_float,
)

VCF_HEADER = (
    "##fileformat=VCFv4.2\n"
    "##INFO=<ID=GENE,Number=1,Type=String,Description=\"Gene symbol\">\n"
    "##INFO=<ID=HGVSp,Number=1,Type=String,Description=\"protein\">\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tTUMOR\n"
)


def _write_vcf(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "test.vcf"
    p.write_text(VCF_HEADER + body)
    return p


def test_classify_variant_type():
    assert _classify_variant_type("A", "G") == "SNV"
    assert _classify_variant_type("AT", "GC") == "SNV"  # MNV grouped with SNV
    assert _classify_variant_type("A", "ATG") == "INDEL"  # insertion
    assert _classify_variant_type("ATG", "A") == "INDEL"  # deletion


def test_parse_first_float_multiallelic():
    # Number=A field: take the matching (first) value, do not float() the whole string.
    assert _parse_first_float("0.5,0.3") == 0.5
    assert _parse_first_float("0.42") == 0.42
    assert _parse_first_float("") is None
    assert _parse_first_float(None) is None


def test_single_snv(tmp_path):
    body = "chr7\t55259515\t.\tT\tG\t100\tPASS\tGENE=EGFR;HGVSp=p.L858R\tGT:DP:AF\t0/1:500:0.50\n"
    df = parse_vcf_to_df(_write_vcf(tmp_path, body))
    assert len(df) == 1
    row = df.iloc[0]
    assert row["gene"] == "EGFR"
    assert row["vaf"] == 0.50
    assert row["dp"] == 500
    assert row["variant_type"] == "SNV"


def test_multiallelic_split(tmp_path):
    # One ALT pair of values per allele; parser must emit one row each with the
    # matching AF, instead of dropping VAF on a float() failure.
    body = "chr1\t100\t.\tC\tA,T\t100\tPASS\tGENE=FOO\tGT:DP:AF\t1/2:200:0.30,0.10\n"
    df = parse_vcf_to_df(_write_vcf(tmp_path, body))
    assert len(df) == 2
    assert sorted(df["alt"].tolist()) == ["A", "T"]
    assert sorted(df["vaf"].tolist()) == [0.10, 0.30]
    # DP is shared across the record's alleles.
    assert df["dp"].tolist() == [200, 200]


def test_vaf_threshold_keeps_unknown(tmp_path):
    # Variant with VAF below threshold is dropped; variant with unknown VAF is kept.
    body = (
        "chr1\t1\t.\tC\tA\t100\tPASS\tGENE=LOW\tGT:DP:AF\t0/1:200:0.02\n"
        "chr2\t2\t.\tG\tT\t100\tPASS\tGENE=NOAF\tGT:DP\t0/1:200\n"
    )
    df = parse_vcf_to_df(_write_vcf(tmp_path, body), vaf_threshold=0.05)
    genes = df["gene"].tolist()
    assert "LOW" not in genes      # 0.02 < 0.05 -> dropped
    assert "NOAF" in genes         # unknown VAF -> kept


def test_variant_type_filter(tmp_path):
    body = (
        "chr1\t1\t.\tC\tA\t100\tPASS\tGENE=SNVGENE\tGT:AF\t0/1:0.4\n"
        "chr2\t2\t.\tG\tGAA\t100\tPASS\tGENE=INSGENE\tGT:AF\t0/1:0.4\n"
    )
    snv = parse_vcf_to_df(_write_vcf(tmp_path, body), variant_type="SNV")
    assert snv["gene"].tolist() == ["SNVGENE"]
    indel = parse_vcf_to_df(_write_vcf(tmp_path, body), variant_type="INDEL")
    assert indel["gene"].tolist() == ["INSGENE"]
    mixed = parse_vcf_to_df(_write_vcf(tmp_path, body), variant_type="mixed")
    assert len(mixed) == 2
