"""Bring-your-own-VCF ingestion -> canonical ``Variant`` objects.

Research / education / demo only — **NOT for clinical use**. This module lets a
user paste/upload their own VCF and receive the SAME dual-mode interpretation the
cohort pipeline produces, by reusing every downstream module (aggregator, rule +
LLM classifiers, faithfulness gate).

Two stages, mirroring ``src/cohort/loader.py``:

1. :func:`parse_vcf` — pure, offline text parsing of VCF into minimal
   ``{chrom, pos, ref, alt}`` records. Multiallelic ALTs are split into one
   record each; header/``#`` lines are skipped; malformed lines are reported as
   skipped rather than crashing the batch.
2. :func:`annotate_variants` — the ONLY network path here: resolves each record
   to gene symbol + protein change (HGVSp) + consequence via the Ensembl VEP REST
   API (the same endpoint family the AlphaMissense annotator already uses),
   picking the canonical / most-severe coding consequence, then builds a
   :class:`src.models.Variant`. The same candidate filter as ``loader.py`` drops
   silent / non-coding / no-protein-change calls (reported as skipped).

   Three throughput features make this tractable for real BYO-VCFs:

   * **Batch POST** — variants are sent to the VEP *region* POST endpoint
     (``/vep/human/region``) in chunks of :data:`_BATCH_SIZE` instead of one GET
     per variant. A whole-chunk HTTP failure marks just that chunk's records
     skipped (the rest of the file still annotates); a per-variant missing /
     non-coding result is skipped exactly as before.
   * **Persistent cache** — results are keyed by
     ``(assembly, chrom, pos, ref, alt)`` in a JSON cache under
     ``data/knowledge/`` (default :data:`DEFAULT_VEP_CACHE`, mirrors the
     AlphaMissense ``vep_cache.json`` pattern). Only cache misses are POSTed;
     re-runs / overlapping variants then hit zero network.
   * **Pre-filter** — ``max_variants`` caps how many records are annotated
     (overflow -> skipped). Two panel filters compose:

     - ``restrict_to_panel`` / ``panel_bed`` apply a **pre-VEP genomic-region
       filter**: records whose ``(chrom, pos)`` fall outside every driver-gene
       interval in the assembly-appropriate committed BED
       (``data/knowledge/panel/driver_panel_grch3{7,8}.bed``, built by
       ``scripts.fetch_panel_bed`` from Ensembl gene spans) are skipped *before*
       batching, so off-panel variants never reach the network. This is what
       actually reduces VEP calls on large / WGS VCFs.
     - ``panel_genes`` is the legacy **post-VEP gene-symbol filter**; it still
       trims downstream LLM cost but, applied after annotation, does not cut VEP
       calls. The two are independent and compose.

     See :func:`annotate_variants` and :func:`load_panel_bed`.
"""
from __future__ import annotations

import json
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from src.models import Variant
from src.cohort.loader import NON_CANDIDATE_TYPES, _variant_type

# Ensembl VEP REST. assembly="GRCh37" -> grch37 mirror (matches TCGA/cBioPortal
# coordinates); assembly="GRCh38" -> the default rest.ensembl.org host.
VEP_HOSTS = {
    "GRCH37": "https://grch37.rest.ensembl.org",
    "GRCH38": "https://rest.ensembl.org",
}
# VEP REST flags requested on every call so the parsed annotation carries more
# than gene/HGVSp. ``canonical``/``hgvs`` select the transcript + HGVSc/HGVSp;
# ``mane`` adds the MANE flag; ``numbers`` exon/intron numbers; ``variant_class``
# the SO variant class; ``sift``/``polyphen`` the pathogenicity predictors;
# ``af``/``af_gnomad`` the 1000G + gnomAD population allele frequencies. The
# GET (legacy per-variant seam) and the batch POST body MUST stay in sync.
_VEP_GET_FLAGS = (
    "canonical=1&hgvs=1&mane=1&numbers=1&variant_class=1"
    "&sift=1&polyphen=1&af=1&af_gnomad=1"
)
_VEP_POST_FLAGS = {
    "canonical": 1, "hgvs": 1, "mane": 1, "numbers": 1, "variant_class": 1,
    "sift": 1, "polyphen": 1, "af": 1, "af_gnomad": 1,
}
# Legacy single-variant GET path (kept for the per-variant ``_fetcher`` seam).
_VEP_PATH = ("/vep/human/region/{chrom}:{pos}-{end}/{alt}"
             "?content-type=application/json&" + _VEP_GET_FLAGS)
# Batch POST endpoint + how many variants per request (Ensembl caps at ~200).
_VEP_BATCH_PATH = "/vep/human/region"
_BATCH_SIZE = 200

# Persistent VEP annotation cache (mirrors AlphaMissense's vep_cache.json).
# Schema v2 keys are suffixed so the richer responses (now carrying impact,
# protein_position, SIFT/PolyPhen, colocated_variants, gnomAD AF, MANE, ...) are
# never confused with v1 entries that lacked those flags. Stale v1 keys are just
# ignored (treated as cache misses) and re-fetched.
_VEP_CACHE_SCHEMA = "v2"
DEFAULT_VEP_CACHE = Path("data/knowledge/vep_byo_cache.json")

# Committed driver-gene panel BEDs (gene spans from Ensembl REST gene-lookup,
# built by scripts.fetch_panel_bed). Keyed by normalized assembly label. Used by
# the pre-VEP genomic-region filter so off-panel records never hit the network.
PANEL_BED_DIR = Path("data/knowledge/panel")
PANEL_BED_FILES = {
    "GRCH37": PANEL_BED_DIR / "driver_panel_grch37.bed",
    "GRCH38": PANEL_BED_DIR / "driver_panel_grch38.bed",
}

