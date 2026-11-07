"""Full(er) ClinGen/CGC/VICC point-based oncogenicity engine — citable by design.

The original `rules.py` is a deliberately simplified CIViC+AlphaMissense heuristic.
This module implements the point-based VICC combining rules (Horak et al. 2022) over
INDEPENDENT data sources — cancerhotspots.org (OS3/OM3/OP3), a curated tumour-suppressor
list (OVS1), UniProt domains (OM1), AlphaMissense (OP1/SBP1), gnomAD (SBVS1/SBS1/OP4),
MaveDB deep mutational scanning and CIViC *functional* evidence (OS2 vs SBS2) — and emits
EVERY fired criterion as a citable record (code + points + statement + source), so the
call is fully auditable. The Horak gold SOP codes/points are never read, so the engine is
not fit to the benchmark.

CIViC -> VICC code mapping (corrected 2026-09-24; see ``civic_signal_from_rows``).
Horak 2022 Table 2 defines OS2 as "Well-established in vitro or in vivo functional studies
supportive of an oncogenic effect of the variant" and SBS2 as "Well-established in vitro or
in vivo functional studies show no oncogenic effects". Only CIViC evidence that IS a
functional study is therefore mapped to OS2/SBS2:
  * evidence_type ``Functional`` with direction Supports and significance Gain of Function /
    Loss of Function / Dominant Negative / Neomorphic -> oncogenic functional line;
    Supports + Unaltered Function -> benign functional line;
  * evidence_type ``Oncogenic`` only at CIViC level D ("Preclinical evidence ... in vivo or
    in vitro models"); Supports Oncogenicity -> oncogenic line, Does Not Support
    Oncogenicity -> benign line. Oncogenic items at levels A/B/C/E describe observations in
    patients (recurrence, case reports), which the SOP scores via hotspot codes, not OS2;
  * Predictive (Sensitivity/Response, Resistance, Adverse Response ...), Prognostic,
    Diagnostic and Predisposing (germline) evidence is NOT oncogenicity evidence under the
    SOP ("This SOP is not intended for determining the diagnostic, prognostic or therapeutic
    value of variants") and grants no code.
Strength: CIViC evidence levels A-E grade *clinical* study design, not the robustness of a
functional assay (every CIViC Functional item in the snapshot is level D), so level is not
used as a strength proxy. Instead the SOP note "Functional studies that have been shown to
be reproducible and robust are considered the most well established" and its explicit
permission to downgrade OS2/SBS2 are operationalised as: >= 2 independent citations
(distinct PubMed/ASCO ids) -> full strength (OS2 +4 / SBS2 -4); a single citation ->
downgraded to moderate (OS2_Moderate +2 / SBS2_Moderate -2). Concordant-direction lines
only: if oncogenic and benign functional citations tie, neither fires.

OM4 follows the SOP definition ("Missense variant at an amino acid residue where a different
missense variant determined to be oncogenic (using this standard) has been documented",
Grantham-distance condition, excluded if OS1/OS3/OM1 apply). It needs a registry of
SOP-determined oncogenic variants, which no open non-circular source provides here, so it
is an opt-in input (``residue_oncogenic_alts``) that the evaluation scripts do not supply.
(Before 2026-09-24 an unrelated "weaker CIViC evidence" concept was mislabelled OM4.)

Configurations (``CONFIGS``; added 2026-09-24):
  * ``sop_strict`` (PRIMARY) — Table 2/3 implemented to the letter where open data allow:
    OS3/OM3/OP3 on residue total AND same-change count; exclusion rules (OM1 not with
    OS1/OS3, OM3 not with OM1/OM4, OS3 and OS2 not with OS1, OM2 not with OVS1, OM4 not
    with OS1/OS3/OM1); OP4 only when gnomAD data are observed (no approximation, not gated
    on other evidence); OM1 only at UniProt residue-level active/binding sites; SOP null
    definition (stop-loss is OM2, initiation codon is null) and OM2; no non-SOP guards.
  * ``os2_fixed`` — the original engine with only the CIViC->OS2 mapping fixed.
  * ``original`` — the engine as published before 2026-09-24 (reproduced exactly).
  * ``sop_strict_v2`` family (pre-registered 2026-09-24, candidate; notes/audits/2026-09-24/
    개선라운드_사전명시_20260924.md): OP1/SBP1 only when ALL utilised predictor lines
    (AlphaMissense, REVEL, CADD) agree at ClinGen-calibrated supporting thresholds;
    SBVS1/SBS1 on the maximum of the 5 SOP continental gnomAD populations (strict >);
    wider functional inputs (CIViC release, MaveDB TSG sets; read by the consumers via
    ``src.classify.vicc_inputs``); plus sensitivity configurations and per-change ablations.
Codes not evaluable from open data (left unassigned in sop_strict): OS1 (no non-circular
registry of SOP-classified variants), OM4 (same), OP2 (needs tumour type), SBP2 (needs a
splice predictor and conservation); OS2 is limited to CIViC Functional/Oncogenic-D items
and MaveDB DMS (TP53, PTEN).

Point thresholds (Horak 2022 Figure 1): Oncogenic >=10, Likely Oncogenic 6-9, VUS 0-5,
Likely Benign -1..-6, Benign <=-7.
"""
import json
import os
import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.models.standards import VICCOncogenicity

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_HOTSPOTS_PATH = os.path.join(ROOT, "data", "knowledge", "hotspots", "cancerhotspots.json")

# Well-established tumour-suppressor genes (Cancer Gene Census, loss-of-function mechanism).
# Used only for OVS1 (null variant -> very strong oncogenic). Standard knowledge, not
# tuned to any benchmark.
TUMOUR_SUPPRESSORS = {
    "TP53", "PTEN", "RB1", "APC", "NF1", "NF2", "BRCA1", "BRCA2", "CDKN2A", "VHL",
    "STK11", "SMAD4", "ATM", "CDH1", "FBXW7", "KEAP1", "ARID1A", "BAP1", "MLH1",
    "MSH2", "MSH6", "PMS2", "PALB2", "CHEK2", "WT1", "NOTCH1", "FAT1",
}

