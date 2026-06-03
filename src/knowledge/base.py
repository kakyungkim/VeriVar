"""KnowledgeSource interface — the contract every structured DB adapter implements.

Each source answers a (gene, protein_change, cancer_type) query with a list of
citable :class:`Evidence` (and optionally drugs/trials). Crucially, a source
returns an EMPTY list when it has nothing — that absence is what lets the
aggregator drive honest abstention (e.g. a pseudogene with no support becomes
VUS instead of being handed fabricated evidence).
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from src.models import ClinicalTrial, DrugAssociation, Evidence


def normalize_protein_change(protein_change: str) -> str:
    """Strip a leading 'p.' so 'p.V600E' and 'V600E' compare equal."""
    pc = (protein_change or "").strip()
    return pc[2:] if pc.startswith("p.") else pc


class KnowledgeSource(ABC):
    """Structured knowledgebase adapter."""

    name: str = "base"

    @abstractmethod
    def evidence(self, gene: str, protein_change: str, cancer_type: Optional[str] = None) -> List[Evidence]:
        """Return citable evidence for the variant (possibly empty)."""

    def drugs(self, gene: str, protein_change: str, cancer_type: Optional[str] = None) -> List[DrugAssociation]:
        return []

    def trials(self, gene: str, protein_change: str, cancer_type: Optional[str] = None) -> List[ClinicalTrial]:
        return []
