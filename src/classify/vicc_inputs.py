"""Offline input loaders for the ``sop_strict_v2`` family of VICC configurations.

Pre-registration: notes/audits/2026-09-24/개선라운드_사전명시_20260924.md (local-only notes).
The snapshots are written by ``scripts/fetch_vicc_v2_inputs.py`` (the only network step);
this module only reads them, so every consumer stays offline-reproducible.

Per-variant inputs (keyed by the GRCh38 ``"chrom pos ref alt"`` string, see :func:`v2_key`):
  * computational predictor lines for OP1/SBP1 (change a): REVEL, CADD phred, SIFT,
    PolyPhen-2 from Ensembl VEP; AlphaMissense stays on the existing snapshots (only its
    thresholds change) and the VEP value is kept for QC;
  * ``pop_max5`` — the maximum alternate-allele frequency over the five SOP continental
    populations (African, Latino/Admixed American, East Asian, Non-Finnish European, South
    Asian) in gnomAD v4 exomes and genomes (change b);
  * DMS loss-of-function calls ``dms_lof_v2.json`` and the CIViC release union (change c).

Transcript rules (pre-registered): SIFT/PolyPhen-2 from the gene's MANE Select transcript
(else canonical); REVEL from a same-gene transcript whose amino-acid change equals the MANE
one (the REVEL plugin annotates older Ensembl transcripts only; first by transcript id when
values differ); CADD is variant-level. If the MANE amino-acid change or position disagrees
with the benchmark protein change, REVEL/SIFT/PolyPhen-2 are set to missing (CADD kept).
"""
import csv
import glob
import json
import os
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
KNOW = os.path.join(ROOT, "data", "knowledge")
VEP_V2 = os.path.join(KNOW, "vep_v2", "vep_v2_annotations.json")
DMS_V1 = os.path.join(KNOW, "functional", "dms_lof.json")
DMS_V2 = os.path.join(KNOW, "functional", "dms_lof_v2.json")
CIVIC_V1 = [os.path.join(BENCH, "horak_civic.tsv"),
            os.path.join(KNOW, "civic", "civic_evidence_panel.tsv")]
CIVIC_RELEASE_GLOB = os.path.join(KNOW, "civic", "civic_evidence_release_*.tsv")
HORAK_TSV = os.path.join(BENCH, "horak_benchmark.tsv")
CLINVAR_TSV = os.path.join(BENCH, "clinvar_onc", "clinvar_oncogenicity_missense_grch38.tsv")

# SOP SBVS1/SBS1: "any of 5 general continental populations: African, East Asian, European
# (Non-Finnish), Latino, and South Asian" (gnomAD v4 labels; amr = Admixed American/Latino).
CONTINENTAL_POPS = ("afr", "amr", "eas", "nfe", "sas")
PREDICTOR_FIELDS = ("revel", "cadd_phred", "sift", "polyphen")
_AA = re.compile(r"^p?\.?([A-Z])(\d+)([A-Z*])$")


def v2_key(chrom: Any, pos: Any, ref: str, alt: str) -> str:
    """GRCh38 variant key without the ``chr`` prefix: ``"17 7670669 G T"``."""
    return f"{str(chrom).replace('chr', '')} {int(pos)} {ref} {alt}"


def _read_tsv(path: str) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def horak_variants() -> List[dict]:
    """Horak-70 rows with GRCh38 coordinates (gold columns are not returned)."""
    out = []
    for r in _read_tsv(HORAK_TSV):
        out.append({"benchmark": "horak", "gene": r["gene"], "aa": r["aa"],
                    "chrom": r["b38_chr"].replace("chr", ""), "pos": int(r["b38_pos"]),
                    "ref": r["b38_ref"], "alt": r["b38_alt"]})
    return out


def clinvar_variants() -> List[dict]:
    """ClinVar oncogenicity snapshot rows (GRCh38); labels are not returned."""
    out = []
    for r in _read_tsv(CLINVAR_TSV):
        out.append({"benchmark": "clinvar", "gene": r["gene"], "aa": r["aa"],
                    "chrom": r["chrom"], "pos": int(r["pos"]), "ref": r["ref"],
                    "alt": r["alt"], "variation_id": r["variation_id"]})
    return out