# VEP consequence terms (SO terms) that are NOT interpretation candidates — the
# VCF analogue of loader.NON_CANDIDATE_TYPES. Anything not protein-altering.
_NON_CANDIDATE_CONSEQUENCES = {
    "synonymous_variant", "stop_retained_variant", "start_retained_variant",
    "intron_variant", "upstream_gene_variant", "downstream_gene_variant",
    "5_prime_UTR_variant", "3_prime_UTR_variant", "intergenic_variant",
    "non_coding_transcript_variant", "non_coding_transcript_exon_variant",
    "regulatory_region_variant", "TF_binding_site_variant",
    "mature_miRNA_variant", "NMD_transcript_variant",
}

# Rough severity ordering (most severe first) to break ties when VEP returns
# several coding consequences and none is flagged canonical.
_SEVERITY_ORDER = [
    "transcript_ablation", "splice_acceptor_variant", "splice_donor_variant",
    "stop_gained", "frameshift_variant", "stop_lost", "start_lost",
    "transcript_amplification", "inframe_insertion", "inframe_deletion",
    "missense_variant", "protein_altering_variant", "splice_region_variant",
]
_SEVERITY_RANK = {term: i for i, term in enumerate(_SEVERITY_ORDER)}


@dataclass
class SkippedRecord:
    """A VCF record that was dropped or failed, with a human-readable reason."""
    record: dict
    reason: str


@dataclass
class AnnotationResult:
    """Outcome of :func:`annotate_variants`: resolved variants + skipped/failed."""
    variants: List[Variant] = field(default_factory=list)
    skipped: List[SkippedRecord] = field(default_factory=list)


def _valid_base(s: str) -> bool:
    return bool(s) and all(c in "ACGTNacgtn" for c in s)


# Genome-build aliases seen in the wild, mapped to our canonical labels. Checked
# case-insensitively as whole-word/prefix tokens against VCF header reference /
# assembly declarations. GRCh37.p* / GRCh38.p* patch releases are matched by
# prefix. b37/b38 are the GATK resource-bundle aliases.
_GRCH37_TOKENS = ("grch37", "hg19", "b37", "human_g1k_v37")
_GRCH38_TOKENS = ("grch38", "hg38", "b38", "human_g1k_v38")


def detect_assembly(text: str) -> Optional[str]:
    """Infer the genome build from VCF header lines (pure, no network).

    Scans the ``##`` meta-information header for a build declaration and returns
    the canonical label:

    * ``"GRCh37"`` for hg19 / b37 / GRCh37 / GRCh37.p* (and ``human_g1k_v37``)
    * ``"GRCh38"`` for hg38 / b38 / GRCh38 / GRCh38.p* (and ``human_g1k_v38``)
    * ``None`` when no recognizable build token is present.

    Header lines inspected: ``##reference=``, ``##assembly=``, and any
    ``##contig=<...,assembly=...>`` line (the per-contig ``assembly=`` tag). The
    match is case-insensitive; patch releases (``GRCh38.p13``) match by prefix.
    GRCh38 is tested first so a header naming both (rare) does not misfire to 37.
    """
    haystack_parts: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not line.startswith("##"):
            # ``#CHROM`` column header or a data line: headers are all at the
            # top, so stop scanning once the meta-header block ends.
            break
        low = line.lower()
        if low.startswith("##reference=") or low.startswith("##assembly="):
            haystack_parts.append(low.split("=", 1)[1])
        elif low.startswith("##contig=") and "assembly=" in low:
            # pull the per-contig assembly= tag value (up to the next , or >)
            frag = low.split("assembly=", 1)[1]
            frag = frag.split(",", 1)[0].split(">", 1)[0]
            haystack_parts.append(frag)
    hay = " ".join(haystack_parts)
    if not hay:
        return None
    # GRCh38 first: a 38 token is unambiguous; 37 tokens never appear in a 38 hay.
    if any(tok in hay for tok in _GRCH38_TOKENS):
        return "GRCh38"
    if any(tok in hay for tok in _GRCH37_TOKENS):
        return "GRCh37"
    return None