# Well-established oncogenes (Cancer Gene Census oncogene role). Used only for SOP OM2
# (in-frame length change in a known oncogene or TSG). Standard knowledge, not tuned.
ONCOGENES = {
    "KRAS", "NRAS", "HRAS", "BRAF", "RAF1", "MAP2K1", "PIK3CA", "AKT1", "MTOR", "EGFR",
    "ERBB2", "ERBB3", "MET", "ALK", "ROS1", "RET", "FGFR1", "FGFR2", "FGFR3", "KIT",
    "PDGFRA", "FLT3", "JAK2", "MPL", "IDH1", "IDH2", "EZH2", "ESR1", "CTNNB1", "GNAS",
    "GNAQ", "GNA11", "SF3B1", "U2AF1", "MYC", "MYCN", "CCND1", "CDK4", "SMO", "NFE2L2",
}

# Legacy null pattern (original engine): counts stop-loss ("ext") as null.
_NULL = re.compile(r"(\*|Ter|fs|ext|splice)", re.I)
# SOP OVS1 null: nonsense, frameshift, canonical splice, initiation codon. Stop-loss is
# NOT null under the SOP (it is OM2 in a TSG).
_NULL_SOP = re.compile(r"(\*$|Ter$|\*\d*$|fs|splice|^p?\.?(M|Met)1[^0-9])", re.I)
_STOPLOSS = re.compile(r"(\*|Ter)\d+.*ext", re.I)
_INFRAME = re.compile(r"(del|ins|dup)", re.I)
_AA = re.compile(r"([A-Za-z])(\d+)(.*)")


@dataclass(frozen=True)
class VICCConfig:
    """A named engine configuration.

    ``sop_strict`` is the primary result (Horak 2022 SOP implemented to the letter wherever
    open data allow). ``os2_fixed`` and ``original`` are kept as sensitivity analyses: the
    engine after the 2026-09-24 CIViC-mapping fix, and the engine as published before it."""
    name: str
    civic_mapping: str          # "functional" (SOP) | "legacy" (any Supports item)
    hotspot_rule: str           # "sop" (residue total + same-change count) | "alt_count"
    sop_exclusions: bool        # OM1/OM3/OS3/OS2/OM2 exclusion rules of Table 2
    op4: str                    # "data_only" | "gated_approx" (legacy)
    lone_benign_guard: bool     # legacy: a single benign line -> VUS instead of LB
    om1_scope: str              # "site" (UniProt active/binding site) | "domain" (legacy)
    sop_null: bool              # SOP null definition (no stop-loss) + OM2
    description: str = ""
    # --- sop_strict_v2 family (added 2026-09-24, pre-registered; defaults = legacy behaviour)
    # OP1/SBP1 computational lines: predictor names (keys of PREDICTOR_THRESHOLDS[...]).
    comp_predictors: Tuple[str, ...] = ("alphamissense",)
    # threshold table: "am_developer" (legacy AM 0.564/0.34) | "clingen" | "developer"
    comp_thresholds: str = "am_developer"
    # SBVS1/SBS1 frequency: "overall" (max gnomADe/g overall AF, >=) | "continental_max"
    # (max over the 5 SOP continental populations, strict >, per the SOP text)
    pop_af_mode: str = "overall"
    # Input versions read by the consumers (not by the engine): "v1" existing snapshots,
    # "v2" + CIViC monthly release (civic) / + pre-registered MaveDB sets (dms).
    civic_inputs: str = "v1"
    dms_inputs: str = "v1"


@dataclass(frozen=True)
class PredictorThreshold:
    """Supporting-level cut points of one computational predictor.

    ``higher_is_onco``: larger scores mean damaging (False for SIFT). A score supports an
    oncogenic effect if it is at or beyond ``onco``; it suggests no impact if at or beyond
    ``benign`` on the other side (strictly beyond when ``benign_strict``, for developer
    single-cut rules such as REVEL < 0.5). Between the two it is indeterminate."""
    onco: float
    benign: float
    higher_is_onco: bool = True
    benign_strict: bool = False

    def direction(self, x: float) -> Optional[str]:
        if self.higher_is_onco:
            if x >= self.onco:
                return "onco"
            if (x < self.benign) if self.benign_strict else (x <= self.benign):
                return "benign"
        else:
            if x <= self.onco:
                return "onco"
            if (x > self.benign) if self.benign_strict else (x >= self.benign):
                return "benign"
        return None


# Pre-registered thresholds (notes/audits/2026-09-24/개선라운드_사전명시_20260924.md, sec. 2.1/3).
#  clingen: supporting boundaries of the ClinGen calibrations — AlphaMissense Bergquist et al.
#    Genet Med 2025 Table 1 (PP3 >=0.792, BP4 <=0.169); REVEL, CADD, SIFT, PolyPhen-2 Pejaver
#    et al. AJHG 2022 Table 2 (REVEL >=0.644 / <=0.290; CADD >=25.3 / <=22.7; SIFT <=0.001 /
#    >=0.080; PolyPhen-2 >=0.978 / <=0.113).
#  developer: tool-developer defaults (AlphaMissense 0.564/0.34, Cheng 2023; REVEL 0.5,
#    Ioannidis 2016; CADD 20, Pejaver 2022 Table 3 developer default).
PREDICTOR_THRESHOLDS: Dict[str, Dict[str, PredictorThreshold]] = {
    "am_developer": {"alphamissense": PredictorThreshold(0.564, 0.34)},
    "clingen": {
        "alphamissense": PredictorThreshold(0.792, 0.169),
        "revel": PredictorThreshold(0.644, 0.290),
        "cadd_phred": PredictorThreshold(25.3, 22.7),
        "sift": PredictorThreshold(0.001, 0.080, higher_is_onco=False),
        "polyphen": PredictorThreshold(0.978, 0.113),
    },
    "developer": {
        "alphamissense": PredictorThreshold(0.564, 0.34),
        "revel": PredictorThreshold(0.5, 0.5, benign_strict=True),
        "cadd_phred": PredictorThreshold(20.0, 20.0, benign_strict=True),
    },
}
_PRED_LABEL = {"alphamissense": "AlphaMissense", "revel": "REVEL", "cadd_phred": "CADD",
               "sift": "SIFT", "polyphen": "PolyPhen-2"}
