"""End-to-end dual-mode interpretation pipeline (Phase 4 integration).

Loads the cohort -> selects variants -> retrieves evidence -> classifies each in
both modes (A: LLM, B: rule + LLM explanation) -> computes dual-mode discordance
-> writes a report-friendly JSON + CSV with provenance.

Run:  python -m src.pipeline [--limit N]
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from src.cohort.loader import load_cohort
from src.knowledge.factory import build_aggregator
from src.classify.select import select_for_classification, SelectedVariant
from src.classify.rules import RuleClassifier
from src.classify.llm import LLMClassifier
from src.classify.verify import Verifier, apply_verdict
from src.retrieval.graph import KnowledgeGraph
from src.compare.dualmode import compare, discordance_summary
from src.provenance import build_provenance

OUT_DIR = Path("data/outputs")
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _retry(fn, attempts: int = 2):
    last = None
    for _ in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - transient API errors
            last = e
    raise last


def build_retriever(agg=None, kg=None, am_online: bool = False):
    """Build the full HybridEvidenceRetriever (structured + dense + graph).

    This is the SAME retriever the cohort pipeline uses, so callers (the cohort
    loop here and the bring-your-own-VCF path in :mod:`src.interpret`) attach the
    identical rich evidence — full CIViC statements and the clinical trials that
    ride on the NCT ids carried by retrieved CIViC evidence.

    ``agg``/``kg`` default to the committed offline aggregator and the CIViC
    knowledge graph. Loading the persistent dense index
    (``data/knowledge/chroma_index``) + the sentence-transformer embedder is the
    first-call cost; cache the returned object (e.g. ``st.cache_resource``).

    ``am_online`` (only used when ``agg`` is not supplied) builds the default
    aggregator with a LIVE AlphaMissense annotator (Ensembl VEP REST) while
    keeping CIViC/DGIdb/trials offline — for the online VCF-upload path so
    GRCh38 missense variants get AlphaMissense scores the committed
    GRCh37-keyed cache cannot supply. The cohort pipeline leaves this ``False``.
    """
    from src.retrieval import build_civic_corpus, HybridRetriever, SentenceTransformerEmbedder
    from src.retrieval.orchestrator import HybridEvidenceRetriever
    agg = agg or build_aggregator(offline=True, am_online=am_online)
    kg = kg if kg is not None else KnowledgeGraph.from_civic()
    docs = build_civic_corpus()
    dense = HybridRetriever(docs, embedder=SentenceTransformerEmbedder(),
                            persist_path="data/knowledge/chroma_index")
    return HybridEvidenceRetriever(agg, dense=dense, graph=kg)


# Backwards-compatible alias (kept for the cohort run() call below).
def _dense_orchestrator(agg, kg):
    """Hybrid retriever with the persistent dense index (structured + dense + graph)."""
    return build_retriever(agg=agg, kg=kg)


def run(limit: Optional[int] = None, timestamp: str = "",
        vote: bool = False, verify: bool = False, n_votes: int = 3, dense: bool = False,
        out_basename: str = "cohort_interpretation") -> dict:
    load_dotenv(ENV_PATH, override=True)
    variants = load_cohort()
    agg = build_aggregator(offline=True)
    selected: List[SelectedVariant] = select_for_classification(agg, variants)
    if limit:
        selected = selected[:limit]

    kg = KnowledgeGraph.from_civic()
    rule_clf = RuleClassifier()
    llm = LLMClassifier()
    verifier = Verifier()
    live = llm.available()
    orchestrator = _dense_orchestrator(agg, kg) if dense else None
    techniques = [t for t, on in [("dense-RAG", dense), (f"self-consistency(n={n_votes})", vote),
                                  ("agentic-verifier", verify)] if on]
    print(f"[*] {len(selected)} variants to classify (LLM {'live' if live else 'UNAVAILABLE'})"
          + (f" · {', '.join(techniques)}" if techniques else ""))

    rows, comparisons = [], []
    for i, s in enumerate(selected, 1):
        v = s.variant
        if orchestrator is not None:
            retrieved = orchestrator.retrieve(v)
            bundle, graph = retrieved.bundle, retrieved.graph
        else:
            bundle, graph = s.bundle, kg.context(v.gene, v.hgvsp)
        rule = rule_clf.classify(v, bundle)
        if live:
            if vote:
                mode_a = _retry(lambda: llm.classify_self_consistency(v, bundle, graph, n=n_votes))
            else:
                mode_a = _retry(lambda: llm.classify(v, bundle, graph))
            # Verify only non-abstained calls — an abstained VUS isn't an over-claim.
            if verify and not mode_a.abstained:
                verdict = _retry(lambda: verifier.verify(v, bundle, mode_a, graph))
                mode_a = apply_verdict(mode_a, verdict)
            mode_b = _retry(lambda: llm.explain_rule(v, bundle, rule, graph))
        else:
            mode_a, mode_b = rule, rule  # offline fallback: both = rule
        cmp = compare(v, mode_a, mode_b)
        comparisons.append(cmp)
        rows.append({
            "variant_key": v.key, "gene": v.gene, "hgvsp": v.hgvsp,
            "cancer_type": v.cancer_type, "variant_type": v.variant_type,
            "evidence_tier": s.tier, "sample_ids": s.sample_ids,
            "n_evidence": len(bundle.evidences), "n_drugs": len(bundle.drugs),
            "n_trials": len(bundle.trials),
            "mode_a": mode_a.model_dump(mode="json"),
            "mode_b": mode_b.model_dump(mode="json"),
            "discordant": cmp.discordant,
            # Persist the exact evidence used so the dashboard chat grounds on the
            # same bundle the classification saw (no lossy re-retrieval).
            "bundle": bundle.model_dump(mode="json"),
            "related_variants": graph.related_variants[:8] if graph else [],
        })
        if i % 10 == 0 or i == len(selected):
            print(f"    {i}/{len(selected)} done")

    summary = discordance_summary(comparisons)
    provenance = build_provenance(
        live=live,
        model_name=llm.model if live else None,
        data_sources={
            "cohort": "cBioPortal REST (TCGA PanCancer Atlas)",
            "civic": "CIViC nightly", "dgidb": "DGIdb",
            "alphamissense": "Ensembl VEP REST", "trials": "ClinicalTrials.gov v2",
        },
        timestamp=timestamp,
        n_variants=len(selected),
        techniques=techniques or ["single-pass"],
        n_votes=n_votes if vote else None,
        retrieval_index=orchestrator.index_fingerprint() if orchestrator is not None else None,
    )
    output = {
        "provenance": provenance.model_dump(mode="json"),
        "discordance_summary": summary,
        "variants": rows,
    }
    _write(output, out_basename)
    print(f"[+] overall tier concordance: {summary['overall'].get('tier_concordance_rate')}, "
          f"oncogenicity: {summary['overall'].get('oncogenicity_concordance_rate')}")
    return output


def _write(output: dict, basename: str = "cohort_interpretation") -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{basename}.json").write_text(json.dumps(output, indent=2))
    with (OUT_DIR / f"{basename}.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "cancer_type", "evidence_tier",
                    "modeA_oncogenicity", "modeA_tier", "modeB_oncogenicity", "modeB_tier", "discordant"])
        for r in output["variants"]:
            a, b = r["mode_a"], r["mode_b"]
            w.writerow([r["variant_key"], r["cancer_type"], r["evidence_tier"],
                        a["oncogenicity"], a["tier"], b["oncogenicity"], b["tier"], r["discordant"]])
    print(f"[+] wrote {OUT_DIR}/{basename}.json + .csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="classify only the first N variants")
    ap.add_argument("--vote", action="store_true", help="Mode A self-consistency voting")
    ap.add_argument("--verify", action="store_true", help="agentic verifier on Mode A")
    ap.add_argument("--dense", action="store_true", help="add dense-RAG arm (needs scripts.build_index)")
    ap.add_argument("--n-votes", type=int, default=3, help="samples per variant when --vote")
    ap.add_argument("--out", default="cohort_interpretation", help="output basename")
    args = ap.parse_args()
    run(limit=args.limit, vote=args.vote, verify=args.verify, n_votes=args.n_votes, dense=args.dense,
        out_basename=args.out, timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