def parse_vcf(text: str, drop_non_pass: bool = False) -> List[dict]:
    """Parse VCF text into ``{chrom, pos, ref, alt}`` records (pure, no network).

    * Header / ``##meta`` / column-header (``#CHROM``) and blank lines are skipped.
    * Multiallelic ALTs (comma-separated) are split into one record per ALT.
    * ``pos`` is coerced to int; rows with a non-numeric POS or invalid REF/ALT
      bases are silently skipped (malformed input shouldn't crash a batch).
    * ``drop_non_pass=True`` drops rows whose FILTER column is not ``PASS``/``.``.

    Returns a list of dict records (order preserved). Symbolic ALTs (``<DEL>``,
    breakends ``[`` / ``]``) and ``*`` (spanning deletion) are skipped — this
    parser targets small SNV/INDEL substitutions, like the cohort loader.
    """
    records: List[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 5:
            cols = line.split()  # tolerate space-separated pastes
        if len(cols) < 5:
            continue
        chrom, pos_s, _id, ref, alt_field = cols[0], cols[1], cols[2], cols[3], cols[4]
        flt = cols[6] if len(cols) > 6 else "."
        if drop_non_pass and flt not in ("PASS", "."):
            continue
        try:
            pos = int(pos_s)
        except ValueError:
            continue
        ref = ref.strip().upper()
        if not _valid_base(ref):
            continue
        for alt in alt_field.split(","):
            alt = alt.strip().upper()
            if alt in ("", ".", "*") or alt.startswith("<") or "[" in alt or "]" in alt:
                continue
            if not _valid_base(alt):
                continue
            records.append({"chrom": str(chrom).replace("chr", "").replace("CHR", ""),
                            "pos": pos, "ref": ref, "alt": alt})
    return records


# --------------------------------------------------------------------------- #
# VCF writer (symmetric with parse_vcf): serialize annotation + interpretation
# back out as a valid VCF v4.2 so users can download the combined result.
# Pure / offline — no network. Frontend wraps the returned string in a
# st.download_button.
# --------------------------------------------------------------------------- #

# Reserved characters that must never appear raw inside a VCF INFO value (the
# field separator ``;``, key/value ``=``, multi-value ``,``) plus our own
# pipe sub-field delimiter ``|``. Whitespace is collapsed to ``_`` first; any
# remaining reserved char is %-encoded (VEP/CSQ convention).
_VCF_INFO_RESERVED = {
    "%": "%25",  # encode the escape char first so it round-trips
    ";": "%3B",
    "=": "%3D",
    ",": "%2C",
    "|": "%7C",
    "\t": "%09",
    "&": "%26",  # CSQ uses & as a multi-value separator; keep it out too
    " ": "_",
}

# Sub-field order for the structured INFO. Stable count is load-bearing so the
# pipe-joined value stays parseable (always 11 in full mode, 3 in annotate-only).
_VERIVAR_FORMAT_FULL = (
    "Gene|HGVSp|Consequence|GenerativeOnc|GenerativeTier|"
    "DeterministicOnc|DeterministicTier|AlphaMissense|nEvidence|nDrugs|nTrials"
)
_VERIVAR_FORMAT_ANNOTATE = "Gene|HGVSp|Consequence"
_N_FIELDS_FULL = 11
_N_FIELDS_ANNOTATE = 3


def _vcf_info_safe(value) -> str:
    """Sanitize one INFO sub-field to be VCF-safe (VEP/CSQ-style encoding).

    Empty / ``None`` / missing -> ``"."``. Spaces collapse to ``_``; the reserved
    INFO characters (``; = , |`` and whitespace) are %-encoded so the pipe-joined
    value stays unambiguous and the line stays a valid VCFv4.2 INFO field.
    """
    if value is None:
        return "."
    s = str(value).strip()
    if not s:
        return "."
    # Encode the escape char first so existing '%' don't corrupt later codes.
    out = s.replace("%", _VCF_INFO_RESERVED["%"])
    for ch, enc in _VCF_INFO_RESERVED.items():
        if ch == "%":
            continue
        out = out.replace(ch, enc)
    return out


def _onc_value(mode: Optional[dict]) -> str:
    """Pull the oncogenicity label from a mode_a/mode_b result dict (or '.')."""
    if not isinstance(mode, dict):
        return "."
    return _vcf_info_safe(mode.get("oncogenicity"))


def _tier_value(mode: Optional[dict]) -> str:
    """Pull the AMP/ASCO/CAP tier from a mode_a/mode_b result dict (or '.')."""
    if not isinstance(mode, dict):
        return "."
    return _vcf_info_safe(mode.get("tier"))


def _alphamissense_value(result: Optional[dict]) -> str:
    """Extract the AlphaMissense score (preferred) or class from a result bundle.

    Scans ``result['bundle']['evidences']`` for the AlphaMissense item (the one
    emitted by :class:`AlphaMissenseAnnotator`, ``source == "AlphaMissense"``).
    Returns its numeric ``score`` formatted to 3 dp when present, else its
    ``evidence_level`` (the AM class string), else ``"."``.
    """
    if not isinstance(result, dict):
        return "."
    bundle = result.get("bundle") or {}
    for ev in bundle.get("evidences", []) or []:
        if not isinstance(ev, dict):
            continue
        if str(ev.get("source", "")).lower() != "alphamissense":
            continue
        score = ev.get("score")
        if isinstance(score, (int, float)):
            return _vcf_info_safe(f"{float(score):.3f}")
        cls = ev.get("evidence_level")
        if cls:
            return _vcf_info_safe(cls)
    return "."


def _verivar_info(row: dict, result: Optional[dict]) -> str:
    """Build the pipe-joined ``VERIVAR=...`` INFO value for one record.

    Field order/count is fixed (11 full, 3 annotate-only) so the value parses
    against the ``##INFO`` Format. Every sub-field is sanitized via
    :func:`_vcf_info_safe`.
    """
    gene = _vcf_info_safe(row.get("gene"))
    hgvsp = _vcf_info_safe(row.get("hgvsp"))
    consequence = _vcf_info_safe(row.get("variant_type"))

    if result is None:
        fields = [gene, hgvsp, consequence]
    else:
        fields = [
            gene,
            hgvsp,
            consequence,
            _onc_value(result.get("mode_a")),
            _tier_value(result.get("mode_a")),
            _onc_value(result.get("mode_b")),
            _tier_value(result.get("mode_b")),
            _alphamissense_value(result),
            _vcf_info_safe(result.get("n_evidence")),
            _vcf_info_safe(result.get("n_drugs")),
            _vcf_info_safe(result.get("n_trials")),
        ]
    return "VERIVAR=" + "|".join(fields)


def to_annotated_vcf(annotation_rows: List[dict], results: Optional[List[dict]] = None,
                     assembly: str = "GRCh37") -> str:
    """Serialize VEP annotation + VeriVar interpretation back out as a VCF v4.2.

    Symmetric counterpart of :func:`parse_vcf`: turns the dashboard's annotation
    rows (and, optionally, the index-aligned :func:`src.interpret.interpret_variants`
    result dicts) into a downloadable, valid VCFv4.2 string. Pure and offline —
    **no network**, research/education only (stamped in the header).

    Args:
        annotation_rows: dicts with ``chrom, pos, ref, alt, gene, hgvsp,
            variant_type, assembly`` — the VEP-annotation rows the dashboard
            already builds from ``ar.variants``.
        results: optional, **index-aligned** with ``annotation_rows`` — the
            ``interpret_variants`` output dicts (each with ``mode_a`` / ``mode_b``
            carrying ``oncogenicity`` / ``tier``, ``n_evidence`` / ``n_drugs`` /
            ``n_trials``, and a ``bundle`` whose evidences may include an
            AlphaMissense item). ``None`` -> annotate-only mode (3-field INFO).
        assembly: genome build, written to ``##reference=`` (default GRCh37).

    INFO encoding (critical): a single structured ``VERIVAR`` key whose value is
    a pipe-joined, VCF-safe record. Format (full mode)::

        Gene|HGVSp|Consequence|GenerativeOnc|GenerativeTier|
        DeterministicOnc|DeterministicTier|AlphaMissense|nEvidence|nDrugs|nTrials

    and ``Gene|HGVSp|Consequence`` in annotate-only mode. Each sub-field is
    sanitized (spaces -> ``_``; reserved ``; = , |`` and whitespace %-encoded;
    empty/missing -> ``.``) so the value never breaks the INFO grammar. The
    AlphaMissense sub-field is the AM score (else class) from the result bundle,
    else ``.``.

    Returns:
        A valid VCFv4.2 string: meta-header + ``#CHROM`` column header + one
        ``PASS`` data line per annotation row (8 tab-separated columns each).
    """
    annotate_only = results is None
    fmt = _VERIVAR_FORMAT_ANNOTATE if annotate_only else _VERIVAR_FORMAT_FULL
    desc = "VeriVar annotation. Format: " + fmt

    lines: List[str] = [
        "##fileformat=VCFv4.2",
        f"##reference={assembly}",
        "##source=VeriVar — research/education only, not for clinical use",
        f'##INFO=<ID=VERIVAR,Number=.,Type=String,Description="{desc}">',
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
    ]

    for i, row in enumerate(annotation_rows):
        result = None
        if not annotate_only and results is not None and i < len(results):
            result = results[i]
        info = _verivar_info(row, result)
        chrom = _vcf_info_safe(row.get("chrom"))
        pos = row.get("pos")
        pos_s = str(pos) if pos not in (None, "") else "."
        ref = _vcf_info_safe(row.get("ref"))
        alt = _vcf_info_safe(row.get("alt"))
        lines.append("\t".join([chrom, pos_s, ".", ref, alt, ".", "PASS", info]))

    return "\n".join(lines) + "\n"


def _vep_alleles(ref: str, alt: str) -> Tuple[int, str]:
    """Return (region_end, vep_allele) for the VEP region endpoint.

    VEP's region API expects an end coordinate spanning REF and an allele string.
    For a simple substitution end == pos and allele == alt. For indels we span
    the REF length so the region covers the deleted/replaced bases.
    """
    end_offset = max(len(ref) - 1, 0)
    return end_offset, alt


def _pick_consequence(vep_record: dict) -> Optional[dict]:
    """Choose the canonical / most-severe coding transcript consequence.

    Preference order: canonical coding transcript > most-severe coding
    consequence by :data:`_SEVERITY_RANK`. Non-coding / silent consequences are
    ignored (they make the variant a non-candidate).
    """
    coding: List[dict] = []
    for tc in vep_record.get("transcript_consequences", []):
        terms = tc.get("consequence_terms", []) or []
        # keep only transcripts with at least one candidate (protein-altering) term
        if all(t in _NON_CANDIDATE_CONSEQUENCES for t in terms):
            continue
        coding.append(tc)
    if not coding:
        return None

    def _rank(tc: dict) -> tuple:
        terms = tc.get("consequence_terms", []) or []
        sev = min((_SEVERITY_RANK.get(t, 999) for t in terms), default=999)
        canonical = 0 if tc.get("canonical") in (1, "1", True) else 1
        return (canonical, sev)

    return sorted(coding, key=_rank)[0]


# VEP emits 3-letter HGVSp (p.Val600Glu); the knowledge bases (CIViC, the
# variant_key) use 1-letter (p.V600E). Normalize so uploaded variants actually
# match retrieved evidence/drugs/trials — otherwise every BYO-VCF variant looks
# evidence-poor and abstains. (Ter -> * for nonsense; fs kept.)
_AA3TO1 = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q",
    "Glu": "E", "Gly": "G", "His": "H", "Ile": "I", "Leu": "L", "Lys": "K",
    "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W",
    "Tyr": "Y", "Val": "V", "Ter": "*", "Sec": "U", "Pyl": "O",
}
_AA3_RE = re.compile("|".join(_AA3TO1))


