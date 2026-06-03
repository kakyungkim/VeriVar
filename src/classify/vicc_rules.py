"""Full(er) ClinGen/CGC/VICC point-based oncogenicity engine — citable by design.

The original `rules.py` is a deliberately simplified CIViC+AlphaMissense heuristic.
This module implements the point-based VICC combining rules (Horak et al. 2022) over
INDEPENDENT data sources — cancerhotspots.org (OS3/OM3/OP3), a curated tumour-suppressor
list (OVS1), AlphaMissense (OP1/SBP1), and CIViC functional/clinical evidence
(OS2/OM1 vs SBS2) — and emits EVERY fired criterion as a citable record (code + points +
statement + source), so the call is fully auditable. The Horak gold SOP codes/points are
never read, so the engine is not fit to the benchmark.

Point thresholds (Horak 2022): Oncogenic >=10, Likely Oncogenic 6-9, VUS 0-5,
Likely Benign -1..-6, Benign <=-7.
"""
import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

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

_NULL = re.compile(r"(\*|Ter|fs|ext|splice)", re.I)
_AA = re.compile(r"([A-Za-z])(\d+)(.*)")

# Point value per VICC strength.
_PTS = {"OVS1": 8, "OS1": 4, "OS2": 4, "OS3": 4, "OM1": 2, "OM3": 2, "OM4": 2,
        "OP1": 1, "OP3": 1, "OP4": 1, "SBS2": -4, "SBP1": -1, "SBVS1": -8, "SBS1": -4}


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
    (signals from an EvidenceBundle)."""

    def __init__(self, hotspots: Optional[Dict] = None, residue_hotspot: bool = False):
        self.hotspots = hotspots if hotspots is not None else _load_hotspots()
        # When True, the OS3/OM3/OP3 tier uses the TOTAL recurrence at the residue
        # (the faithful Horak/cancerhotspots definition) rather than the count for the
        # specific substitution. Raises sensitivity (recovers e.g. FLT3 D835E) at a small
        # specificity cost (a rare substitution at a strong hotspot residue, e.g.
        # PIK3CA H1047Q, can inherit the residue's recurrence). Off by default.
        self.residue_hotspot = residue_hotspot

    def score(self, gene: str, aa: str, *,
              am_pathogenicity: Optional[float] = None,
              civic_onco: int = 0, civic_benign: int = 0,
              civic_best_level: Optional[str] = None,
              in_domain: Optional[str] = None,
              functional_lof: bool = False,
              functional_neutral: bool = False,
              gnomad_af: Optional[float] = None,
              known_oncogenic: bool = False) -> VICCResult:
        crit: List[Criterion] = []
        pp = parse_protein_change(aa)
        is_null = bool(_NULL.search(aa or ""))

        # OS1 — same amino-acid change as a previously established oncogenic variant
        # (curated knowledge base, e.g. OncoKB / ClinVar somatic oncogenicity). This is
        # the guideline criterion OncoVI uses for much of its sensitivity; supplied as an
        # OPTIONAL, disclosed-circularity signal (see scripts/fetch_horak_clinvar.py).
        if known_oncogenic:
            crit.append(Criterion("OS1", _PTS["OS1"],
                                  f"{gene} {aa} is an established oncogenic variant in a "
                                  f"curated knowledge base.", "OncoKB/ClinVar"))

        # OVS1 — null variant in a tumour suppressor (loss of function).
        if is_null and gene in TUMOUR_SUPPRESSORS:
            crit.append(Criterion("OVS1", _PTS["OVS1"],
                                  f"{gene} {aa} is a null (LoF) variant in a tumour-suppressor gene.",
                                  "VICC/CGC"))
        elif pp:
            ref, pos, alt = pp
            # OM1 — located in a well-established functional domain (UniProt).
            if in_domain:
                crit.append(Criterion("OM1", _PTS["OM1"],
                                      f"{gene} {ref}{pos} lies in the {in_domain} functional domain.",
                                      "UniProt"))
            # OS2 / SBS2 — well-established functional study (DMS/MAVE).
            if functional_lof:
                crit.append(Criterion("OS2", _PTS["OS2"],
                                      f"Deep mutational scanning shows {gene} {ref}{pos}{alt} is "
                                      f"loss-of-function / damaging.", "MaveDB/DMS"))
            elif functional_neutral:
                crit.append(Criterion("SBS2", _PTS["SBS2"],
                                      f"Deep mutational scanning shows {gene} {ref}{pos}{alt} is "
                                      f"functionally neutral (no effect).", "MaveDB/DMS"))
            # OS3/OM3/OP3 — recurrence at a statistical hotspot (cancerhotspots.org).
            res = self.hotspots.get(gene, {}).get(str(pos)) or self.hotspots.get(gene, {}).get(pos)
            if res:
                c = sum(res.values()) if self.residue_hotspot else res.get(alt, 0)
                if c >= 50:
                    crit.append(Criterion("OS3", _PTS["OS3"],
                                          f"{gene} {ref}{pos}{alt} occurs in {c} samples at a "
                                          f"cancerhotspots.org hotspot residue.", "cancerhotspots"))
                elif c >= 10:
                    crit.append(Criterion("OM3", _PTS["OM3"],
                                          f"{gene} {ref}{pos}{alt} occurs in {c} samples at a "
                                          f"hotspot residue.", "cancerhotspots"))
                else:
                    crit.append(Criterion("OP3", _PTS["OP3"],
                                          f"{gene} residue {ref}{pos} is a cancerhotspots.org "
                                          f"hotspot.", "cancerhotspots"))

        # OS2 (strong) / OM4 (moderate) vs SBS2 — CIViC functional/clinical evidence.
        if civic_onco > 0:
            if civic_best_level in ("A", "B") and not any(c.code == "OS2" for c in crit):
                crit.append(Criterion("OS2", _PTS["OS2"],
                                      f"{civic_onco} CIViC evidence item(s) (level {civic_best_level}) "
                                      f"support an oncogenic role.", "CIViC"))
            elif not any(c.code in ("OS2", "OM4") for c in crit):
                crit.append(Criterion("OM4", _PTS["OM4"],
                                      f"{civic_onco} CIViC evidence item(s) support an oncogenic role.",
                                      "CIViC"))
        if civic_benign > civic_onco:
            crit.append(Criterion("SBS2", _PTS["SBS2"],
                                  f"{civic_benign} CIViC evidence item(s) refute an oncogenic role "
                                  f"(e.g. unaltered function / does not support).", "CIViC"))

        # OP1/SBP1 — computational (AlphaMissense).
        if am_pathogenicity is not None:
            if am_pathogenicity >= 0.564:
                crit.append(Criterion("OP1", _PTS["OP1"],
                                      f"AlphaMissense predicts pathogenic ({am_pathogenicity:.3f}).",
                                      "AlphaMissense"))
            elif am_pathogenicity <= 0.34:
                crit.append(Criterion("SBP1", _PTS["SBP1"],
                                      f"AlphaMissense predicts benign ({am_pathogenicity:.3f}).",
                                      "AlphaMissense"))

        # SBVS1 / SBS1 — common in the population => benign (gnomAD).
        if gnomad_af is not None and gnomad_af >= 0.05:
            crit.append(Criterion("SBVS1", _PTS["SBVS1"],
                                  f"Population allele frequency {gnomad_af:.3f} (>=5%) in gnomAD.", "gnomAD"))
        elif gnomad_af is not None and gnomad_af >= 0.01:
            crit.append(Criterion("SBS1", _PTS["SBS1"],
                                  f"Population allele frequency {gnomad_af:.3f} (>=1%) in gnomAD.", "gnomAD"))

        # OP4 — absent / very rare in population databases (real gnomAD if provided,
        # else approximated for recurrent somatic / CIViC-supported, non-OVS1 calls).
        has_onco = any(c.code in ("OS1", "OS3", "OM3", "OP3", "OS2", "OM1", "OM4") for c in crit)
        has_benign_pop = any(c.code in ("SBVS1", "SBS1") for c in crit)
        if has_onco and not any(c.code == "OVS1" for c in crit) and not has_benign_pop:
            if gnomad_af is not None:
                if gnomad_af < 1e-4:
                    crit.append(Criterion("OP4", _PTS["OP4"],
                                          f"Absent / very rare in gnomAD (AF {gnomad_af:.5f}).", "gnomAD"))
            else:
                crit.append(Criterion("OP4", _PTS["OP4"],
                                      "Recurrent somatic variant, absent/rare in population databases "
                                      "(approximated; gnomAD not queried).", "approx"))

        points = sum(c.points for c in crit)
        onc = classify_points(points)
        # A single benign line without populational support is too weak to call
        # Likely Benign on its own -> abstain to VUS (matches expert conservatism;
        # a benign classification normally needs gnomAD frequency or two lines).
        # This covers both a lone computational SBP1 and a lone functional SBS2
        # (e.g. a DMS "neutral" call that contradicts the clinical picture).
        neg = [c for c in crit if c.points < 0]
        has_pop_benign = any(c.code in ("SBVS1", "SBS1") for c in crit)
        if onc == VICCOncogenicity.LIKELY_BENIGN and not has_pop_benign and len(neg) <= 1:
            onc = VICCOncogenicity.VUS
        return VICCResult(onc, points, crit)