CONTINENTAL_SBVS1, CONTINENTAL_SBS1 = 0.05, 0.01


CONFIGS: Dict[str, VICCConfig] = {
    "sop_strict": VICCConfig(
        "sop_strict", civic_mapping="functional", hotspot_rule="sop", sop_exclusions=True,
        op4="data_only", lone_benign_guard=False, om1_scope="site", sop_null=True,
        description="SOP-strict (primary): Horak 2022 Tables 2-3 incl. exclusion rules; OP4 "
                    "only from observed gnomAD data; OM1 only at UniProt active/binding sites; "
                    "CIViC functional evidence only; no non-SOP guards."),
    "os2_fixed": VICCConfig(
        "os2_fixed", civic_mapping="functional", hotspot_rule="alt_count", sop_exclusions=False,
        op4="gated_approx", lone_benign_guard=True, om1_scope="domain", sop_null=False,
        description="Sensitivity analysis: original engine with only the CIViC->OS2 mapping "
                    "fixed (functional evidence only; OM4 per SOP, unassigned)."),
    "original": VICCConfig(
        "original", civic_mapping="legacy", hotspot_rule="alt_count", sop_exclusions=False,
        op4="gated_approx", lone_benign_guard=True, om1_scope="domain", sop_null=False,
        description="Sensitivity analysis: engine as published before 2026-09-24 (any "
                    "direction-supporting CIViC item -> OS2 if level A/B else legacy 'OM4')."),
}

_V2_PRED = ("alphamissense", "revel", "cadd_phred")
_V2 = dict(comp_predictors=_V2_PRED, comp_thresholds="clingen", pop_af_mode="continental_max",
           civic_inputs="v2", dms_inputs="v2")


def _derive(base: str, name: str, description: str, **overrides: Any) -> VICCConfig:
    return replace(CONFIGS[base], name=name, description=description, **overrides)


# sop_strict_v2 family (pre-registered 2026-09-24; candidate primary + sensitivity configs +
# per-change ablations). The existing three configurations are unchanged.
CONFIGS["sop_strict_v2"] = _derive(
    "sop_strict", "sop_strict_v2",
    "SOP-strict v2 (candidate primary, pre-registered): sop_strict + OP1/SBP1 only when all "
    "utilised lines agree (AlphaMissense, REVEL, CADD at ClinGen supporting thresholds) + "
    "SBVS1/SBS1 on the maximum of the 5 SOP continental gnomAD populations + CIViC monthly "
    "release and pre-registered MaveDB DMS sets.", **_V2)
CONFIGS["sop_strict_v2_5pred"] = _derive(
    "sop_strict_v2", "sop_strict_v2_5pred",
    "Sensitivity S-a1: v2 with SIFT and PolyPhen-2 added to the all-agree predictor set "
    "(Pejaver 2022 thresholds).",
    comp_predictors=_V2_PRED + ("sift", "polyphen"))
CONFIGS["sop_strict_v2_revel"] = _derive(
    "sop_strict_v2", "sop_strict_v2_revel",
    "Sensitivity S-a2: v2 with OP1/SBP1 from REVEL alone (Pejaver 2022 single calibrated "
    "tool recommendation).", comp_predictors=("revel",))
CONFIGS["sop_strict_v2_devcut"] = _derive(
    "sop_strict_v2", "sop_strict_v2_devcut",
    "Sensitivity S-a3: v2 with developer cut-offs (AlphaMissense 0.564/0.34, REVEL 0.5, "
    "CADD 20).", comp_thresholds="developer")
CONFIGS["sop_strict_v2_om1domain"] = _derive(
    "sop_strict_v2", "sop_strict_v2_om1domain",
    "Sensitivity S-d: v2 with the broader domain-level OM1 reading (exclusions kept).",
    om1_scope="domain")
# Per-change ablations (add-one from sop_strict, leave-one-out from sop_strict_v2).
CONFIGS["abl_strict_plus_a"] = _derive(
    "sop_strict", "abl_strict_plus_a", "Ablation: sop_strict + change a (predictors).",
    comp_predictors=_V2_PRED, comp_thresholds="clingen")
CONFIGS["abl_strict_plus_a0"] = _derive(
    "sop_strict", "abl_strict_plus_a0",
    "Ablation: sop_strict + AlphaMissense at ClinGen thresholds only (single line).",
    comp_predictors=("alphamissense",), comp_thresholds="clingen")
CONFIGS["abl_strict_plus_b"] = _derive(
    "sop_strict", "abl_strict_plus_b", "Ablation: sop_strict + change b (continental max AF).",
    pop_af_mode="continental_max")
CONFIGS["abl_strict_plus_c1"] = _derive(
    "sop_strict", "abl_strict_plus_c1", "Ablation: sop_strict + change c1 (CIViC release).",
    civic_inputs="v2")
CONFIGS["abl_strict_plus_c2"] = _derive(
    "sop_strict", "abl_strict_plus_c2", "Ablation: sop_strict + change c2 (MaveDB additions).",
    dms_inputs="v2")
CONFIGS["abl_v2_minus_a"] = _derive(
    "sop_strict_v2", "abl_v2_minus_a", "Ablation: sop_strict_v2 without change a.",
    comp_predictors=("alphamissense",), comp_thresholds="am_developer")
CONFIGS["abl_v2_minus_b"] = _derive(
    "sop_strict_v2", "abl_v2_minus_b", "Ablation: sop_strict_v2 without change b.",
    pop_af_mode="overall")
CONFIGS["abl_v2_minus_c1"] = _derive(
    "sop_strict_v2", "abl_v2_minus_c1", "Ablation: sop_strict_v2 without change c1.",
    civic_inputs="v1")