def _hgvsp_three_to_one(s: str) -> str:
    """Convert 3-letter residue codes in an HGVSp string to 1-letter (CIViC style)."""
    return _AA3_RE.sub(lambda m: _AA3TO1[m.group(0)], s)


def _protein_change(tc: dict) -> str:
    """Extract a 1-letter ``p.<change>`` HGVSp from a VEP transcript consequence."""
    hgvsp = tc.get("hgvsp") or ""
    if hgvsp and ":" in hgvsp:
        hgvsp = hgvsp.split(":", 1)[1]  # strip 'ENSP...:'
    if hgvsp and not hgvsp.startswith("p."):
        hgvsp = f"p.{hgvsp}"
    return _hgvsp_three_to_one(hgvsp)


def _consequence_to_variant_type(terms: List[str]) -> str:
    """Map VEP SO terms onto our SNV/INDEL classification (reuses loader logic)."""
    joined = " ".join(terms)
    if any(t in joined for t in ("frameshift", "inframe_insertion", "inframe_deletion")):
        return "INDEL"
    return "SNV"


def _parse_colocated(vep_item: dict) -> Tuple[Optional[str], Optional[str], Optional[float]]:
    """Extract (rsid, cosmic_id, gnomad_af) from a record's ``colocated_variants``.

    VEP returns a ``colocated_variants`` list on the *record* (not the transcript
    consequence); each entry has an ``id`` (e.g. ``rs113488022`` or ``COSV...`` /
    ``COSM...``) and, for known variants, population allele frequencies under
    ``frequencies`` keyed by allele then population (``gnomad`` / ``gnomADe`` /
    ``gnomADg`` / ``gnomad_*``). We take the first dbSNP ``rs`` id, the first
    COSMIC id, and the first gnomAD AF we can find. Missing -> None (never faked).
    """
    rsid: Optional[str] = None
    cosmic: Optional[str] = None
    gnomad_af: Optional[float] = None
    for cv in vep_item.get("colocated_variants", []) or []:
        if not isinstance(cv, dict):
            continue
        cid = str(cv.get("id", "") or "")
        if rsid is None and cid.lower().startswith("rs"):
            rsid = cid
        if cosmic is None and (cid.upper().startswith("COSV")
                               or cid.upper().startswith("COSM")):
            cosmic = cid
        if gnomad_af is None:
            gnomad_af = _extract_gnomad_af(cv)
    return rsid, cosmic, gnomad_af


