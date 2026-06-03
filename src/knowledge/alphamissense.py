"""AlphaMissense computational evidence via the Ensembl VEP REST API.

For each missense SNV this fetches the AlphaMissense pathogenicity score/class
(GRCh37, matching the cBioPortal TCGA coordinates) and emits a citable
:class:`Evidence`. This is the VICC-mandated *computational* evidence line — the
classifier maps it to code OP1 (supporting oncogenic) or SBP1 (supporting
benign). Results are cached to disk for offline reproducibility.

Per Cheng et al. 2023, the suggested thresholds are: pathogenic >= 0.564,
benign <= 0.34, ambiguous in between.
"""
import json
import urllib.request
from pathlib import Path
from typing import List, Optional

from src.models import Evidence, Modality, Variant

VEP_GRCH37 = "https://grch37.rest.ensembl.org/vep/human/region/{chrom}:{pos}-{pos}/{alt}?AlphaMissense=1&content-type=application/json"
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

    def _lookup(self, v: Variant) -> Optional[dict]:
        key = f"{v.chrom}:{v.pos}:{v.ref}>{v.alt}"
        if key in self._cache:
            return self._cache[key]
        if self.offline:
            return None
        url = VEP_GRCH37.format(chrom=v.chrom, pos=v.pos, alt=v.alt)
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
        self._cache[key] = best  # cache misses (None) too, to avoid refetching
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
