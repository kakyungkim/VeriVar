"""LLM classifier (Mode A) and rule-explanation (Mode B), citation-grounded.

Mode A: the LLM independently assigns VICC oncogenicity + AMP/ASCO/CAP tier from
the retrieved evidence, citing evidence ids and abstaining when no
variant-specific evidence exists.
Mode B: the deterministic rule result is authoritative; the LLM writes an
explanation only (tier/oncogenicity fixed).

Both modes are constrained to the enum vocabularies via structured output, and
are told to cite ONLY the provided evidence ids — the faithfulness contract.
"""
import os
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models import (
    AMPLevel, AMPTier, ClassificationResult, EvidenceBundle, Variant,
    VICCOncogenicity,
)
from src.retrieval.graph import GraphContext

MODEL = "gpt-4o-mini"


class LLMClassification(BaseModel):
    """Structured-output schema the LLM must fill (Mode A)."""
    oncogenicity: VICCOncogenicity
    tier: AMPTier
    tier_level: Optional[AMPLevel] = None
    rationale: str = Field(description="2-3 sentences, citing evidence ids in brackets")
    citations: List[str] = Field(default_factory=list, description="evidence ids actually used")
    confidence: float = Field(ge=0.0, le=1.0)
    abstained: bool = Field(description="true if evidence was insufficient to classify")


_EVIDENCE_CAP = 30


def _evidence_priority(e, cancer_type: Optional[str]):
    """Rank evidence so the most decision-relevant items survive the cap."""
    score = 0
    if e.source == "CIViC":
        score += 1
    if (e.significance or "").strip().lower() == "sensitivity/response":
        score += 3
    if (e.direction or "").strip() == "Supports":
        score += 1
    if cancer_type and e.disease and any(
            w in e.disease.lower() for w in cancer_type.lower().split() if len(w) > 3):
        score += 2
    return -score


def format_evidence(variant: Variant, bundle: EvidenceBundle,
                    graph: Optional[GraphContext] = None) -> str:
    """Render the evidence bundle as a citable text block for the prompt.

    Includes the structured CIViC fields (type / direction / significance) so the
    model can reason about drug-sensitivity vs resistance vs neutral evidence,
    and caps the list (prioritising sensitivity / matching-cancer items) to keep
    the prompt bounded for highly-curated variants.
    """
    lines = [f"Variant: {variant.gene} {variant.hgvsp} ({variant.variant_type})",
             f"Cancer context: {variant.cancer_type or 'unspecified'}", ""]
    if bundle.evidences:
        ordered = sorted(bundle.evidences, key=lambda e: _evidence_priority(e, variant.cancer_type))
        shown = ordered[:_EVIDENCE_CAP]
        lines.append(f"EVIDENCE ({len(shown)} of {len(bundle.evidences)} shown; cite by id):")
        for e in shown:
            meta = " ".join(filter(None, [
                f"[{e.id}]", f"src={e.source}",
                f"type={e.evidence_type}" if e.evidence_type else "",
                f"dir={e.direction}" if e.direction else "",
                f"sig={e.significance}" if e.significance else "",
                f"level={e.evidence_level}" if e.evidence_level else "",
                f"disease={e.disease}" if e.disease else "",
                f"score={e.score:.3f}" if e.score is not None else "",
            ]))
            lines.append(f"  - {meta}: {e.statement[:240]}")
    else:
        lines.append("EVIDENCE: none retrieved for this variant.")
    if bundle.drugs:
        lines.append("\nASSOCIATED DRUGS: " + ", ".join(
            f"{d.drug}({d.source})" for d in bundle.drugs[:12]))
    if bundle.trials:
        lines.append("TRIALS: " + ", ".join(
            f"{t.nct_id}[{t.status or '?'}]" for t in bundle.trials[:8]))
    if graph and graph.related_variants:
        lines.append("RELATED VARIANTS (shared drug): " + ", ".join(graph.related_variants[:8]))
    return "\n".join(lines)


_VOCAB = (
    "Oncogenicity (ClinGen/CGC/VICC): Oncogenic, Likely Oncogenic, VUS, Likely Benign, Benign.\n"
    "Tier (AMP/ASCO/CAP): Tier I (strong), Tier II (potential), Tier III (unknown), Tier IV (benign). "
    "Tier I/II also take a Level A-D.\n"
)