def _extract_gnomad_af(cv: dict) -> Optional[float]:
    """Pull a gnomAD allele frequency out of one colocated-variant entry.

    Two shapes are accepted: (1) the nested ``frequencies`` map
    (``{allele: {population: af}}``) — preferred when present; (2) flat top-level
    keys VEP emits with ``af_gnomad`` (e.g. ``gnomad_af`` / ``gnomADe_AF`` /
    ``gnomADg_AF``). Returns the first numeric gnomAD AF found, else None.
    """
    freqs = cv.get("frequencies")
    if isinstance(freqs, dict):
        for _allele, pops in freqs.items():
            if not isinstance(pops, dict):
                continue
            for pop, val in pops.items():
                if "gnomad" in str(pop).lower() and isinstance(val, (int, float)):
                    return float(val)
    for k, val in cv.items():
        kl = str(k).lower()
        if "gnomad" in kl and kl.endswith("af") and isinstance(val, (int, float)):
            return float(val)
    return None


def _parse_predictor(tc: dict, name: str) -> Optional[dict]:
    """Extract a SIFT or PolyPhen prediction+score from a transcript consequence.

    VEP emits ``sift_prediction``/``sift_score`` and
    ``polyphen_prediction``/``polyphen_score`` on the transcript consequence when
    ``sift=1``/``polyphen=1`` are requested. Returns
    ``{"prediction": str|None, "score": float|None}`` if either is present, else
    None (missing predictors stay absent rather than fabricated).
    """
    pred = tc.get(f"{name}_prediction")
    score = tc.get(f"{name}_score")
    if pred is None and score is None:
        return None
    out: dict = {"prediction": pred if pred is not None else None}
    out["score"] = float(score) if isinstance(score, (int, float)) else None
    return out


def _parse_vep_annotation(vep_item: dict, tc: dict, terms: List[str]) -> dict:
    """Build the :attr:`Variant.vep` dict from the picked transcript + record.

    All values come from the SAME VEP REST response (the chosen canonical/most-
    severe transcript consequence ``tc`` and the record-level ``colocated_variants``
    / ``variant_class``). Nothing is fabricated; any field VEP didn't return stays
    ``None``. Key schema (see module docstring / tests):

    consequence, impact, transcript_id, canonical, mane, hgvsc, protein_position,
    amino_acids, rsid, cosmic, existing_variation, gnomad_af, sift, polyphen,
    variant_class.
    """
    rsid, cosmic, gnomad_af = _parse_colocated(vep_item)

    # protein_position: VEP gives ``protein_start``/``protein_end`` ints. Collapse
    # to a single position when start == end, else "start-end". None if absent.
    p_start = tc.get("protein_start")
    p_end = tc.get("protein_end")
    if p_start is None:
        protein_position: Optional[str] = None
    elif p_end is None or p_end == p_start:
        protein_position = str(p_start)
    else:
        protein_position = f"{p_start}-{p_end}"

    hgvsc = tc.get("hgvsc") or None
    if hgvsc and ":" in hgvsc:
        hgvsc = hgvsc.split(":", 1)[1]  # strip 'ENST...:' prefix -> bare c.

    canonical = tc.get("canonical") in (1, "1", True)
    mane = tc.get("mane") or tc.get("mane_select") or tc.get("mane_plus_clinical")

    return {
        "consequence": ",".join(terms) if terms else None,
        "impact": tc.get("impact"),
        "transcript_id": tc.get("transcript_id"),
        "canonical": canonical,
        "mane": mane if mane else None,
        "hgvsc": hgvsc,
        "protein_position": protein_position,
        "amino_acids": tc.get("amino_acids"),
        "rsid": rsid,
        "cosmic": cosmic,
        "existing_variation": rsid or cosmic,
        "gnomad_af": gnomad_af,
        "sift": _parse_predictor(tc, "sift"),
        "polyphen": _parse_predictor(tc, "polyphen"),
        "variant_class": vep_item.get("variant_class"),
    }