# --------------------------------------------------------------------------- VEP parsing
def parse_vep_v2_record(rec: Mapping[str, Any], gene: str) -> dict:
    """Reduce one VEP REST record to the pre-registered v2 fields (see module docstring)."""
    alt = str(rec.get("allele_string", "/")).split("/")[-1]
    tcs = [t for t in (rec.get("transcript_consequences") or [])
           if t.get("gene_symbol") == gene]
    mane = next((t for t in tcs if t.get("mane_select")), None)
    main = mane or next((t for t in tcs if t.get("canonical")), None)
    out: Dict[str, Any] = {"vep_returned": True, "gene": gene,
                           "main_transcript": main.get("transcript_id") if main else None,
                           "main_is_mane": bool(mane),
                           "main_amino_acids": main.get("amino_acids") if main else None,
                           "main_protein_start": main.get("protein_start") if main else None,
                           "most_severe_consequence": rec.get("most_severe_consequence")}
    cadd = next((t.get("cadd_phred") for t in (rec.get("transcript_consequences") or [])
                 if t.get("cadd_phred") is not None), None)
    out["cadd_phred"] = cadd
    out["sift"] = main.get("sift_score") if main else None
    out["polyphen"] = main.get("polyphen_score") if main else None
    am = (main or {}).get("alphamissense") or {}
    out["am_vep"] = am.get("am_pathogenicity")
    revels = []
    if main and main.get("amino_acids"):
        for t in sorted(tcs, key=lambda t: t.get("transcript_id", "")):
            if t.get("amino_acids") == main["amino_acids"] and t.get("revel") is not None:
                revels.append((t["transcript_id"], float(t["revel"])))
    out["revel"] = revels[0][1] if revels else None
    out["revel_transcript"] = revels[0][0] if revels else None
    out["revel_n_distinct"] = len({v for _, v in revels})
    freqs: Dict[str, float] = {}
    for cv in rec.get("colocated_variants") or []:
        fr = (cv.get("frequencies") or {}).get(alt) or {}
        for k, v in fr.items():
            if k.startswith("gnomade") or k.startswith("gnomadg"):
                try:
                    freqs[k] = max(freqs.get(k, 0.0), float(v))
                except (TypeError, ValueError):
                    continue
    out["gnomad_freqs"] = freqs
    pm, src = pop_max5(freqs)
    out["pop_max5"], out["pop_max5_source"] = pm, src
    return out


def pop_max5(freqs: Mapping[str, float]) -> Tuple[float, Optional[str]]:
    """Maximum AF over the 5 SOP continental populations in gnomAD exomes and genomes.

    Absent populations count as 0.0 (VEP returned the variant but no gnomAD record)."""
    best, src = 0.0, None
    for ds in ("gnomade", "gnomadg"):
        for p in CONTINENTAL_POPS:
            v = freqs.get(f"{ds}_{p}")
            if v is not None and float(v) > best:
                best, src = float(v), f"{ds}_{p}"
    return best, src


def aa_matches(aa: str, amino_acids: Optional[str], protein_start: Any) -> bool:
    """True if VEP's main-transcript change ('D/Y', 835) equals the protein change 'p.D835Y'."""
    m = _AA.match(str(aa or "").strip())
    if not m or not amino_acids or protein_start in (None, ""):
        return False
    parts = str(amino_acids).split("/")
    return (len(parts) == 2 and parts[0] == m.group(1) and parts[1] == m.group(3)
            and int(protein_start) == int(m.group(2)))


# --------------------------------------------------------------------------- loaders
def load_json(path: str) -> dict:
    return json.load(open(path)) if os.path.exists(path) else {}


def load_vep_v2() -> Dict[str, dict]:
    return load_json(VEP_V2)


def load_dms_lof(version: str = "v1") -> Dict[str, Dict[str, bool]]:
    """DMS LoF calls: ``v1`` = the existing TP53/PTEN file; ``v2`` = + pre-registered MaveDB
    additions (falls back to v1 if the v2 snapshot is missing)."""
    if version == "v2" and os.path.exists(DMS_V2):
        return load_json(DMS_V2)
    return load_json(DMS_V1)


def civic_release_paths() -> List[str]:
    return sorted(glob.glob(CIVIC_RELEASE_GLOB))


def load_civic_rows(version: str = "v1", base_paths: Optional[Iterable[str]] = None
                    ) -> List[dict]:
    """CIViC evidence rows. ``v1`` = the existing snapshots (``base_paths`` or both panel TSVs);
    ``v2`` = those plus the latest monthly release, deduplicated by evidence_id with the
    existing rows taking precedence (additions only)."""
    paths = list(base_paths) if base_paths is not None else list(CIVIC_V1)
    if version == "v2":
        rel = civic_release_paths()
        paths = paths + rel[-1:]
    seen, rows = set(), []
    for p in paths:
        if not os.path.exists(p):
            continue
        for r in _read_tsv(p):
            eid = r.get("evidence_id")
            if eid in seen:
                continue
            seen.add(eid)
            rows.append(r)
    return rows


# --------------------------------------------------------------------------- per variant
def variant_inputs(v: Mapping[str, Any], vep: Mapping[str, dict],
                   dms_v2: Optional[Mapping[str, Mapping[str, bool]]] = None) -> dict:
    """Pre-registered v2 inputs for one benchmark variant (dict with the fields the engine
    consumes: ``predictors`` and ``pop_af_max5``, plus QC fields)."""
    k = v2_key(v["chrom"], v["pos"], v["ref"], v["alt"])
    a = vep.get(k) or {}
    ok = aa_matches(v["aa"], a.get("main_amino_acids"), a.get("main_protein_start"))
    preds = {"cadd_phred": a.get("cadd_phred")}
    for f in ("revel", "sift", "polyphen"):
        preds[f] = a.get(f) if ok else None
    m = _AA.match(str(v["aa"]))
    vkey = f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else ""
    dms = bool(dms_v2 and vkey and (dms_v2.get(v["gene"]) or {}).get(vkey))
    return {"key": k, "gene": v["gene"], "aa": v["aa"],
            "vep_returned": bool(a.get("vep_returned")), "aa_match": ok,
            "predictors": preds,
            "pop_af_max5": a.get("pop_max5") if a.get("vep_returned") else None,
            "pop_af_max5_source": a.get("pop_max5_source"),
            "am_vep": a.get("am_vep"), "revel_n_distinct": a.get("revel_n_distinct", 0),
            "dms_lof_v2": dms}


