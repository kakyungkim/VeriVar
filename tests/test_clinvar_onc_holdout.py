"""Offline tests for the rebuilt ClinVar somatic-oncogenicity holdout.

Parsing is tested on synthetic ClinVar FTP lines (no network); the construction and
metrics are tested on synthetic records; the committed report is checked for internal
consistency when present (skipped on a fresh clone without the snapshot)."""
import json
import os

import pytest

from scripts.fetch_clinvar_oncogenicity import (
    collapse_oncogenicity,
    parse_date,
    parse_missense,
    parse_submission_summary,
    parse_variant_summary,
    parse_vep_record,
)
from scripts.run_clinvar_onc_holdout import (
    OUT,
    RuleArm,
    auroc,
    auroc_ci,
    build_holdout,
    detection_metrics,
    norm_key,
)

VS_HEADER = ("#AlleleID\tType\tName\tGeneID\tGeneSymbol\tHGNC_ID\tClinicalSignificance\t"
             "ClinSigSimple\tLastEvaluated\tRS# (dbSNP)\tnsv/esv (dbVar)\tRCVaccession\t"
             "PhenotypeIDS\tPhenotypeList\tOrigin\tOriginSimple\tAssembly\t"
             "ChromosomeAccession\tChromosome\tStart\tStop\tReferenceAllele\tAlternateAllele\t"
             "Cytogenetic\tReviewStatus\tNumberSubmitters\tGuidelines\tTestedInGTR\tOtherIDs\t"
             "SubmitterCategories\tVariationID\tPositionVCF\tReferenceAlleleVCF\t"
             "AlternateAlleleVCF\tSomaticClinicalImpact\tSomaticClinicalImpactLastEvaluated\t"
             "ReviewStatusClinicalImpact\tOncogenicity\tOncogenicityLastEvaluated\t"
             "ReviewStatusOncogenicity\tSCVsForAggregateGermlineClassification\t"
             "SCVsForAggregateSomaticClinicalImpact\tSCVsForAggregateOncogenicityClassification")


def _vs_line(vid, name, onc, rs="criteria provided, single submitter", asm="GRCh38",
             typ="single nucleotide variant", germ="Uncertain significance"):
    f = dict.fromkeys(VS_HEADER.lstrip("#").split("\t"), "-")
    f.update({"AlleleID": vid, "Type": typ, "Name": name, "GeneSymbol": "TP53",
              "ClinicalSignificance": germ, "Assembly": asm, "Chromosome": "17",
              "VariationID": vid, "PositionVCF": "7673802", "ReferenceAlleleVCF": "C",
              "AlternateAlleleVCF": "T", "Oncogenicity": onc,
              "OncogenicityLastEvaluated": "Mar 04, 2025", "ReviewStatusOncogenicity": rs,
              "OriginSimple": "somatic"})
    return "\t".join(f[k] for k in VS_HEADER.lstrip("#").split("\t")) + "\n"


def test_missense_parsing_and_collapse():
    assert parse_missense("NM_000546.6(TP53):c.818G>A (p.Arg273His)") == ("TP53", "p.R273H")
    assert parse_missense("NM_000546.6(TP53):c.916C>T (p.Arg306Ter)") is None
    assert parse_missense("NM_000546.6(TP53):c.639A>G (p.Arg213=)") is None
    assert collapse_oncogenicity("Likely oncogenic") == "ONC"
    assert collapse_oncogenicity("Uncertain significance") == "VUS"
    assert collapse_oncogenicity("Likely benign") == "BEN"
    assert collapse_oncogenicity("Conflicting classifications of oncogenicity") == "CONFLICT"
    assert parse_date("Mar 04, 2025") == "2025-03-04" and parse_date("-") == ""


def test_variant_summary_filter_uses_oncogenicity_column_not_germline():
    lines = [VS_HEADER + "\n",
             _vs_line("1", "NM_000546.6(TP53):c.818G>A (p.Arg273His)", "Oncogenic"),
             # germline-only record: germline Benign, no oncogenicity -> must be dropped
             _vs_line("2", "NM_000546.6(TP53):c.1G>A (p.Met1Ile)", "-", germ="Benign"),
             _vs_line("3", "NM_000546.6(TP53):c.2T>C (p.Met1Thr)", "Uncertain significance",
                      rs="no assertion criteria provided"),
             _vs_line("4", "NM_000546.6(TP53):c.818G>A (p.Arg273His)", "Oncogenic",
                      asm="GRCh37"),
             _vs_line("5", "NM_000546.6(TP53):c.916C>T (p.Arg306Ter)", "Oncogenic"),
             _vs_line("6", "NM_000546.6(TP53):c.3G>A (p.Met1Ile)", "Uncertain significance")]
    rows, funnel = parse_variant_summary(lines)
    assert [r["variation_id"] for r in rows] == ["1", "6"]
    assert [r["onc_class"] for r in rows] == ["ONC", "VUS"]
    assert funnel["dropped_no_assertion_criteria"] == 1
    assert funnel["dropped_snv_not_missense"] == 1
    assert rows[0]["onc_last_evaluated"] == "2025-03-04"