CONFIGS["abl_v2_minus_c2"] = _derive(
    "sop_strict_v2", "abl_v2_minus_c2", "Ablation: sop_strict_v2 without change c2.",
    dms_inputs="v1")
V2_FAMILY = tuple(k for k in CONFIGS if k.startswith(("sop_strict_v2", "abl_")))
PRIMARY_CONFIG = "sop_strict"

# UniProt feature selection for OM1.
_REGION_KEYS = ("dna", "bind", "pocket", "kinase", "catalyt", "phosphatase", "set", "tensin")


def domain_feature_at(domains: Mapping[str, Any], gene: str, pos: int,
                      scope: str = "site") -> Optional[str]:
    """UniProt feature supporting OM1 at ``gene`` residue ``pos``.

    scope="site": only residue-level Active site / Binding site features (the SOP's
    "critical and well-established part of a functional domain (e.g., active site of an
    enzyme)"). scope="domain": the legacy reading (any Domain, Active/Binding site, or a
    functional Region), which credits whole domains."""
    for s_, e_, t, desc in domains.get(gene, []):
        if not (s_ <= pos <= e_):
            continue
        if scope == "site":
            if t in ("Active site", "Binding site"):
                return f"{t}{': ' + desc if desc else ''} ({s_}-{e_})"
        else:
            if t in ("Domain", "Active site", "Binding site"):
                return desc or t
            if t == "Region" and any(k in (desc or "").lower() for k in _REGION_KEYS):
                return desc
    return None

# Point value per VICC strength.
_PTS = {"OVS1": 8, "OS1": 4, "OS2": 4, "OS3": 4, "OM1": 2, "OM3": 2, "OM4": 2,
        "OS2_Moderate": 2, "OM2": 2,
        "OP1": 1, "OP3": 1, "OP4": 1, "SBS2": -4, "SBS2_Moderate": -2, "SBP1": -1,
        "SBVS1": -8, "SBS1": -4}

# Codes that count as oncogenic support (used for the OP4 approximation gate).
ONCOGENIC_CODES = frozenset({"OVS1", "OS1", "OS2", "OS2_Moderate", "OS3", "OM1", "OM2",
                             "OM3", "OM4", "OP1", "OP3", "OP4"})
# OP4 "extremely low frequency": the SOP gives no number; engine threshold (unchanged).
OP4_MAX_AF = 1e-4
# Codes at full "strong" (or very strong) strength.
STRONG_CODES = frozenset({"OVS1", "OS1", "OS2", "OS3"})

# ---- CIViC evidence -> functional line (see module docstring) --------------------------
FUNCTIONAL_ONCO_SIG = frozenset({"gain of function", "loss of function",
                                 "dominant negative", "neomorphic"})
FUNCTIONAL_BENIGN_SIG = frozenset({"unaltered function"})
# CIViC level D = "Preclinical evidence ... in vivo or in vitro models" (docs.civicdb.org).
_PRECLINICAL_LEVEL = "D"
# Independent citations needed for full OS2/SBS2 strength (SOP: "reproducible and robust").
REPLICATION_MIN_CITATIONS = 2

# Grantham (1974) amino-acid distance, Science 185:862, used only by the SOP OM4 condition.
# 190 unordered pairs; checked against the SOP example (R->H 29, R->C 180), L-I 5, C-W 215.
_GRANTHAM = {
    "AC": 195, "AD": 126, "AE": 107, "AF": 113, "AG": 60, "AH": 86, "AI": 94, "AK": 106,
    "AL": 96, "AM": 84, "AN": 111, "AP": 27, "AQ": 91, "AR": 112, "AS": 99, "AT": 58,
    "AV": 64, "AW": 148, "AY": 112, "CD": 154, "CE": 170, "CF": 205, "CG": 159, "CH": 174,
    "CI": 198, "CK": 202, "CL": 198, "CM": 196, "CN": 139, "CP": 169, "CQ": 154, "CR": 180,
    "CS": 112, "CT": 149, "CV": 192, "CW": 215, "CY": 194, "DE": 45, "DF": 177, "DG": 94,
    "DH": 81, "DI": 168, "DK": 101, "DL": 172, "DM": 160, "DN": 23, "DP": 108, "DQ": 61,
    "DR": 96, "DS": 65, "DT": 85, "DV": 152, "DW": 181, "DY": 160, "EF": 140, "EG": 98,
    "EH": 40, "EI": 134, "EK": 56, "EL": 138, "EM": 126, "EN": 42, "EP": 93, "EQ": 29,
    "ER": 54, "ES": 80, "ET": 65, "EV": 121, "EW": 152, "EY": 122, "FG": 153, "FH": 100,
    "FI": 21, "FK": 102, "FL": 22, "FM": 28, "FN": 158, "FP": 114, "FQ": 116, "FR": 97,
    "FS": 155, "FT": 103, "FV": 50, "FW": 40, "FY": 22, "GH": 98, "GI": 135, "GK": 127,
    "GL": 138, "GM": 127, "GN": 80, "GP": 42, "GQ": 87, "GR": 125, "GS": 56, "GT": 59,
    "GV": 109, "GW": 184, "GY": 147, "HI": 94, "HK": 32, "HL": 99, "HM": 87, "HN": 68,
    "HP": 77, "HQ": 24, "HR": 29, "HS": 89, "HT": 47, "HV": 84, "HW": 115, "HY": 83,
    "IK": 102, "IL": 5, "IM": 10, "IN": 149, "IP": 95, "IQ": 109, "IR": 97, "IS": 142,
    "IT": 89, "IV": 29, "IW": 61, "IY": 33, "KL": 107, "KM": 95, "KN": 94, "KP": 103,
    "KQ": 53, "KR": 26, "KS": 121, "KT": 78, "KV": 97, "KW": 110, "KY": 85, "LM": 15,
    "LN": 153, "LP": 98, "LQ": 113, "LR": 102, "LS": 145, "LT": 92, "LV": 32, "LW": 61,
    "LY": 36, "MN": 142, "MP": 87, "MQ": 101, "MR": 91, "MS": 135, "MT": 81, "MV": 21,
    "MW": 67, "MY": 36, "NP": 91, "NQ": 46, "NR": 86, "NS": 46, "NT": 65, "NV": 133,
    "NW": 174, "NY": 143, "PQ": 76, "PR": 103, "PS": 74, "PT": 38, "PV": 68, "PW": 147,
    "PY": 110, "QR": 43, "QS": 68, "QT": 42, "QV": 96, "QW": 130, "QY": 99, "RS": 110,
    "RT": 71, "RV": 96, "RW": 101, "RY": 77, "ST": 58, "SV": 124, "SW": 177, "SY": 144,
    "TV": 69, "TW": 128, "TY": 92, "VW": 88, "VY": 55, "WY": 37,
}
# The SOP asks that the new change be "greater or at least approximately the same" distance
# as the documented oncogenic one but gives no number; 0.9 is our stated reading.
OM4_GRANTHAM_TOLERANCE = 0.9


