"""GraphRAG: a knowledge graph over CIViC for multi-hop retrieval.

Dense/structured retrieval answers "what is known about THIS variant". The graph
adds relational context a flat lookup misses — e.g. "what other variants does
this variant's drug also target" (variant -> evidence -> drug -> evidence ->
variant) — which is useful for resistance/cross-actionability reasoning.

Nodes: gene, variant, disease, drug, evidence (CIViC EID), trial (NCT).
Built from the same RetrievalDoc corpus used by the dense index, so evidence
nodes keep their citable ids.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.retrieval.corpus import RetrievalDoc, build_civic_corpus
from src.knowledge.base import normalize_protein_change


def _vid(gene: str, variant: str) -> str:
    return f"variant:{gene.upper()} {normalize_protein_change(variant).upper()}"


@dataclass
class GraphContext:
    variant_key: str
    evidence_ids: List[str] = field(default_factory=list)
    drugs: List[str] = field(default_factory=list)
    diseases: List[str] = field(default_factory=list)
    trials: List[str] = field(default_factory=list)
    related_variants: List[str] = field(default_factory=list)  # share a drug (multi-hop)


class KnowledgeGraph:
    def __init__(self):
        import networkx as nx
        self.g = nx.MultiDiGraph()

    @classmethod
    def from_corpus(cls, docs: List[RetrievalDoc]) -> "KnowledgeGraph":
        kg = cls()
        for d in docs:
            kg._add_doc(d)
        return kg

    @classmethod
    def from_civic(cls) -> "KnowledgeGraph":
        return cls.from_corpus(build_civic_corpus())

    def _add_doc(self, d: RetrievalDoc) -> None:
        g = self.g
        vnode = _vid(d.gene, d.variant)
        gnode = f"gene:{d.gene.upper()}"
        enode = f"evidence:{d.id}"
        g.add_node(vnode, type="variant", gene=d.gene, variant=d.variant)
        g.add_node(gnode, type="gene")
        g.add_node(enode, type="evidence", id=d.id)
        g.add_edge(vnode, gnode, rel="in_gene")
        g.add_edge(vnode, enode, rel="has_evidence")
        if d.disease:
            dn = f"disease:{d.disease}"
            g.add_node(dn, type="disease")
            g.add_edge(enode, dn, rel="in_disease")
        for drug in [x.strip() for x in d.drugs.split(",") if x.strip()]:
            dr = f"drug:{drug}"
            g.add_node(dr, type="drug")
            g.add_edge(enode, dr, rel="recommends")
        for nct in [x.strip() for x in d.nct_ids.split(",") if x.strip()]:
            tn = f"trial:{nct}"
            g.add_node(tn, type="trial")
            g.add_edge(enode, tn, rel="trial")

    def context(self, gene: str, protein_change: str) -> GraphContext:
        g = self.g
        vnode = _vid(gene, protein_change)
        ctx = GraphContext(variant_key=f"{gene} {protein_change}".strip())
        if vnode not in g:
            return ctx

        evidence_nodes = [n for n in g.successors(vnode)
                          if g.nodes[n].get("type") == "evidence"]
        drugs, diseases, trials = set(), set(), set()
        for en in evidence_nodes:
            ctx.evidence_ids.append(g.nodes[en]["id"])
            for nbr in g.successors(en):
                t = g.nodes[nbr].get("type")
                if t == "drug":
                    drugs.add(nbr.split("drug:", 1)[1])
                elif t == "disease":
                    diseases.add(nbr.split("disease:", 1)[1])
                elif t == "trial":
                    trials.add(nbr.split("trial:", 1)[1])

        # Multi-hop: variants that share one of this variant's drugs.
        related = set()
        for en in evidence_nodes:
            for drug_node in [n for n in g.successors(en) if g.nodes[n].get("type") == "drug"]:
                for other_ev in g.predecessors(drug_node):
                    for v in g.predecessors(other_ev):
                        if g.nodes[v].get("type") == "variant" and v != vnode:
                            related.add(v.split("variant:", 1)[1])

        ctx.drugs = sorted(drugs)
        ctx.diseases = sorted(diseases)
        ctx.trials = sorted(trials)
        ctx.related_variants = sorted(related)
        return ctx
