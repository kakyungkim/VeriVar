"""CIViC adapter — clinical evidence, drugs, and trial links for a variant.

Parses the CIViC ClinicalEvidenceSummaries TSV snapshot (see
``scripts/fetch_knowledge.py``). Each evidence row yields a citable
``Evidence`` (id ``CIViC:EID<n>``); the ``evidence_statement`` text doubles as
the dense-RAG corpus unit in Phase 3b.
"""
import csv
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.models import ClinicalTrial, DrugAssociation, Evidence, Modality
from src.knowledge.base import KnowledgeSource, normalize_protein_change

DEFAULT_PATH = Path("data/knowledge/civic/civic_evidence_panel.tsv")


def _split_profile(molecular_profile: str) -> Tuple[str, str]:
    """'BRAF V600E' -> ('BRAF', 'V600E'). Simple single-variant profiles only."""
    parts = (molecular_profile or "").split()
    if not parts:
        return "", ""
    return parts[0].upper(), " ".join(parts[1:]).upper()


class CivicSource(KnowledgeSource):
    name = "CIViC"

    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = Path(path)
        self._index: Dict[Tuple[str, str], List[dict]] = {}
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        with self.path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                gene, variant = _split_profile(row.get("molecular_profile", ""))
                if not gene:
                    continue
                self._index.setdefault((gene, variant), []).append(row)

    def _rows(self, gene: str, protein_change: str) -> List[dict]:
        key = (gene.upper(), normalize_protein_change(protein_change).upper())
        return self._index.get(key, [])

    def evidence(self, gene: str, protein_change: str, cancer_type: Optional[str] = None) -> List[Evidence]:
        out = []
        for row in self._rows(gene, protein_change):
            eid = row.get("evidence_id", "")
            pmids = [row["citation_id"]] if row.get("source_type", "").upper().startswith("PUBMED") and row.get("citation_id") else []
            out.append(Evidence(
                id=f"CIViC:EID{eid}",
                source="CIViC",
                modality=Modality.GENOMIC_SNV_INDEL,
                gene=gene,
                variant=protein_change,
                disease=row.get("disease") or None,
                statement=row.get("evidence_statement", ""),
                evidence_level=row.get("evidence_level") or None,
                direction=row.get("evidence_direction") or None,
                evidence_type=row.get("evidence_type") or None,
                significance=row.get("significance") or None,
                pmids=pmids,
                url=row.get("evidence_civic_url") or None,
            ))
        return out

    def drugs(self, gene: str, protein_change: str, cancer_type: Optional[str] = None) -> List[DrugAssociation]:
        out = []
        for row in self._rows(gene, protein_change):
            therapies = [t.strip() for t in (row.get("therapies") or "").split(",") if t.strip()]
            for drug in therapies:
                out.append(DrugAssociation(
                    drug=drug,
                    source="CIViC",
                    interaction_type=row.get("therapy_interaction_type") or None,
                    evidence_level=row.get("evidence_level") or None,
                    disease=row.get("disease") or None,
                    citations=[f"CIViC:EID{row.get('evidence_id','')}"],
                ))
        return out

    def trials(self, gene: str, protein_change: str, cancer_type: Optional[str] = None) -> List[ClinicalTrial]:
        seen, out = set(), []
        for row in self._rows(gene, protein_change):
            for nct in (row.get("nct_ids") or "").split(","):
                nct = nct.strip()
                if nct and nct not in seen:
                    seen.add(nct)
                    out.append(ClinicalTrial(nct_id=nct, url=f"https://clinicaltrials.gov/study/{nct}"))
        return out