def grantham(a: str, b: str) -> Optional[int]:
    """Grantham distance between two one-letter amino acids (0 if identical)."""
    a, b = (a or "").upper(), (b or "").upper()
    if a == b and len(a) == 1:
        return 0
    return _GRANTHAM.get("".join(sorted(a + b)))


@dataclass
class CivicSignal:
    """CIViC evidence for one exact variant, reduced to SOP functional lines.

    ``onco_eids``/``benign_eids`` are the CIViC evidence ids that are functional studies in
    the oncogenic / benign direction; ``*_citations`` count distinct source citations among
    them (the replication criterion). ``ignored`` counts matched items that grant no code,
    keyed by "<evidence_type>|<significance>" so the exclusion is auditable."""
    onco_eids: List[str] = field(default_factory=list)
    benign_eids: List[str] = field(default_factory=list)
    onco_citations: int = 0
    benign_citations: int = 0
    ignored: Dict[str, int] = field(default_factory=dict)
    # Legacy (original engine) reduction, filled when mapping="legacy".
    legacy_onco: int = 0
    legacy_benign: int = 0
    legacy_best_level: Optional[str] = None

    @property
    def n_matched(self) -> int:
        return len(self.onco_eids) + len(self.benign_eids) + sum(self.ignored.values())


def _civic_functional_direction(row: Mapping[str, Any]) -> Optional[str]:
    """Return "onco", "benign" or None for one CIViC evidence row (SOP mapping)."""
    et = str(row.get("evidence_type", "") or "").strip().lower()
    d = str(row.get("evidence_direction", "") or "").strip().lower()
    s = str(row.get("significance", "") or "").strip().lower()
    lv = str(row.get("evidence_level", "") or "").strip().upper()
    if et == "functional":
        if d == "supports" and s in FUNCTIONAL_ONCO_SIG:
            return "onco"
        if d == "supports" and s in FUNCTIONAL_BENIGN_SIG:
            return "benign"
        return None          # e.g. "Does Not Support Dominant Negative": not a clean line
    if et == "oncogenic" and lv == _PRECLINICAL_LEVEL and s == "oncogenicity":
        if d == "supports":
            return "onco"
        if d == "does not support":
            return "benign"
    return None


def exact_profile_match(molecular_profile: str, gene: str, ref: str, pos: int,
                        alt: str) -> bool:
    """True if a CIViC molecular profile names THIS exact substitution (optionally
    followed by a separator, e.g. "GENE V600E AND ..."), never a neighbour at the residue."""
    exact = f"{gene} {ref}{pos}{alt}"
    mp = str(molecular_profile)
    return mp.startswith(exact) and (len(mp) == len(exact) or not mp[len(exact)].isalnum())


_LEGACY_BEN_SIG = {"unaltered function", "benign", "likely benign", "negative"}
_LEGACY_RANK = {"A": 3, "B": 2, "C": 1, "D": 0}


def civic_signal_from_rows(rows: Iterable[Mapping[str, Any]], gene: str, ref: str,
                           pos: int, alt: str) -> CivicSignal:
    """Reduce CIViC evidence rows (CIViC export columns) to SOP functional lines for the
    exact variant ``gene ref pos alt``. Shared by every VICC-engine consumer. The legacy
    reduction (``legacy_*`` fields) is filled alongside so the ``original`` configuration
    can be reproduced from the same call."""
    sig = CivicSignal()
    onco_cit, ben_cit = set(), set()
    for r in rows:
        if not exact_profile_match(r.get("molecular_profile", ""), gene, ref, pos, alt):
            continue
        # legacy: any Supports item is oncogenic unless its significance is benign-ish
        s_l = str(r.get("significance", "")).lower()
        d_l = str(r.get("evidence_direction", "")).lower()
        if s_l in _LEGACY_BEN_SIG:
            sig.legacy_benign += 1
        elif d_l == "supports":
            sig.legacy_onco += 1
            lv = str(r.get("evidence_level", ""))
            if (sig.legacy_best_level is None
                    or _LEGACY_RANK.get(lv, -1) > _LEGACY_RANK.get(sig.legacy_best_level, -1)):
                sig.legacy_best_level = lv
        eid = str(r.get("evidence_id", "") or "")
        cit = str(r.get("citation_id", "") or "") or f"EID{eid}"
        direction = _civic_functional_direction(r)
        if direction == "onco":
            sig.onco_eids.append(eid)
            onco_cit.add(cit)
        elif direction == "benign":
            sig.benign_eids.append(eid)
            ben_cit.add(cit)
        else:
            key = f"{r.get('evidence_type', '')}|{r.get('significance', '')}"
            sig.ignored[key] = sig.ignored.get(key, 0) + 1
    sig.onco_citations, sig.benign_citations = len(onco_cit), len(ben_cit)
    return sig


@dataclass
class Criterion:
    """One fired VICC criterion, rendered as citable evidence."""
    code: str
    points: int
    statement: str
    source: str

    @property
    def id(self) -> str:
        return f"VICC:{self.code}"


