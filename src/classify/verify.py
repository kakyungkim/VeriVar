"""Agentic verifier — an adversarial second pass over a Mode A classification.

A separate LLM agent tries to REFUTE the classification using only the evidence,
with a strict bar for actionability (Tier I/II needs direct drug-sensitivity
evidence for THIS variant — gene-level druggability is not enough). This catches
the over-actionability failure mode seen in the first run (passenger variants in
druggable genes drifting to Tier II). ``apply_verdict`` is pure and unit-tested.
"""
import os
from typing import Optional

from pydantic import BaseModel, Field

from src.models import AMPTier, ClassificationResult, EvidenceBundle, Variant
from src.classify.llm import format_evidence
from src.retrieval.graph import GraphContext


class VerifierVerdict(BaseModel):
    supported: bool = Field(description="Is the classification supported by the evidence?")
    reason: str = Field(description="One sentence justification")
    suggested_tier: Optional[AMPTier] = Field(None, description="Corrected tier if not supported")


def apply_verdict(result: ClassificationResult, verdict: VerifierVerdict) -> ClassificationResult:
    """Downgrade/flag a classification the verifier refuted (pure)."""
    if verdict.supported:
        return result
    new_tier = verdict.suggested_tier or AMPTier.TIER_III
    downgraded = new_tier in (AMPTier.TIER_III, AMPTier.TIER_IV)
    return result.model_copy(update={
        "tier": new_tier,
        "tier_level": None if downgraded else result.tier_level,
        "confidence": min(result.confidence if result.confidence is not None else 1.0, 0.5),
        "rationale": f"{result.rationale} [Verifier: {verdict.reason}]",
    })


class Verifier:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def verify(self, variant: Variant, bundle: EvidenceBundle, result: ClassificationResult,
               graph: Optional[GraphContext] = None, temperature: float = 0.0) -> VerifierVerdict:
        from langchain_openai import ChatOpenAI
        system = (
            "You are a careful molecular pathology reviewer. A classification was produced for the variant "
            "below. Using ONLY the provided evidence, decide whether it is SUPPORTED. Default to SUPPORTED; "
            "only refute a CLEAR mismatch.\n"
            "- Actionability (Tier I/II) is supported if there is drug-sensitivity evidence (direction "
            "Supports, significance Sensitivity/Response) for this variant OR for a hotspot/variant group "
            "that includes it. Gene-level druggability ALONE (no sensitivity evidence at all) is NOT enough.\n"
            "- 'Oncogenic'/'Likely Oncogenic' is supported by functional/clinical evidence; it is NOT "
            "supported when the only evidence is 'Unaltered Function' or 'Does Not Support'.\n"
            "If unsupported, give the corrected tier."
        )
        claim = (f"CLASSIFICATION TO REVIEW: oncogenicity={result.oncogenicity.value}, "
                 f"tier={result.tier.value}"
                 + (f" ({result.tier_level.value})" if result.tier_level else ""))
        human = claim + "\n\n" + format_evidence(variant, bundle, graph)
        llm = ChatOpenAI(model=self.model, temperature=temperature).with_structured_output(VerifierVerdict)
        return llm.invoke([("system", system), ("human", human)])
