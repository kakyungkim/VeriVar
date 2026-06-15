"""AlphaMissense computational evidence via the Ensembl VEP REST API.

For each missense SNV this fetches the AlphaMissense pathogenicity score/class
via the Ensembl VEP REST API and emits a citable :class:`Evidence`. The lookup
is **build-aware**: the VEP mirror is chosen by ``Variant.assembly`` (GRCh37 ->
grch37 mirror, matching the cBioPortal TCGA coordinates; GRCh38 ->
rest.ensembl.org). AlphaMissense is a protein-level predictor, so no liftover is
needed — only the build-appropriate coordinate query. This is the VICC-mandated
*computational* evidence line — the classifier maps it to code OP1 (supporting
oncogenic) or SBP1 (supporting benign). Results are cached to disk (keyed by
``assembly|chrom:pos:ref>alt``, with a read-only legacy bare-key fallback for the
committed GRCh37 cache) for offline reproducibility.

Per Cheng et al. 2023, the suggested thresholds are: pathogenic >= 0.564,
benign <= 0.34, ambiguous in between.
"""
import json
import urllib.request
from pathlib import Path
from typing import List, Optional

from src.models import Evidence, Modality, Variant

# AlphaMissense is a *protein-level* predictor, but the Ensembl VEP REST lookup
# is coordinate-based, so the mirror MUST match the variant's genome build (no
# liftover is needed — we just query the build-appropriate REST host). GRCh37 ->
# the grch37 mirror (matches the cBioPortal TCGA coordinates); GRCh38 -> the
# default rest.ensembl.org host.
VEP_GRCH37 = "https://grch37.rest.ensembl.org/vep/human/region/{chrom}:{pos}-{pos}/{alt}?AlphaMissense=1&content-type=application/json"
VEP_GRCH38 = "https://rest.ensembl.org/vep/human/region/{chrom}:{pos}-{pos}/{alt}?AlphaMissense=1&content-type=application/json"
VEP_MIRRORS = {"GRCH37": VEP_GRCH37, "GRCH38": VEP_GRCH38}
DEFAULT_CACHE = Path("data/knowledge/alphamissense/vep_cache.json")

PATHOGENIC_T = 0.564
BENIGN_T = 0.34


def vicc_code(am_pathogenicity: float) -> Optional[str]:
    """Map an AlphaMissense score to a VICC computational evidence code."""
    if am_pathogenicity >= PATHOGENIC_T:
        return "OP1"   # computational evidence supports oncogenic impact
    if am_pathogenicity <= BENIGN_T:
        return "SBP1"  # computational evidence supports benign / no impact
    return None        # ambiguous -> no code


class AlphaMissenseAnnotator:
    name = "AlphaMissense"

    def __init__(self, cache_path: Path = DEFAULT_CACHE, offline: bool = True):
        self.cache_path = Path(cache_path)
        self.offline = offline
        self._cache = json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}

    @staticmethod
    def _is_missense_snv(v: Variant) -> bool:
        return v.variant_type == "SNV" and len(v.ref) == 1 and len(v.alt) == 1 and v.ref != "-" and v.alt != "-"

    @staticmethod
    def _bare_key(v: Variant) -> str:
        """Legacy assembly-agnostic cache key (``chrom:pos:ref>alt``).

        Retained for backward-compatible GRCh37 lookups against the committed
        cache, which was written before keys carried an assembly prefix.
        """
        return f"{v.chrom}:{v.pos}:{v.ref}>{v.alt}"

    @staticmethod
    def _assembly_key(v: Variant) -> str:
        """Assembly-aware cache key (``GRCh37|chrom:pos:ref>alt``).

        Coordinates mean different residues across builds, so GRCh37 and GRCh38
        results MUST NOT share a key. New entries are written under this key.
        """
        asm = (getattr(v, "assembly", None) or "GRCh37")
        return f"{asm}|{v.chrom}:{v.pos}:{v.ref}>{v.alt}"

    def _lookup(self, v: Variant) -> Optional[dict]:
        asm = (getattr(v, "assembly", None) or "GRCh37")
        asm_key = self._assembly_key(v)
        # Prefer the assembly-prefixed key; for GRCh37 fall back to the legacy
        # bare key so the committed 417-entry GRCh37 cache still hits.
        if asm_key in self._cache:
            return self._cache[asm_key]
        if asm.upper() == "GRCH37":
            bare = self._bare_key(v)
            if bare in self._cache:
                return self._cache[bare]
        if self.offline:
            return None
        mirror = VEP_MIRRORS.get(asm.upper(), VEP_GRCH37)
        url = mirror.format(chrom=v.chrom, pos=v.pos, alt=v.alt)
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
        except Exception:
            return None
        best = None
        for rec in (data if isinstance(data, list) else [data]):
            for tc in rec.get("transcript_consequences", []):
                am = tc.get("alphamissense")
                if am and "am_pathogenicity" in am:
                    score = am["am_pathogenicity"]
                    if best is None or score > best["am_pathogenicity"]:
                        best = {"am_pathogenicity": score, "am_class": am.get("am_class")}
        # Write new entries under the assembly-prefixed key (cache misses too, to
        # avoid refetching); the legacy bare key is read-only.
        self._cache[asm_key] = best
        self._save()
        return best

    def evidence_for_variant(self, v: Variant) -> List[Evidence]:
        if not self._is_missense_snv(v):
            return []
        am = self._lookup(v)
        if not am:
            return []
        score, cls = am["am_pathogenicity"], am.get("am_class", "")
        code = vicc_code(score)
        return [Evidence(
            id=f"AlphaMissense:{v.chrom}:{v.pos}{v.ref}>{v.alt}",
            source="AlphaMissense",
            modality=Modality.GENOMIC_SNV_INDEL,
            gene=v.gene,
            variant=v.hgvsp,
            statement=(f"AlphaMissense predicts {v.gene} {v.hgvsp} as {cls} "
                       f"(pathogenicity={score:.3f}); computational evidence "
                       f"{'(' + code + ')' if code else '(ambiguous)'}."),
            evidence_level=cls or None,
            score=score,
        )]

    def _save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, indent=2))
