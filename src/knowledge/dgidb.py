"""DGIdb adapter — gene-level drug-gene interactions.

Reads a snapshot ``{gene: [interactions]}`` produced by
``scripts/fetch_knowledge.py``. DGIdb is gene-level (not variant-specific), so
drugs are returned for the gene regardless of protein change.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional

from src.models import DrugAssociation, Evidence
from src.knowledge.base import KnowledgeSource

DEFAULT_PATH = Path("data/knowledge/dgidb/dgidb_panel.json")
# Only surface reasonably confident interactions to limit noise.
MIN_SCORE = 0.0
MAX_DRUGS_PER_GENE = 15


class DgidbSource(KnowledgeSource):
    name = "DGIdb"

    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = Path(path)
        self._by_gene: Dict[str, list] = {}
        if self.path.exists():
            self._by_gene = {k.upper(): v for k, v in json.loads(self.path.read_text()).items()}

    def evidence(self, gene: str, protein_change: str, cancer_type: Optional[str] = None) -> List[Evidence]:
        # DGIdb contributes drugs, not standalone oncogenicity evidence statements.
        return []

    def drugs(self, gene: str, protein_change: str, cancer_type: Optional[str] = None) -> List[DrugAssociation]:
        interactions = self._by_gene.get(gene.upper(), [])
        ranked = sorted(interactions, key=lambda i: -(i.get("score") or 0.0))
        out = []
        for i in ranked[:MAX_DRUGS_PER_GENE]:
            if (i.get("score") or 0.0) < MIN_SCORE:
                continue
            itypes = ", ".join(i.get("interaction_types", [])) or None
            out.append(DrugAssociation(
                drug=i.get("drug", ""),
                source="DGIdb",
                interaction_type=itypes,
                citations=[f"DGIdb:{s}" for s in i.get("sources", [])][:5],
            ))
        return out
