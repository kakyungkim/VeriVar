"""Single-batch dual-mode interpretation for ad-hoc (bring-your-own) variants.

Research / education / demo only — **NOT for clinical use**.

This is the entry point the bring-your-own-VCF feature calls. It reuses the exact
same machinery as ``src/pipeline.py`` (offline evidence aggregator, the
direction-aware deterministic rule arm, the optional Generative/LLM mode, the
knowledge graph, and the deterministic faithfulness gate) so a user-supplied
:class:`~src.models.Variant` list is interpreted identically to a cohort variant
and the per-variant output matches ``cohort_interpretation.json``'s
``variants[i]`` shape — letting the dashboard render it unchanged.

Faithfulness contract (unchanged): each LLM call may cite only retrieved
evidence ids and a variant with no variant-specific evidence abstains (VUS).
Mode B (deterministic rule) always runs; Mode A (Generative/LLM) runs only when
``use_llm=True`` AND an API key is present — otherwise it is a clear "not run"
marker and **zero** external API calls are made.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from src.models import EvidenceBundle, Variant
from src.knowledge.factory import build_aggregator
from src.knowledge.aggregator import EvidenceAggregator
from src.classify.rules import RuleClassifier
from src.classify.llm import LLMClassifier
from src.classify.faithfulness import enforce_faithfulness
from src.compare.dualmode import compare
from src.retrieval.graph import KnowledgeGraph

logger = logging.getLogger(__name__)

# Mode A "not run" placeholder when use_llm=False (or no API key). Mirrors the
# ClassificationResult json shape so the frontend can treat it uniformly.
MODE_A_NOT_RUN = {
    "oncogenicity": "—",
    "oncogenicity_codes": [],
    "tier": "—",
    "tier_level": None,
    "rationale": "Generative mode not run (offline)",
    "citations": [],
    "confidence": None,
    "abstained": True,
}


def _evidence_tier(bundle: EvidenceBundle) -> str:
    """Same tiering as ``src/classify/select.py``."""
    if any(e.source == "CIViC" for e in bundle.evidences):
        return "civic"
    if any(e.source == "AlphaMissense" for e in bundle.evidences):
        return "alphamissense"
    return "none"


def _related_cancers(bundle: EvidenceBundle) -> List[str]:
    """Deduped, sorted disease/condition strings mentioned anywhere in a bundle.

    Lets the UI surface "related cancers" even when the user did not pick a
    cancer type. Sources, in order of pooling: every ``Evidence.disease``, every
    ``DrugAssociation.disease``, and each ``ClinicalTrial.conditions`` entry.
    Blank/whitespace-only values are dropped; comparison is case-insensitive on
    the stripped string while preserving the first-seen casing.
    """
    seen: dict[str, str] = {}
    pools: List[Optional[str]] = []
    pools += [e.disease for e in bundle.evidences]
    pools += [d.disease for d in bundle.drugs]
    for t in bundle.trials:
        pools += list(t.conditions)
    for raw in pools:
        if not raw:
            continue
        s = raw.strip()
        if not s:
            continue
        key = s.lower()
        seen.setdefault(key, s)
    return sorted(seen.values(), key=str.lower)


def get_default_retriever(am_online: bool = False):
    """Return the full HybridEvidenceRetriever (structured + dense + graph).

    Thin re-export of :func:`src.pipeline.build_retriever` so the dashboard can
    build the retriever ONCE behind ``st.cache_resource`` and pass it to
    :func:`interpret_variants`. First call loads the persistent dense index and
    the sentence-transformer embedder (the only cost); subsequent calls reuse it.
    Returns ``None`` is never used — failures propagate so the caller can decide
    whether to degrade to the offline aggregator.

    ``am_online=True`` builds the retriever with a LIVE AlphaMissense annotator
    (Ensembl VEP REST) while CIViC/DGIdb/trials stay offline — use this for the
    bring-your-own-VCF upload path so GRCh38 missense variants get AlphaMissense
    evidence. Leave ``False`` (default) for the offline/cohort path.
    """
    from src.pipeline import build_retriever
    return build_retriever(am_online=am_online)


def interpret_variants(
    variants: List[Variant],
    use_llm: bool = False,
    retriever=None,
    aggregator: Optional[EvidenceAggregator] = None,
    graph: Optional[KnowledgeGraph] = None,
    am_online: bool = False,
) -> List[dict]:
    """Interpret a list of variants in dual mode; return cohort-shaped dicts.

    For each variant:

    1. Build the evidence bundle. If a ``retriever`` (the cohort's
       :class:`~src.retrieval.orchestrator.HybridEvidenceRetriever`) is supplied
       — or if one can be built lazily — use ``retriever.retrieve(v)`` so the
       bundle carries the SAME rich structured+dense+graph evidence and clinical
       trials the cohort gets (e.g. BRAF V600E picks up its many NCT trials).
       Falls back to the offline structured ``aggregator`` (exact-match only)
       when no retriever / dense index is available; the path used is logged.
    2. Run the deterministic / VICC **rule arm** (Mode B) — always. Works with
       ``v.cancer_type=None`` (oncogenicity still runs; tiering is context-free).
    3. Run the **Generative / LLM arm** (Mode A) only if ``use_llm=True`` and an
       ``OPENAI_API_KEY`` is set; otherwise Mode A is :data:`MODE_A_NOT_RUN` and
       no external API call is made.
    4. Apply the deterministic faithfulness gate to Mode A (drops fabricated
       citations, forces abstention when unsupported). Variants with no
       retrievable variant-specific evidence abstain (VUS) — correct behavior.

    Returns one dict per variant with the SAME keys as
    ``cohort_interpretation.json`` ``variants[i]``: ``variant_key``, ``gene``,
    ``hgvsp``, ``cancer_type``, ``variant_type``, ``evidence_tier``,
    ``sample_ids``, ``n_evidence``, ``n_drugs``, ``n_trials``, ``mode_a``,
    ``mode_b``, ``discordant``, ``bundle``, ``related_variants`` — PLUS one new
    key, ``related_cancers`` (sorted unique disease/condition strings drawn from
    the bundle, so the UI can show context even when no cancer type was picked).
    When Mode A was not run, ``discordant`` is ``None``.

    Args:
        retriever: optional HybridEvidenceRetriever (preferred — rich bundles).
            ``None`` keeps the offline aggregator path (no dense index needed).
        aggregator / graph: explicit offline overrides (mainly for tests).
        am_online: when ``True`` (and no explicit ``aggregator`` is passed),
            the offline fallback aggregator is built with a LIVE AlphaMissense
            annotator (Ensembl VEP REST) so GRCh38 missense uploads get
            AlphaMissense evidence the committed GRCh37 cache cannot supply;
            CIViC/DGIdb/trials stay offline. Only affects the fallback path —
            for the rich path the caller should build the ``retriever`` with the
            matching ``am_online`` (see :func:`get_default_retriever`). Default
            ``False`` keeps the cohort/offline behavior unchanged.

    Network: VEP is upstream (annotation, in :mod:`src.cohort.vcf_loader`).
    OpenAI is called here ONLY when ``use_llm=True`` and a key is present.
    """
    agg = aggregator or build_aggregator(offline=True, am_online=am_online)
    rule_clf = RuleClassifier()
    kg = graph if graph is not None else KnowledgeGraph.from_civic()

    live = use_llm and LLMClassifier.available()
    llm = LLMClassifier() if live else None

    use_retriever = retriever is not None
    if use_retriever:
        logger.info("interpret_variants: using HybridEvidenceRetriever (rich bundles)")
    else:
        logger.info("interpret_variants: using offline aggregator (exact-match bundles)")

    rows: List[dict] = []
    for v in variants:
        if use_retriever:
            try:
                retrieved = retriever.retrieve(v)
                bundle, ctx = retrieved.bundle, retrieved.graph
            except Exception as e:  # noqa: BLE001 - degrade if dense index missing
                logger.warning("retriever.retrieve failed for %s (%s); "
                               "falling back to offline aggregator", v.key, e)
                bundle = agg.for_variant_obj(v)
                ctx = kg.context(v.gene, v.hgvsp) if kg else None
        else:
            bundle = agg.for_variant_obj(v)
            ctx = kg.context(v.gene, v.hgvsp) if kg else None
        rule = rule_clf.classify(v, bundle)

        if live:
            mode_a_result = llm.classify(v, bundle, ctx)
            mode_b_result = llm.explain_rule(v, bundle, rule, ctx)
            mode_a = mode_a_result.model_dump(mode="json")
            mode_b = mode_b_result.model_dump(mode="json")
            discordant = compare(v, mode_a_result, mode_b_result).discordant
        else:
            # Offline: only the deterministic arm is real. Mode A is a marker.
            mode_a = dict(MODE_A_NOT_RUN)
            mode_b = rule.model_dump(mode="json")
            discordant = None

        row = {
            "variant_key": v.key,
            "gene": v.gene,
            "hgvsp": v.hgvsp,
            "cancer_type": v.cancer_type,
            "variant_type": v.variant_type,
            "evidence_tier": _evidence_tier(bundle),
            "sample_ids": [v.sample_id] if v.sample_id else [],
            "n_evidence": len(bundle.evidences),
            "n_drugs": len(bundle.drugs),
            "n_trials": len(bundle.trials),
            "mode_a": mode_a,
            "mode_b": mode_b,
            "discordant": discordant,
            "bundle": bundle.model_dump(mode="json"),
            "related_variants": ctx.related_variants[:8] if ctx else [],
            "related_cancers": _related_cancers(bundle),
        }
        # Faithfulness gate only meaningfully applies to a real Mode-A call; the
        # "not run" marker is already abstained, so the gate is a safe no-op.
        if live:
            row = enforce_faithfulness(row)
        rows.append(row)
    return rows