def test_submission_summary_keeps_only_oncogenicity_scvs():
    hdr = ("#VariationID\tClinicalSignificance\tDateLastEvaluated\tDescription\t"
           "SubmittedPhenotypeInfo\tReportedPhenotypeInfo\tReviewStatus\tCollectionMethod\t"
           "OriginCounts\tSubmitter\tSCV\tSubmittedGeneSymbol\tExplanationOfInterpretation\t"
           "SomaticClinicalImpact\tOncogenicity\tContributesToAggregateClassification\n")
    lines = ["##comment\n", hdr,
             "1\t-\tMar 04, 2025\t-\t-\t-\tcriteria provided, single submitter\tclinical"
             "\tsomatic:1\tLab A\tSCV1.1\tTP53\t-\t-\tOncogenic\tyes\n",
             "1\tBenign\tJan 01, 2020\t-\t-\t-\tcriteria provided, single submitter\tclinical"
             "\tgermline:1\tLab B\tSCV2.1\tTP53\t-\t-\t-\tyes\n"]
    out = parse_submission_summary(lines)
    assert list(out) == ["1"] and len(out["1"]) == 1
    assert out["1"][0]["submitter"] == "Lab A" and out["1"][0]["date"] == "2025-03-04"


def test_vep_record_parsing():
    rec = {"input": "17 7673802 . C T . . .", "allele_string": "C/T",
           "transcript_consequences": [
               {"gene_symbol": "TP53", "alphamissense": {"am_pathogenicity": 0.98,
                                                         "am_class": "likely_pathogenic"}},
               {"gene_symbol": "WRAP53", "alphamissense": {"am_pathogenicity": 0.99}}],
           "colocated_variants": [{"frequencies": {"T": {"gnomade": 1e-5, "gnomadg": 2e-5,
                                                         "af": 0.3}}}]}
    a = parse_vep_record(rec, "TP53")
    assert a["am_pathogenicity"] == 0.98          # other gene's transcript ignored
    assert a["gnomad_af"] == 2e-5                  # 1000G 'af' ignored
    assert parse_vep_record({"allele_string": "C/T"}, "TP53")["gnomad_af"] == 0.0


def _rec(vid, gene, aa, cls, label=None, n=1):
    lab = label or {"ONC": "Oncogenic", "VUS": "Uncertain significance",
                    "BEN": "Benign", "CONFLICT": "Conflicting"}[cls]
    return {"variation_id": vid, "gene": gene, "aa": aa, "onc_class": cls,
            "oncogenicity": lab, "n_onc_scvs": str(n), "onc_submitters": "Lab A"}


def test_build_holdout_excludes_horak_dedupes_and_drops_conflicts():
    rows = [_rec("1", "TP53", "p.R273H", "ONC"), _rec("2", "TP53", "p.R273H", "ONC", n=2),
            _rec("3", "PTEN", "p.R130Q", "ONC"), _rec("4", "PTEN", "p.R130Q", "VUS"),
            _rec("5", "KRAS", "p.G12D", "ONC"),           # Horak-70 member
            _rec("6", "BRAF", "p.X1Y", "CONFLICT"), _rec("7", "RB1", "p.A2V", "VUS")]
    out, funnel = build_holdout(rows, {norm_key("KRAS", "G12D")})
    keys = {r["key"]: r for r in out}
    assert set(keys) == {"TP53 p.R273H", "RB1 p.A2V"}
    assert keys["TP53 p.R273H"]["variation_id"] == "2"        # most SCVs wins
    assert keys["TP53 p.R273H"]["n_nucleotide_variants"] == 2
    assert funnel["dropped_keys_conflicting_labels"] == 1
    assert funnel["dropped_aggregate_conflicting"] == 1
    assert funnel["horak70_overlap_keys"] == 1


def test_auroc_and_detection_metrics():
    assert auroc([1, 1, 0, 0], [3, 2, 1, 0]) == 1.0
    assert auroc([1, 0], [1, 1]) == 0.5
    assert auroc([1, 1], [1, 2]) is None
    ci = auroc_ci([1, 1, 1, 0, 0, 0], [9, 7, 2, 3, 1, 0], n_boot=200)
    assert ci["lo"] <= ci["point"] <= ci["hi"]
    recs = [{"gold": "ONC", "points": 10, "pred": "Oncogenic"},
            {"gold": "ONC", "points": 2, "pred": "VUS"},
            {"gold": "VUS", "points": 0, "pred": "VUS"},
            {"gold": "VUS", "points": 7, "pred": "Likely Oncogenic"},
            {"gold": "BEN", "points": -8, "pred": "Benign"}]
    d = detection_metrics(recs)
    assert (d["n"], d["tp"], d["fn"], d["tn"], d["fp"]) == (4, 1, 1, 1, 1)
    assert d["sensitivity"]["point"] == 0.5 and d["specificity_on_gold_vus"]["point"] == 0.5


def test_rule_arm_never_fires_clinvar_os1():
    arm = RuleArm()
    res = arm.score({"gene": "TP53", "aa": "p.R273H", "am_pathogenicity": "0.99",
                     "gnomad_af": "0.0"})
    assert "OS1" not in [c.code for c in res.criteria]


@pytest.mark.skipif(not os.path.exists(OUT), reason="holdout report not generated")
def test_committed_report_is_consistent():
    rep = json.load(open(OUT))
    assert rep["rule_arm_config"]["OS1_known_oncogenic"] is False
    for scope in ("panel9", "all"):
        d = rep["scopes"][scope]["detection"]
        assert d["tp"] + d["fn"] == d["n_onc"] and d["tn"] + d["fp"] == d["n_vus"]
        assert d["n_onc"] + d["n_vus"] == d["n"]
        for m in (d["sensitivity"], d["specificity_on_gold_vus"], d["auroc_points"]):
            assert m["lo"] <= m["point"] <= m["hi"]
    assert rep["scopes"]["panel9"]["detection"]["n"] <= rep["scopes"]["all"]["detection"]["n"]
