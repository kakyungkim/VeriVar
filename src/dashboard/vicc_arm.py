"""Citable VICC rule arm for one persisted cohort record (dashboard + Fig S3 demo).

The cohort output (``data/outputs/cohort_interpretation.json``) stores the Generative and
Deterministic modes only; the SOP-strict VICC point engine
(:class:`src.classify.vicc_rules.VICCPointClassifier`, default ``sop_strict``) is not run
per variant by the pipeline. This module runs it on demand so the dashboard and the
Supplementary Figure S3 demo show the engine's own codes, points and call, never
hand-written ones.

Signals are taken from committed, offline sources only, mirroring the Horak evaluation
wiring (``scripts/run_horak_vicc.py``):

* AlphaMissense score  -> the ``AlphaMissense:*`` item in the persisted ``bundle``;
* CIViC                -> the persisted bundle's CIViC items, reduced by
  :func:`civic_signal_from_rows` (only functional studies can grant OS2/SBS2);
* hotspots             -> ``data/knowledge/hotspots/cancerhotspots.json`` (engine default);
* OM1 site             -> ``data/knowledge/domains/uniprot_domains.json``;
* DMS (OS2/SBS2)       -> ``data/knowledge/functional/dms_{lof,neutral}.json``;
* gnomAD AF (OP4/SBS1/SBVS1) -> the cached Ensembl VEP record in
  ``data/knowledge/vep_byo_cache.json`` for the variant's GRCh37 coordinates (taken from
  ``data/cohorts/*.json``), using the same convention as ``horak_gnomad.json`` (max
  gnomAD exome/genome AF of the alt allele; 0.0 when the record has no gnomAD entry).
  When no cached VEP record exists, gnomAD is reported as *not assessed* and the
  SOP-strict engine awards no OP4.

No network access, no LLM call.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from src.classify.vicc_rules import (PRIMARY_CONFIG, VICCPointClassifier, VICCResult,
                                     civic_signal_from_rows, domain_feature_at,
                                     parse_protein_change)

_ROOT = Path(__file__).resolve().parents[2]
_COHORTS = _ROOT / "data" / "cohorts"
_DOMAINS = _ROOT / "data" / "knowledge" / "domains" / "uniprot_domains.json"
_FUNC = _ROOT / "data" / "knowledge" / "functional"
_VEP_CACHE = _ROOT / "data" / "knowledge" / "vep_byo_cache.json"
_EID = re.compile(r"CIViC:EID(\d+)")


@dataclass
class VICCArm:
    """Engine output plus the provenance of every input signal (for display)."""
    result: VICCResult
    config: str
    inputs: Dict[str, str] = field(default_factory=dict)
    coords: Optional[str] = None
    gnomad_af: Optional[float] = None

    @property
    def call(self) -> str:
        return self.result.oncogenicity.value

    @property
    def points(self) -> int:
        return self.result.points

    def rows(self) -> List[Dict[str, Any]]:
        out = []
        for c in self.result.criteria:
            text = c.statement
            # Display only: the engine prints OP4 AF with 5 decimals, so a real AF such as
            # 1.4e-06 reads "0.00000". Show it in scientific notation (same value).
            if c.code == "OP4" and self.gnomad_af:
                text = f"Extremely rare in gnomAD (AF {self.gnomad_af:.2e})."
            out.append({"code": c.code, "points": c.points, "statement": text,
                        "source": c.source})
        return out


def _load(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else {}


@lru_cache(maxsize=1)
def _domains() -> Dict:
    return _load(_DOMAINS)


@lru_cache(maxsize=1)
def _dms() -> tuple:
    return _load(_FUNC / "dms_lof.json"), _load(_FUNC / "dms_neutral.json")


@lru_cache(maxsize=1)
def _vep_cache() -> Dict:
    return _load(_VEP_CACHE)


@lru_cache(maxsize=1)
def _cohort_coords() -> Dict[tuple, tuple]:
    """(sample_id, gene, protein_change) -> (chrom, pos, ref, alt) from cohort snapshots."""
    out: Dict[tuple, tuple] = {}
    for p in sorted(_COHORTS.glob("*_tcga_*.json")):
        for m in _load(p).get("mutations", []):
            out[(m.get("sample_id"), m.get("gene"), m.get("protein_change"))] = (
                str(m.get("chrom")), int(m.get("pos")), m.get("ref"), m.get("alt"))
    return out


@lru_cache(maxsize=4)
def _classifier(config: str) -> VICCPointClassifier:
    return VICCPointClassifier(config=config)


def coords_for(rec: Mapping[str, Any]) -> Optional[tuple]:
    """GRCh37 (chrom, pos, ref, alt) for a cohort record, or None."""
    gene, aa = rec.get("gene"), (rec.get("hgvsp") or "").replace("p.", "")
    table = _cohort_coords()
    for sid in rec.get("sample_ids") or []:
        hit = table.get((sid, gene, aa))
        if hit:
            return hit
    return None


def gnomad_af_for(coords: Optional[tuple]) -> Optional[float]:
    """gnomAD AF from the cached VEP record (horak_gnomad.json convention), else None."""
    if not coords:
        return None
    chrom, pos, ref, alt = coords
    cache = _vep_cache()
    rec = None
    for key in (f"GRCH37|v2|{chrom} {pos} {ref} {alt}", f"GRCH37|{chrom} {pos} {ref} {alt}"):
        if key in cache and cache[key].get("colocated_variants") is not None:
            rec = cache[key]
            break
    if rec is None:
        return None
    af = 0.0
    for cv in rec.get("colocated_variants") or []:
        fr = (cv.get("frequencies") or {}).get(alt) or {}
        for k in ("gnomade", "gnomadg"):
            if k in fr:
                af = max(af, float(fr[k]))
    return af


def _civic_rows(evidences: List[Mapping[str, Any]], gene: str) -> List[Dict[str, Any]]:
    """Persisted bundle CIViC items -> CIViC-export-shaped rows for the engine."""
    rows = []
    for e in evidences:
        if (e.get("source") or "").lower() != "civic":
            continue
        m = _EID.search(e.get("id") or "")
        variant = (e.get("variant") or "").replace("p.", "")
        pmids = e.get("pmids") or []
        rows.append({
            "molecular_profile": f"{gene} {variant}",
            "evidence_type": e.get("evidence_type") or "",
            "evidence_direction": e.get("direction") or "",
            "significance": e.get("significance") or "",
            "evidence_level": e.get("evidence_level") or "",
            "evidence_id": m.group(1) if m else "",
            "citation_id": pmids[0] if pmids else "",
        })
    return rows


def score_record(rec: Mapping[str, Any], config: str = PRIMARY_CONFIG) -> VICCArm:
    """Run the VICC point engine on one persisted cohort record."""
    gene, aa = rec.get("gene", ""), rec.get("hgvsp", "")
    evidences = (rec.get("bundle") or {}).get("evidences") or []
    clf = _classifier(config)
    pp = parse_protein_change(aa)
    inputs: Dict[str, str] = {}

    am = next((e.get("score") for e in evidences
               if (e.get("source") or "") == "AlphaMissense" and e.get("score") is not None),
              None)
    inputs["AlphaMissense"] = f"{am:.3f}" if am is not None else "none in bundle"

    civic = None
    if pp:
        civic = civic_signal_from_rows(_civic_rows(evidences, gene), gene, *pp)
        n_func = len(civic.onco_eids) + len(civic.benign_eids)
        inputs["CIViC functional"] = (f"{n_func} functional item(s)"
                                      + (f"; {sum(civic.ignored.values())} non-functional "
                                         f"item(s) grant no code" if civic.ignored else ""))
    in_dom = domain_feature_at(_domains(), gene, pp[1], clf.config.om1_scope) if pp else None
    dms_lof, dms_neu = _dms()
    vkey = f"{pp[0]}{pp[1]}{pp[2]}" if pp else ""
    flof = bool(pp and dms_lof.get(gene, {}).get(vkey, False))
    fneu = bool(pp and dms_neu.get(gene, {}).get(vkey, False))

    coords = coords_for(rec)
    gaf = gnomad_af_for(coords)
    inputs["gnomAD"] = ("not assessed (no cached VEP record; OP4 not evaluable)"
                        if gaf is None else
                        ("absent" if gaf == 0 else f"AF {gaf:.2e}") + " (cached Ensembl VEP)")
    res = clf.score(gene, aa, am_pathogenicity=am, civic=civic, in_domain=in_dom,
                    gnomad_af=gaf, functional_lof=flof, functional_neutral=fneu)
    coord_s = f"GRCh37 {coords[0]}:{coords[1]} {coords[2]}>{coords[3]}" if coords else None
    return VICCArm(result=res, config=config, inputs=inputs, coords=coord_s,
                   gnomad_af=gaf)
