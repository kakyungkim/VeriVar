"""Build the dense-RAG corpus from the CIViC evidence snapshot.

Each CIViC clinical-evidence row becomes one retrievable document whose text is
the human-written ``evidence_statement`` (prefixed with gene/variant/disease for
better retrieval). The document id is the CIViC evidence id, so a dense hit is
directly citable — the same citation contract used by the structured layer.
"""
import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from src.knowledge.civic import DEFAULT_PATH as CIVIC_PATH, _split_profile


@dataclass
class RetrievalDoc:
    id: str                         # e.g. 'CIViC:EID1234'
    text: str                       # embedding/BM25 text
    gene: str = ""
    variant: str = ""
    disease: str = ""
    drugs: str = ""                 # comma-joined (Chroma metadata must be scalar)
    evidence_level: str = ""
    direction: str = ""
    nct_ids: str = ""

    def metadata(self) -> dict:
        return {
            "gene": self.gene, "variant": self.variant, "disease": self.disease,
            "drugs": self.drugs, "evidence_level": self.evidence_level,
            "direction": self.direction, "nct_ids": self.nct_ids,
        }


def build_civic_corpus(path: Path = CIVIC_PATH) -> List[RetrievalDoc]:
    path = Path(path)
    docs: List[RetrievalDoc] = []
    if not path.exists():
        return docs
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            statement = (row.get("evidence_statement") or "").strip()
            if not statement:
                continue
            gene, variant = _split_profile(row.get("molecular_profile", ""))
            disease = row.get("disease", "") or ""
            text = f"{gene} {variant} ({disease}): {statement}".strip()
            docs.append(RetrievalDoc(
                id=f"CIViC:EID{row.get('evidence_id','')}",
                text=text,
                gene=gene, variant=variant, disease=disease,
                drugs=row.get("therapies", "") or "",
                evidence_level=row.get("evidence_level", "") or "",
                direction=row.get("evidence_direction", "") or "",
                nct_ids=row.get("nct_ids", "") or "",
            ))
    return docs