class LLMClassifier:
    def __init__(self, model: str = MODEL):
        self.model = model
        self._llm = None

    def _client(self, temperature: float):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=self.model, temperature=temperature)

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def classify(self, variant: Variant, bundle: EvidenceBundle,
                 graph: Optional[GraphContext] = None, temperature: float = 0.0) -> ClassificationResult:
        """Mode A — LLM assigns both axes from evidence, grounded + abstaining."""
        system = (
            "You are an expert molecular pathologist classifying a somatic variant on two axes.\n"
            + _VOCAB +
            "Rules: Use ONLY the provided evidence. Cite the evidence ids you used in `citations`. "
            "If there is NO variant-specific evidence, set abstained=true, oncogenicity=VUS, tier=Tier III, "
            "and do not invent therapeutic claims. Tier I requires strong same-tumor-type clinical evidence."
        )
        human = format_evidence(variant, bundle, graph)
        llm = self._client(temperature).with_structured_output(LLMClassification)
        out: LLMClassification = llm.invoke([("system", system), ("human", human)])
        return self._to_result(out)

    def classify_parametric(self, variant: Variant, temperature: float = 0.0) -> ClassificationResult:
        """No-retrieval baseline (ablation): classify from the model's own knowledge.

        No evidence is provided, so the model cannot ground citations — this is
        what isolates the contribution (and faithfulness cost) of the RAG layer.
        """
        system = (
            "You are an expert molecular pathologist. Classify the somatic variant on two axes using your "
            "own knowledge (NO evidence is provided).\n" + _VOCAB +
            "Give your best assessment of oncogenicity and AMP/ASCO/CAP tier for this variant in this cancer."
        )
        human = (f"Variant: {variant.gene} {variant.hgvsp}\n"
                 f"Cancer context: {variant.cancer_type or 'unspecified'}")
        llm = self._client(temperature).with_structured_output(LLMClassification)
        out: LLMClassification = llm.invoke([("system", system), ("human", human)])
        return self._to_result(out)

    def classify_self_consistency(self, variant: Variant, bundle: EvidenceBundle,
                                  graph: Optional[GraphContext] = None, n: int = 3,
                                  temperature: float = 0.4) -> ClassificationResult:
        """Mode A with self-consistency: sample n times, majority-vote per axis.

        The agreement fraction is returned as ``confidence`` — low agreement flags
        a genuinely uncertain variant rather than a falsely-precise single call.
        """
        from src.classify.voting import aggregate_votes
        runs = [self.classify(variant, bundle, graph, temperature=temperature) for _ in range(n)]
        return aggregate_votes(runs)

    def explain_rule(self, variant: Variant, bundle: EvidenceBundle,
                     rule_result: ClassificationResult, graph: Optional[GraphContext] = None,
                     temperature: float = 0.0) -> ClassificationResult:
        """Mode B — tier/oncogenicity fixed by rules; LLM writes the explanation."""
        system = (
            "You are an expert molecular pathologist. A deterministic rule engine has ALREADY assigned the "
            "classification below; it is authoritative and you must NOT change it. Write a 2-3 sentence clinical "
            "explanation grounded in the provided evidence, citing evidence ids. Cite ONLY provided ids."
        )
        fixed = (f"FIXED CLASSIFICATION: oncogenicity={rule_result.oncogenicity.value}, "
                 f"tier={rule_result.tier.value}"
                 + (f" ({rule_result.tier_level.value})" if rule_result.tier_level else ""))
        human = fixed + "\n\n" + format_evidence(variant, bundle, graph)
        from langchain_openai import ChatOpenAI
        llm = self._client(temperature)
        msg = llm.invoke([("system", system), ("human", human)])
        explanation = msg.content if hasattr(msg, "content") else str(msg)
        # Keep the rule's axes; attach the LLM explanation + valid citations.
        valid = set(bundle.citation_ids())
        return ClassificationResult(
            oncogenicity=rule_result.oncogenicity,
            oncogenicity_codes=rule_result.oncogenicity_codes,
            tier=rule_result.tier,
            tier_level=rule_result.tier_level,
            rationale=explanation.strip(),
            citations=[c for c in bundle.citation_ids()],
            confidence=rule_result.confidence,
            abstained=rule_result.abstained,
        )

    def answer_question(self, variant: Variant, bundle: EvidenceBundle, question: str,
                        graph: Optional[GraphContext] = None, temperature: float = 0.0) -> str:
        """Faithfulness-grounded NL answer for the dashboard chat.

        Answers ONLY from the retrieved evidence and refuses (rather than
        speculating) when the evidence does not address the question — the same
        abstention contract the classifier follows.
        """
        system = (
            "You are a precision-oncology assistant answering a question about a somatic variant. "
            "Use ONLY the evidence provided below and cite evidence ids in brackets. If the evidence "
            "does not address the question, reply that you cannot answer from the available evidence — "
            "do NOT speculate or use outside knowledge."
        )
        human = f"Question: {question}\n\n" + format_evidence(variant, bundle, graph)
        msg = self._client(temperature).invoke([("system", system), ("human", human)])
        return msg.content if hasattr(msg, "content") else str(msg)

    @staticmethod
    def _to_result(out: LLMClassification) -> ClassificationResult:
        return ClassificationResult(
            oncogenicity=out.oncogenicity,
            tier=out.tier,
            tier_level=out.tier_level,
            rationale=out.rationale,
            citations=out.citations,
            confidence=out.confidence,
            abstained=out.abstained,
        )