def _vep_fetch(host: str, chrom: str, pos: int, ref: str, alt: str, timeout: float) -> list:
    """Legacy single-variant VEP GET (still used by the per-variant ``_fetcher`` seam)."""
    end_offset, allele = _vep_alleles(ref, alt)
    url = host + _VEP_PATH.format(chrom=chrom, pos=pos, end=pos + end_offset, alt=allele)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    return data if isinstance(data, list) else [data]


def _rec_key(rec: dict) -> str:
    """Coordinate key used both for cache lookups and for matching VEP responses."""
    return f"{rec['chrom']} {rec['pos']} {rec['ref']} {rec['alt']}"


def _cache_key(assembly: str, rec: dict) -> str:
    """Cache key including assembly + schema version.

    The schema suffix (:data:`_VEP_CACHE_SCHEMA`) invalidates pre-enrichment v1
    entries automatically: they key differently, so they never satisfy a v2 lookup
    and are simply re-fetched. GRCh37 vs GRCh38 give different annotations, so the
    assembly is part of the key too.
    """
    return f"{assembly.upper()}|{_VEP_CACHE_SCHEMA}|{_rec_key(rec)}"


def _vep_region_string(rec: dict) -> str:
    """A default-format VEP region line: ``chrom pos . ref alt . . .``.

    VEP echoes this verbatim in each response item's ``input`` field, which we use
    to map results back to records when order can't be trusted.
    """
    return f"{rec['chrom']} {rec['pos']} . {rec['ref']} {rec['alt']} . . ."


def _input_to_key(input_str: str) -> Optional[str]:
    """Recover the ``_rec_key`` ('chrom pos ref alt') from a VEP echoed ``input``."""
    parts = (input_str or "").split()
    if len(parts) < 5:
        return None
    chrom, pos, _id, ref, alt = parts[0], parts[1], parts[2], parts[3], parts[4]
    chrom = str(chrom).replace("chr", "").replace("CHR", "")
    return f"{chrom} {pos} {ref} {alt}"


def _vep_batch_fetch(host: str, recs: List[dict], timeout: float) -> list:
    """POST a chunk of records to the VEP region endpoint; return the response list.

    Body matches the Ensembl spec; the enrichment flags (:data:`_VEP_POST_FLAGS`:
    ``mane``/``numbers``/``variant_class``/``sift``/``polyphen``/``af``/
    ``af_gnomad``) are merged alongside ``variants`` so the response carries
    impact, protein position, predictors, gnomAD AF and colocated variants::

        {"variants": ["<chrom> <pos> . <ref> <alt> . . .", ...],
         "canonical": 1, "hgvs": 1, "mane": 1, "sift": 1, "polyphen": 1,
         "af_gnomad": 1, ...}
    """
    body = json.dumps({
        "variants": [_vep_region_string(r) for r in recs],
        **_VEP_POST_FLAGS,
    }).encode()
    url = host + _VEP_BATCH_PATH
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    return data if isinstance(data, list) else [data]


def _index_batch_response(response: list, recs: List[dict]) -> Dict[str, dict]:
    """Map a VEP batch response back to per-record results, keyed by ``_rec_key``.

    Matches by the echoed ``input`` string first (robust to reordering); falls
    back to positional order for any items VEP returns without a usable ``input``.
    """
    by_key: Dict[str, dict] = {}
    leftover: List[dict] = []
    for item in response:
        key = _input_to_key(item.get("input", "")) if isinstance(item, dict) else None
        if key is not None:
            by_key[key] = item
        else:
            leftover.append(item)
    if leftover:  # positional fallback for items lacking a parseable input echo
        unmatched = [r for r in recs if _rec_key(r) not in by_key]
        for rec, item in zip(unmatched, leftover):
            by_key.setdefault(_rec_key(rec), item)
    return by_key


def _load_cache(cache_path: Path) -> dict:
    """Read the JSON VEP cache (empty dict if absent / unreadable)."""
    try:
        if cache_path.exists():
            return json.loads(cache_path.read_text())
    except (OSError, ValueError):
        pass
    return {}


def _save_cache(cache_path: Path, cache: dict) -> None:
    """Persist the VEP cache, creating ``data/knowledge/`` if needed."""
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2))
    except OSError:
        pass  # caching is best-effort; never fail annotation on a write error


# --------------------------------------------------------------------------- #
# Driver-gene panel region filter (pre-VEP)
# --------------------------------------------------------------------------- #
# A parsed BED is a dict: normalized-chrom -> list of (start, end, gene) intervals
# in BED 0-based half-open coordinates [start, end). Cached per resolved path so a
# large VCF parses the BED once.
PanelBed = Dict[str, List[Tuple[int, int, str]]]
_PANEL_BED_CACHE: Dict[str, PanelBed] = {}


def _norm_chrom(chrom: str) -> str:
    """Normalize a contig name to match parsed VCF records ('chr7'/'CHR7' -> '7')."""
    return str(chrom).replace("chr", "").replace("CHR", "")


def load_panel_bed(path: Path) -> PanelBed:
    """Parse a driver-gene panel BED into a chrom -> [(start, end, gene)] map.

    The BED is **0-based half-open** ``[start, end)`` (see scripts.fetch_panel_bed).
    ``#`` comment / header lines and malformed rows are skipped. Result is cached
    by resolved path so repeated calls (e.g. one large VCF) parse it once.
    """
    key = str(Path(path).resolve())
    cached = _PANEL_BED_CACHE.get(key)
    if cached is not None:
        return cached
    bed: PanelBed = {}
    text = Path(path).read_text()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("track"):
            continue
        cols = line.split("\t")
        if len(cols) < 3:
            cols = line.split()
        if len(cols) < 3:
            continue
        chrom = _norm_chrom(cols[0])
        try:
            start, end = int(cols[1]), int(cols[2])
        except ValueError:
            continue
        gene = cols[3] if len(cols) > 3 else ""
        bed.setdefault(chrom, []).append((start, end, gene))
    for intervals in bed.values():
        intervals.sort()
    _PANEL_BED_CACHE[key] = bed
    return bed