@dataclass
class VICCResult:
    oncogenicity: VICCOncogenicity
    points: int
    criteria: List[Criterion] = field(default_factory=list)

    def citation_ids(self) -> List[str]:
        return [c.id for c in self.criteria]


def _load_hotspots() -> Dict:
    if os.path.exists(_HOTSPOTS_PATH):
        return json.load(open(_HOTSPOTS_PATH))
    return {}


def parse_protein_change(aa: str):
    """'p.V600E' -> ('V', 600, 'E'); returns None if unparseable."""
    m = _AA.match((aa or "").replace("p.", ""))
    return (m.group(1), int(m.group(2)), m.group(3)) if m else None


def classify_points(points: int) -> VICCOncogenicity:
    if points >= 10:
        return VICCOncogenicity.ONCOGENIC
    if points >= 6:
        return VICCOncogenicity.LIKELY_ONCOGENIC
    if points >= 0:
        return VICCOncogenicity.VUS
    if points >= -6:
        return VICCOncogenicity.LIKELY_BENIGN
    return VICCOncogenicity.BENIGN


class VICCPointClassifier:
    """Point-based VICC oncogenicity from independent evidence sources.

    Inputs are pre-extracted signals so the same engine serves both the offline
    Horak evaluation (signals from the benchmark TSVs) and the live pipeline
    (signals from an EvidenceBundle). ``config`` selects a named configuration from
    :data:`CONFIGS` (default: the SOP-strict primary)."""

    def __init__(self, hotspots: Optional[Dict] = None, residue_hotspot: bool = False,
                 config: str = PRIMARY_CONFIG):
        self.hotspots = hotspots if hotspots is not None else _load_hotspots()
        # Optional sensitivity lever (dial mode 2): tier OS3/OM3/OP3 on the TOTAL recurrence
        # at the residue only, dropping the SOP's "same amino acid change count >= 10"
        # condition. Not SOP-conformant; off by default.
        self.residue_hotspot = residue_hotspot
        if config not in CONFIGS:
            raise ValueError(f"unknown VICC config {config!r}; choose from {sorted(CONFIGS)}")
        self.config = CONFIGS[config]

    # -- hotspot tier -------------------------------------------------------------------
    def _hotspot(self, gene: str, ref: str, pos: int, alt: str) -> Optional[Criterion]:
        res = self.hotspots.get(gene, {}).get(str(pos)) or self.hotspots.get(gene, {}).get(pos)
        if not res:
            return None
        alt_n, tot = res.get(alt, 0), sum(res.values())
        if self.residue_hotspot:
            code = "OS3" if tot >= 50 else ("OM3" if tot >= 10 else "OP3")
        elif self.config.hotspot_rule == "sop":
            # Table 2: OS3 = >=50 samples at the position AND same change >=10;
            # OM3 = <50 at the position AND same change >=10; OP3 = same change <10.
            code = "OS3" if (alt_n >= 10 and tot >= 50) else ("OM3" if alt_n >= 10 else "OP3")
        else:  # legacy: both tiers on the same-change count
            code = "OS3" if alt_n >= 50 else ("OM3" if alt_n >= 10 else "OP3")
        c = tot if self.residue_hotspot else alt_n
        if code == "OP3":
            text = (f"{gene} residue {ref}{pos} is a cancerhotspots.org hotspot "
                    f"({ref}{pos}{alt} count {alt_n}).")
        else:
            text = (f"{gene} {ref}{pos}{alt} occurs in {c} samples at a cancerhotspots.org "
                    f"hotspot residue ({tot} samples at the position).")
        return Criterion(code, _PTS[code], text, "cancerhotspots")

    def score(self, gene: str, aa: str, *,
              am_pathogenicity: Optional[float] = None,
              civic: Optional[CivicSignal] = None,
              in_domain: Optional[str] = None,
              functional_lof: bool = False,
              functional_neutral: bool = False,
              gnomad_af: Optional[float] = None,
              known_oncogenic: bool = False,
              residue_oncogenic_alts: Optional[Sequence[str]] = None,
              predictors: Optional[Mapping[str, Optional[float]]] = None,
              pop_af_max5: Optional[float] = None) -> VICCResult:
        """Score one variant.

        ``civic`` is the output of :func:`civic_signal_from_rows`. ``in_domain`` is the
        UniProt feature from :func:`domain_feature_at` (scope per ``config.om1_scope``).
        ``gnomad_af`` None means no population data (SOP-strict then awards no OP4); 0.0
        means absent from gnomAD. ``residue_oncogenic_alts`` (opt-in, SOP OM4) lists other
        amino acids at the same residue already determined oncogenic under this standard;
        not supplied by the evaluation scripts because no open, non-circular registry
        exists.

        v2 family only: ``predictors`` maps predictor names (``revel``, ``cadd_phred``,
        ``sift``, ``polyphen``; ``alphamissense`` defaults to ``am_pathogenicity``) to scores
        (None = not available, i.e. not a utilised line); ``pop_af_max5`` is the maximum
        allele frequency over the 5 SOP continental gnomAD populations (None = no data)."""
        cfg = self.config
        crit: List[Criterion] = []
        pp = parse_protein_change(aa)
        a = aa or ""
        if cfg.sop_null:
            is_null = bool(_NULL_SOP.search(a)) and not _STOPLOSS.search(a)
        else:
            is_null = bool(_NULL.search(a))

        # OS1 — same amino-acid change as a previously established oncogenic variant.
        # OPTIONAL, disclosed-circularity signal (ClinVar oncogenicity; dial modes 3/4).
        if known_oncogenic:
            crit.append(Criterion("OS1", _PTS["OS1"],
                                  f"{gene} {aa} is an established oncogenic variant in a "
                                  f"curated knowledge base.", "OncoKB/ClinVar"))

        if is_null and gene in TUMOUR_SUPPRESSORS:
            # OVS1 — null variant in a bona fide tumour suppressor.
            crit.append(Criterion("OVS1", _PTS["OVS1"],
                                  f"{gene} {aa} is a null (LoF) variant in a tumour-suppressor gene.",
                                  "VICC/CGC"))
        elif cfg.sop_null and (
                (_STOPLOSS.search(a) and gene in TUMOUR_SUPPRESSORS)
                or (_INFRAME.search(a) and "fs" not in a.lower()
                    and gene in (ONCOGENES | TUMOUR_SUPPRESSORS))):
            # OM2 — protein length change: in-frame indel in a known oncogene / TSG, or
            # stop-loss in a TSG (cannot be used if OVS1 applies; it does not here).
            crit.append(Criterion("OM2", _PTS["OM2"],
                                  f"{gene} {aa} changes protein length (in-frame indel or "
                                  f"stop-loss) in a known cancer gene.", "VICC/CGC"))
        elif pp:
            ref, pos, alt = pp
            # OM1 — critical, well-established part of a functional domain (UniProt).
            if in_domain:
                crit.append(Criterion("OM1", _PTS["OM1"],
                                      f"{gene} {ref}{pos} lies in {in_domain}.", "UniProt"))
            # OS2 / SBS2 — well-established functional study (DMS/MAVE).
            if functional_lof:
                crit.append(Criterion("OS2", _PTS["OS2"],
                                      f"Deep mutational scanning shows {gene} {ref}{pos}{alt} is "
                                      f"loss-of-function / damaging.", "MaveDB/DMS"))
            elif functional_neutral:
                crit.append(Criterion("SBS2", _PTS["SBS2"],
                                      f"Deep mutational scanning shows {gene} {ref}{pos}{alt} is "
                                      f"functionally neutral (no effect).", "MaveDB/DMS"))
            # OM4 (SOP, opt-in) — a different missense change at this residue is oncogenic,
            # with at least ~equal Grantham distance.
            om4 = None
            if residue_oncogenic_alts and len(alt) == 1 and alt.isalpha():
                d_new = grantham(ref, alt)
                for k in residue_oncogenic_alts:
                    d_known = grantham(ref, k)
                    if (k != alt and d_new is not None and d_known
                            and d_new >= OM4_GRANTHAM_TOLERANCE * d_known):
                        om4 = Criterion("OM4", _PTS["OM4"],
                                        f"{gene} {ref}{pos}{k} at the same residue is oncogenic; "
                                        f"{ref}>{alt} Grantham {d_new} >= ~{ref}>{k} {d_known}.",
                                        "VICC/Grantham")
                        break
            hot = self._hotspot(gene, ref, pos, alt)
            if hot is not None:
                crit.append(hot)
            if om4 is not None:
                crit.append(om4)

        # CIViC evidence.
        if civic is not None and cfg.civic_mapping == "legacy":
            # Original engine, reproduced exactly: any direction-supporting item.
            if civic.legacy_onco > 0:
                if (civic.legacy_best_level in ("A", "B")
                        and not any(c.code == "OS2" for c in crit)):
                    crit.append(Criterion("OS2", _PTS["OS2"],
                                          f"{civic.legacy_onco} CIViC evidence item(s) (level "
                                          f"{civic.legacy_best_level}) support an oncogenic role.",
                                          "CIViC"))
                elif not any(c.code in ("OS2", "OM4") for c in crit):
                    crit.append(Criterion("OM4", _PTS["OM4"],
                                          f"{civic.legacy_onco} CIViC evidence item(s) support an "
                                          f"oncogenic role (legacy, not the SOP OM4).", "CIViC"))
            if civic.legacy_benign > civic.legacy_onco:
                crit.append(Criterion("SBS2", _PTS["SBS2"],
                                      f"{civic.legacy_benign} CIViC evidence item(s) refute an "
                                      f"oncogenic role.", "CIViC"))
        elif civic is not None and (civic.onco_citations or civic.benign_citations):
            # SOP: only functional studies. >=2 independent citations full strength; one
            # citation -> SOP-permitted downgrade to moderate. No double count with DMS.
            n_on, n_be = civic.onco_citations, civic.benign_citations
            full = REPLICATION_MIN_CITATIONS
            if n_on > n_be and not any(c.code.startswith("OS2") for c in crit):
                code = "OS2" if n_on >= full else "OS2_Moderate"
                eids = ", ".join(f"EID{e}" for e in civic.onco_eids)
                crit.append(Criterion(code, _PTS[code],
                                      f"CIViC functional evidence ({eids}; {n_on} independent "
                                      f"citation(s)) shows an oncogenic functional effect of "
                                      f"{gene} {aa}.", "CIViC"))
            elif n_be > n_on and not any(c.code.startswith("SBS2") for c in crit):
                code = "SBS2" if n_be >= full else "SBS2_Moderate"
                eids = ", ".join(f"EID{e}" for e in civic.benign_eids)
                crit.append(Criterion(code, _PTS[code],
                                      f"CIViC functional evidence ({eids}; {n_be} independent "
                                      f"citation(s)) shows no oncogenic effect of {gene} {aa} "
                                      f"(e.g. unaltered function).", "CIViC"))

        # OP1/SBP1 — computational evidence.
        if cfg.comp_predictors == ("alphamissense",) and cfg.comp_thresholds == "am_developer":
            # Legacy path (sop_strict/os2_fixed/original): AlphaMissense, the single line.
            if am_pathogenicity is not None:
                if am_pathogenicity >= 0.564:
                    crit.append(Criterion("OP1", _PTS["OP1"],
                                          f"AlphaMissense predicts pathogenic ({am_pathogenicity:.3f}).",
                                          "AlphaMissense"))
                elif am_pathogenicity <= 0.34:
                    crit.append(Criterion("SBP1", _PTS["SBP1"],
                                          f"AlphaMissense predicts benign ({am_pathogenicity:.3f}).",
                                          "AlphaMissense"))
        else:
            comp = self._computational(am_pathogenicity, predictors)
            if comp is not None:
                crit.append(comp)

        # SBVS1 / SBS1 — common in the population (gnomAD).
        if cfg.pop_af_mode == "continental_max":
            # SOP: MAF ">5%" / ">1%" in any of the 5 general continental populations.
            if pop_af_max5 is not None and pop_af_max5 > CONTINENTAL_SBVS1:
                crit.append(Criterion("SBVS1", _PTS["SBVS1"],
                                      f"Allele frequency {pop_af_max5:.3f} (>5%) in a gnomAD "
                                      f"continental population (AFR/AMR/EAS/NFE/SAS max).",
                                      "gnomAD"))
            elif pop_af_max5 is not None and pop_af_max5 > CONTINENTAL_SBS1:
                crit.append(Criterion("SBS1", _PTS["SBS1"],
                                      f"Allele frequency {pop_af_max5:.3f} (>1%) in a gnomAD "
                                      f"continental population (AFR/AMR/EAS/NFE/SAS max).",
                                      "gnomAD"))
        elif gnomad_af is not None and gnomad_af >= 0.05:
            crit.append(Criterion("SBVS1", _PTS["SBVS1"],
                                  f"Population allele frequency {gnomad_af:.3f} (>=5%) in gnomAD.", "gnomAD"))
        elif gnomad_af is not None and gnomad_af >= 0.01:
            crit.append(Criterion("SBS1", _PTS["SBS1"],
                                  f"Population allele frequency {gnomad_af:.3f} (>=1%) in gnomAD.", "gnomAD"))

        # SOP combination / exclusion rules (Table 2 caveats), applied before OP4.
        if cfg.sop_exclusions:
            crit = self._apply_exclusions(crit)

        # OP4 — absent from controls (or at an extremely low frequency) in gnomAD.
        if cfg.op4 == "data_only":
            if gnomad_af is not None and gnomad_af < OP4_MAX_AF:
                crit.append(Criterion("OP4", _PTS["OP4"],
                                      ("Absent from gnomAD." if gnomad_af == 0 else
                                       f"Extremely rare in gnomAD (AF {gnomad_af:.5f})."),
                                      "gnomAD"))
        else:  # legacy: gated on other oncogenic evidence, approximated when AF missing
            has_onco = any(c.code in ONCOGENIC_CODES - {"OVS1", "OP1", "OP4"} for c in crit)
            has_benign_pop = any(c.code in ("SBVS1", "SBS1") for c in crit)
            if has_onco and not any(c.code == "OVS1" for c in crit) and not has_benign_pop:
                if gnomad_af is not None:
                    if gnomad_af < OP4_MAX_AF:
                        crit.append(Criterion("OP4", _PTS["OP4"],
                                              f"Absent / very rare in gnomAD (AF {gnomad_af:.5f}).",
                                              "gnomAD"))
                else:
                    crit.append(Criterion("OP4", _PTS["OP4"],
                                          "Recurrent somatic variant, absent/rare in population "
                                          "databases (approximated; gnomAD not queried).", "approx"))

        points = sum(c.points for c in crit)
        onc = classify_points(points)
        if cfg.lone_benign_guard:
            # Legacy, non-SOP: a single benign line without populational support -> VUS.
            neg = [c for c in crit if c.points < 0]
            has_pop_benign = any(c.code in ("SBVS1", "SBS1") for c in crit)
            if onc == VICCOncogenicity.LIKELY_BENIGN and not has_pop_benign and len(neg) <= 1:
                onc = VICCOncogenicity.VUS
        return VICCResult(onc, points, crit)

    def _computational(self, am_pathogenicity: Optional[float],
                       predictors: Optional[Mapping[str, Optional[float]]]
                       ) -> Optional[Criterion]:
        """SOP OP1/SBP1: "All utilized lines of computational evidence support an oncogenic
        effect" / "suggest no impact". Utilised lines = configured predictors with a score;
        all must fall in the same supporting range, else no code. Counted once (+1/-1)."""
        cfg = self.config
        table = PREDICTOR_THRESHOLDS[cfg.comp_thresholds]
        scores: Dict[str, Optional[float]] = dict(predictors or {})
        scores.setdefault("alphamissense", am_pathogenicity)
        used = [(p, float(scores[p])) for p in cfg.comp_predictors
                if scores.get(p) is not None]
        if not used:
            return None
        dirs = {table[p].direction(x) for p, x in used}
        if len(dirs) != 1 or None in dirs:
            return None
        d = dirs.pop()
        lines = ", ".join(f"{_PRED_LABEL.get(p, p)} {x:.3f}" for p, x in used)
        src = "+".join(_PRED_LABEL.get(p, p) for p, _ in used)
        if d == "onco":
            return Criterion("OP1", _PTS["OP1"],
                             f"All {len(used)} utilised computational line(s) support an "
                             f"oncogenic effect ({lines}; {cfg.comp_thresholds} thresholds).", src)
        return Criterion("SBP1", _PTS["SBP1"],
                         f"All {len(used)} utilised computational line(s) suggest no impact "
                         f"({lines}; {cfg.comp_thresholds} thresholds).", src)

    @staticmethod
    def _apply_exclusions(crit: List[Criterion]) -> List[Criterion]:
        """Horak 2022 Table 2 caveats, in dependency order:
        OS3 not if OS1 (no nucleotide-level hotspot data); OS2 not if OS1 (no nucleotide-
        level functional data); OM1 not if OS1 or OS3; OM2 not if OVS1; OM4 not if OS1, OS3
        or OM1; OM3 not if OM1 or OM4. Removed criteria are dropped, not re-weighted."""
        codes = lambda: {c.code for c in crit}  # noqa: E731
        drop = set()
        if "OS1" in codes():
            drop |= {"OS3", "OS2", "OS2_Moderate"}
        crit = [c for c in crit if c.code not in drop]
        if codes() & {"OS1", "OS3"}:
            crit = [c for c in crit if c.code != "OM1"]
        if "OVS1" in codes():
            crit = [c for c in crit if c.code != "OM2"]
        if codes() & {"OS1", "OS3", "OM1"}:
            crit = [c for c in crit if c.code != "OM4"]
        if codes() & {"OM1", "OM4"}:
            crit = [c for c in crit if c.code != "OM3"]
        return crit