def build_benchmark_inputs(variants: List[Mapping[str, Any]]) -> Tuple[Dict[str, dict], dict]:
    """Per-variant v2 inputs keyed by ``"GENE p.AA"`` plus a coverage summary."""
    vep = load_vep_v2()
    dms_v2 = load_dms_lof("v2")
    table: Dict[str, dict] = {}
    for v in variants:
        e = variant_inputs(v, vep, dms_v2)
        table[f"{v['gene']} {v['aa']}|{e['key']}"] = e
    vals = list(table.values())
    cov = {"n": len(vals), "vep_returned": sum(e["vep_returned"] for e in vals),
           "aa_match": sum(e["aa_match"] for e in vals),
           "revel_multi_distinct": sum(e["revel_n_distinct"] > 1 for e in vals),
           "pop_af_max5_gt_0.01": sum((e["pop_af_max5"] or 0) > 0.01 for e in vals),
           "pop_af_max5_gt_0.05": sum((e["pop_af_max5"] or 0) > 0.05 for e in vals),
           "dms_lof_v2": sum(e["dms_lof_v2"] for e in vals)}
    for f in PREDICTOR_FIELDS:
        cov[f"has_{f}"] = sum(e["predictors"].get(f) is not None for e in vals)
    return table, cov


# --------------------------------------------------------------------------- consumers
def needs_vep_v2(cfg: Any) -> bool:
    """True if a VICCConfig reads the v2 VEP snapshot (extra predictors or continental AF)."""
    extra = tuple(p for p in cfg.comp_predictors if p != "alphamissense")
    return bool(extra) or cfg.pop_af_mode == "continental_max"


class V2InputProvider:
    """Per-variant ``score()`` keyword arguments for a configuration.

    Legacy configurations get ``{}`` (their inputs are untouched). v2-family configurations
    get ``predictors`` (REVEL/CADD/SIFT/PolyPhen-2 from the VEP v2 snapshot, masked on a
    transcript mismatch) and ``pop_af_max5``. AlphaMissense is NOT supplied here; callers keep
    passing the existing snapshot value as ``am_pathogenicity``."""

    def __init__(self, cfg: Any, vep: Optional[Mapping[str, dict]] = None):
        self.cfg = cfg
        self.active = needs_vep_v2(cfg)
        self.vep = (vep if vep is not None else load_vep_v2()) if self.active else {}
        if self.active and not self.vep:
            raise FileNotFoundError(f"{VEP_V2} missing; run scripts.fetch_vicc_v2_inputs")
        self.n_missing = 0

    def kwargs(self, gene: str, aa: str, chrom: Any = None, pos: Any = None,
               ref: Optional[str] = None, alt: Optional[str] = None) -> dict:
        """Keyword arguments for ``VICCPointClassifier.score``. Coordinates are optional: a
        record without GRCh38 coordinates gets no v2 inputs (no predictor lines beyond
        AlphaMissense, no continental AF), exactly like a variant VEP did not return."""
        if not self.active:
            return {}
        if chrom in (None, "") or pos in (None, "") or not ref or not alt:
            self.n_missing += 1
            out: Dict[str, Any] = {}
            if any(p != "alphamissense" for p in self.cfg.comp_predictors):
                out["predictors"] = {}
            if self.cfg.pop_af_mode == "continental_max":
                out["pop_af_max5"] = None
            return out
        e = variant_inputs({"gene": gene, "aa": aa, "chrom": chrom, "pos": pos, "ref": ref,
                            "alt": alt}, self.vep)
        if not e["vep_returned"]:
            self.n_missing += 1
        out: Dict[str, Any] = {}
        if any(p != "alphamissense" for p in self.cfg.comp_predictors):
            out["predictors"] = e["predictors"]
        if self.cfg.pop_af_mode == "continental_max":
            out["pop_af_max5"] = e["pop_af_max5"]
        return out


def v2_resource_paths(cfg: Any) -> List[str]:
    """Snapshot files a configuration reads beyond the published inputs (for provenance)."""
    paths: List[str] = []
    if needs_vep_v2(cfg):
        paths.append(VEP_V2)
    if cfg.dms_inputs == "v2":
        paths.append(DMS_V2)
    if cfg.civic_inputs == "v2":
        paths += civic_release_paths()[-1:]
    return paths