def _panel_bed_for_assembly(assembly: str, panel_bed: Optional[Path]) -> PanelBed:
    """Resolve the BED to use: explicit ``panel_bed`` else the committed assembly file."""
    if panel_bed is not None:
        return load_panel_bed(Path(panel_bed))
    bed_path = PANEL_BED_FILES.get((assembly or "GRCh37").upper())
    if bed_path is None:
        raise ValueError(
            f"No committed panel BED for assembly {assembly!r}; expected GRCh37/GRCh38"
        )
    return load_panel_bed(bed_path)


def _in_panel(rec: dict, bed: PanelBed) -> bool:
    """True if the record's (chrom, pos) falls within any panel interval.

    VCF ``pos`` is 1-based; BED intervals are 0-based half-open ``[start, end)``.
    A 1-based position ``p`` lies in the interval iff ``start < p <= end`` (i.e.
    the 0-based coordinate ``p-1`` satisfies ``start <= p-1 < end``).
    """
    chrom = _norm_chrom(rec["chrom"])
    pos = int(rec["pos"])
    for start, end, _gene in bed.get(chrom, ()):  # linear scan; panels are tiny
        if start < pos <= end:
            return True
    return False


def _build_variant(rec: dict, vep_item: Optional[dict],
                   cancer_type: Optional[str],
                   assembly: str = "GRCh37") -> Tuple[Optional[Variant], Optional[str]]:
    """Turn one VEP response item into a Variant, or return (None, skip_reason).

    Shared by the batch path and the legacy per-variant path so the candidate
    filter / canonical-consequence pick / HGVSp normalization stay identical.
    """
    if not vep_item:
        return None, "no VEP annotation returned"
    tc = _pick_consequence(vep_item)
    if tc is None:
        return None, "non-coding / silent (no candidate consequence)"

    terms = tc.get("consequence_terms", []) or []
    gene = tc.get("gene_symbol") or "Unknown"
    hgvsp = _protein_change(tc)
    # Candidate filter (mirrors loader.is_candidate): require a protein change for
    # substitutions; truncating events (frameshift/stop) qualify even without a
    # clean p. string.
    truncating = any(t in ("frameshift_variant", "stop_gained", "stop_lost",
                           "start_lost", "splice_acceptor_variant",
                           "splice_donor_variant") for t in terms)
    if not hgvsp and not truncating:
        return None, "no protein change (non-candidate)"

    variant = Variant(
        chrom=str(rec["chrom"]),
        pos=int(rec["pos"]),
        ref=rec["ref"],
        alt=rec["alt"],
        gene=gene,
        hgvsp=hgvsp,
        hgvsc=(tc.get("hgvsc") or ""),
        variant_type=_consequence_to_variant_type(terms),
        cancer_type=cancer_type,
        assembly=assembly,
        # Surface the full enriched annotation (consequence/impact/predictors/
        # gnomAD AF/rsID/...) as a single dict; core pipeline ignores it.
        vep=_parse_vep_annotation(vep_item, tc, terms),
    )
    return variant, None


