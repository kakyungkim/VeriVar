"""Evaluation metrics for the dual-mode pipeline.

The headline metrics are LEAKAGE-FREE and need no external ground truth — they
measure the project's actual thesis (faithfulness): does the model cite real
evidence, abstain when it should, and classify in the direction its cited
evidence points? Plus inter-mode agreement (Cohen's kappa). All computable from
a cohort_interpretation.json, so no new LLM calls are required.
"""
from collections import Counter
from typing import Dict, List

_BENIGN_SIG = {"unaltered function", "benign", "likely benign", "neutral"}
_ONCOGENIC_CLASSES = {"Oncogenic", "Likely Oncogenic"}
_BENIGN_CLASSES = {"Benign", "Likely Benign"}


def cohens_kappa(a: List[str], b: List[str]) -> float:
    """Cohen's kappa for two raters over categorical labels."""
    if not a or len(a) != len(b):
        return float("nan")
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    labels = set(a) | set(b)
    pe = sum((ca[l] / n) * (cb[l] / n) for l in labels)
    if pe == 1.0:
        return 1.0
    return round((po - pe) / (1 - pe), 3)


def _bundle_index(row: dict) -> Dict[str, dict]:
    return {e["id"]: e for e in (row.get("bundle") or {}).get("evidences", [])}


def hallucination_rate(variants: List[dict]) -> dict:
    """Fraction of Mode A classifications citing an id NOT in their bundle."""
    n = hall = 0
    examples = []
    for v in variants:
        cites = v["mode_a"].get("citations") or []
        if not cites:
            continue
        n += 1
        valid = set(_bundle_index(v))
        bad = [c for c in cites if c not in valid and c.startswith("CIViC")]
        if bad:
            hall += 1
            examples.append({"variant": v["variant_key"], "fabricated": bad})
    return {"n_with_citations": n, "n_hallucinating": hall,
            "hallucination_rate": round(hall / n, 3) if n else None, "examples": examples[:10]}


def citation_grounding_rate(variants: List[dict]) -> dict:
    """Of non-abstained Mode A calls that HAVE evidence, fraction that cite >=1 id."""
    n = grounded = 0
    for v in variants:
        a = v["mode_a"]
        if a.get("abstained"):
            continue
        if not _bundle_index(v):  # no evidence to cite
            continue
        n += 1
        if a.get("citations"):
            grounded += 1
    return {"n": n, "grounded": grounded,
            "grounding_rate": round(grounded / n, 3) if n else None}


def abstention_metrics(variants: List[dict]) -> dict:
    """Did Mode A abstain exactly when there was no variant-specific evidence?"""
    no_ev_total = no_ev_abstained = has_ev_abstained = has_ev_total = 0
    for v in variants:
        has_ev = bool(_bundle_index(v))
        abst = v["mode_a"].get("abstained")
        if has_ev:
            has_ev_total += 1
            has_ev_abstained += int(bool(abst))
        else:
            no_ev_total += 1
            no_ev_abstained += int(bool(abst))
    return {
        "no_evidence_variants": no_ev_total,
        "abstained_when_no_evidence": no_ev_abstained,
        "abstention_recall": round(no_ev_abstained / no_ev_total, 3) if no_ev_total else None,
        "abstained_despite_evidence": has_ev_abstained,
        "evidence_variants": has_ev_total,
    }


def directional_faithfulness(variants: List[dict]) -> dict:
    """For each Mode A call, do its CITED evidences point the same direction?

    Oncogenic/Likely Oncogenic -> at least one cited CIViC 'Supports' (non-benign)
    or AlphaMissense OP1. Likely Benign/Benign -> cited benign-significance or
    AlphaMissense SBP1. Unfaithful = the call contradicts its own citations.
    """
    checked = faithful = 0
    violations = []
    for v in variants:
        a = v["mode_a"]
        if a.get("abstained"):
            continue
        idx = _bundle_index(v)
        cited = [idx[c] for c in (a.get("citations") or []) if c in idx]
        if not cited:
            continue
        checked += 1
        onc = a["oncogenicity"]
        supports_onc = any(
            (e.get("direction") == "Supports" and (e.get("significance") or "").lower() not in _BENIGN_SIG)
            or (e.get("source") == "AlphaMissense" and (e.get("score") or 0) >= 0.564)
            for e in cited)
        supports_benign = any(
            (e.get("significance") or "").lower() in _BENIGN_SIG
            or (e.get("source") == "AlphaMissense" and 0 < (e.get("score") or 1) <= 0.34)
            for e in cited)
        ok = True
        if onc in _ONCOGENIC_CLASSES and not supports_onc:
            ok = False
        if onc in _BENIGN_CLASSES and not supports_benign:
            ok = False
        if ok:
            faithful += 1
        else:
            violations.append({"variant": v["variant_key"], "call": onc})
    return {"checked": checked, "faithful": faithful,
            "faithfulness_rate": round(faithful / checked, 3) if checked else None,
            "violations": violations[:10]}


def inter_mode_kappa(variants: List[dict]) -> dict:
    onc_a = [v["mode_a"]["oncogenicity"] for v in variants]
    onc_b = [v["mode_b"]["oncogenicity"] for v in variants]
    tier_a = [v["mode_a"]["tier"] for v in variants]
    tier_b = [v["mode_b"]["tier"] for v in variants]
    return {"oncogenicity_kappa": cohens_kappa(onc_a, onc_b),
            "tier_kappa": cohens_kappa(tier_a, tier_b)}


def evaluate(variants: List[dict]) -> dict:
    """Full leakage-free metric suite over a cohort_interpretation 'variants' list."""
    return {
        "n_variants": len(variants),
        "hallucination": hallucination_rate(variants),
        "citation_grounding": citation_grounding_rate(variants),
        "abstention": abstention_metrics(variants),
        "directional_faithfulness": directional_faithfulness(variants),
        "inter_mode_agreement": inter_mode_kappa(variants),
    }