def annotate_variants(
    records: List[dict],
    assembly: str = "GRCh37",
    cancer_type: Optional[str] = None,
    timeout: float = 60.0,
    max_variants: Optional[int] = None,
    restrict_to_panel: bool = False,
    panel_bed: Optional[Path] = None,
    panel_genes: Optional[List[str]] = None,
    cache_path: Optional[Path] = DEFAULT_VEP_CACHE,
    use_cache: bool = True,
    batch_size: int = _BATCH_SIZE,
    _fetcher: Optional[Callable] = None,
    _batch_fetcher: Optional[Callable] = None,
) -> AnnotationResult:
    """Resolve parsed VCF records to canonical :class:`Variant` objects via VEP.

    Throughput: instead of one GET per record, cache-missing records are POSTed to
    the Ensembl VEP *region* endpoint in chunks of ``batch_size`` (``assembly``
    selects the GRCh37 vs GRCh38 host). Results are matched back to records by the
    echoed ``input`` string (positional fallback). A whole-chunk HTTP failure
    marks just that chunk's records ``skipped`` so the rest of the file still
    annotates; a per-variant missing / non-candidate (silent / non-coding / no
    protein change) result is returned in ``skipped`` with a reason, exactly as
    before. ``cancer_type`` is stamped onto each resolved Variant.

    Caching: when ``use_cache`` is set, VEP results (hits *and* candidate-fail
    misses) are persisted keyed by ``(assembly, chrom, pos, ref, alt)`` in the
    JSON file at ``cache_path`` (default :data:`DEFAULT_VEP_CACHE`). Cached
    records skip the network entirely on re-runs / overlapping VCFs. Pass
    ``cache_path=None`` or ``use_cache=False`` to disable.

    Pre-filter (to make large VCFs tractable):

    * ``max_variants`` — annotate at most this many records; the overflow is
      returned skipped with reason ``"exceeded max_variants cap"``. Applied
      *before* any network so a huge VCF can't blow the budget.
    * ``restrict_to_panel`` / ``panel_bed`` — **pre-VEP genomic-region filter**.
      When ``restrict_to_panel=True`` (or an explicit ``panel_bed`` path is given)
      the assembly-appropriate committed driver-gene BED
      (``data/knowledge/panel/driver_panel_grch3{7,8}.bed``) is loaded and each
      record's ``(chrom, pos)`` is tested against the gene-span intervals. Records
      falling outside *every* interval are returned skipped with reason
      ``"outside driver-gene panel"`` **before batching**, so off-panel variants
      never reach the VEP endpoint — this is the filter that reduces VEP calls on
      large / WGS VCFs. It runs after the ``max_variants`` cap and before caching.
    * ``panel_genes`` — legacy **post-VEP gene-symbol filter**. Records whose
      VEP-resolved gene is outside the panel are returned skipped with reason
      ``"outside panel_genes"``. It composes with ``restrict_to_panel`` (region
      pre-filter then symbol post-filter) and still trims downstream LLM cost, but
      applied after annotation it does NOT reduce VEP calls.

    Test seams (no network in tests): ``_batch_fetcher`` is a callable
    ``(host, recs, timeout) -> list[dict]`` returning a VEP batch response; if
    omitted, the real POST is used. ``_fetcher`` keeps the legacy per-variant
    signature ``(host, chrom, pos, ref, alt, timeout) -> list[dict]`` and, when
    provided, is wrapped into the batch path (one call per record) so old mocks
    keep working.
    """
    host = VEP_HOSTS.get((assembly or "GRCh37").upper())
    if host is None:
        raise ValueError(f"Unknown assembly {assembly!r}; expected GRCh37 or GRCh38")
    asm = (assembly or "GRCh37")
    panel = {g.upper() for g in panel_genes} if panel_genes else None

    result = AnnotationResult()

    # (3) max_variants cap — applied before any network.
    if max_variants is not None and len(records) > max_variants:
        for rec in records[max_variants:]:
            result.skipped.append(SkippedRecord(rec, "exceeded max_variants cap"))
        records = records[:max_variants]

    # (3b) pre-VEP genomic-region (driver-gene panel) filter — drop off-panel
    # records BEFORE batching so they never reach the VEP endpoint. This is the
    # filter that cuts VEP calls on large / WGS VCFs (vs the post-VEP symbol
    # filter ``panel_genes``).
    if restrict_to_panel or panel_bed is not None:
        bed = _panel_bed_for_assembly(asm, panel_bed)
        in_panel: List[dict] = []
        for rec in records:
            if _in_panel(rec, bed):
                in_panel.append(rec)
            else:
                result.skipped.append(SkippedRecord(rec, "outside driver-gene panel"))
        records = in_panel

    # (2) cache: load, then split into hits / misses.
    cache: dict = {}
    cache_file = Path(cache_path) if (use_cache and cache_path is not None) else None
    if cache_file is not None:
        cache = _load_cache(cache_file)

    misses: List[dict] = []
    item_by_key: Dict[str, Optional[dict]] = {}  # rec_key -> VEP item (None=cached fail)
    for rec in records:
        ck = _cache_key(asm, rec)
        if cache_file is not None and ck in cache:
            item_by_key[_rec_key(rec)] = cache[ck]
        else:
            misses.append(rec)

    cache_dirty = False
    if _fetcher is not None and _batch_fetcher is None:
        # Legacy per-variant seam: keep true per-record failure isolation (one bad
        # variant never kills its neighbours), then route results through the same
        # cache + build path as the batch flow.
        for rec in misses:
            try:
                data = _fetcher(host, rec["chrom"], rec["pos"], rec["ref"], rec["alt"], timeout)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
                result.skipped.append(SkippedRecord(rec, f"VEP request failed: {e}"))
                continue
            except Exception as e:  # noqa: BLE001 - defensive: never crash the batch
                result.skipped.append(SkippedRecord(rec, f"VEP error: {e}"))
                continue
            items = data if isinstance(data, list) else [data]
            item = items[0] if items else None
            item_by_key[_rec_key(rec)] = item
            if cache_file is not None:
                cache[_cache_key(asm, rec)] = item
                cache_dirty = True
    else:
        # (1) batch POST the misses, chunked.
        batch_fetch = _batch_fetcher or _vep_batch_fetch
        for start in range(0, len(misses), max(batch_size, 1)):
            chunk = misses[start:start + max(batch_size, 1)]
            try:
                response = batch_fetch(host, chunk, timeout)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
                for rec in chunk:  # whole-chunk failure -> skip just this chunk
                    result.skipped.append(SkippedRecord(rec, f"VEP request failed: {e}"))
                continue
            except Exception as e:  # noqa: BLE001 - defensive: never crash the batch
                for rec in chunk:
                    result.skipped.append(SkippedRecord(rec, f"VEP error: {e}"))
                continue

            indexed = _index_batch_response(response, chunk)
            for rec in chunk:
                item = indexed.get(_rec_key(rec))
                item_by_key[_rec_key(rec)] = item
                if cache_file is not None:
                    cache[_cache_key(asm, rec)] = item  # cache hits + candidate-fails
                    cache_dirty = True

    if cache_file is not None and cache_dirty:
        _save_cache(cache_file, cache)

    # Build Variants (preserving input order); apply candidate + panel filters.
    for rec in records:
        rk = _rec_key(rec)
        if rk not in item_by_key:
            continue  # already recorded as a chunk-failure skip
        variant, reason = _build_variant(rec, item_by_key[rk], cancer_type, asm)
        if variant is None:
            result.skipped.append(SkippedRecord(rec, reason))
            continue
        if panel is not None and (variant.gene or "").upper() not in panel:
            result.skipped.append(SkippedRecord(rec, "outside panel_genes"))
            continue
        result.variants.append(variant)
    return result
