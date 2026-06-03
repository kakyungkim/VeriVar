"""Typed error analysis of Mode A (LLM) vs Mode B (rule) discordances.

Deterministic categorisation of every disagreement into interpretable buckets so
the blog/paper can say *why* the modes differ, not just *how often*. No LLM calls.
"""
from collections import Counter, defaultdict
from typing import Dict, List

_ONCO_ORDER = {"Benign": 0, "Likely Benign": 1, "VUS": 2, "Likely Oncogenic": 3, "Oncogenic": 4}
_TIER_ORDER = {"Tier IV": 0, "Tier III": 1, "Tier II": 2, "Tier I": 3}
_NOT_ONCO = {"VUS", "Likely Benign", "Benign"}
_ONCO = {"Oncogenic", "Likely Oncogenic"}


def _category(v: dict) -> str:
    a, b = v["mode_a"], v["mode_b"]
    onc_a, onc_b = a["oncogenicity"], b["oncogenicity"]
    tier_a, tier_b = a["tier"], b["tier"]
    verifier = "[Verifier:" in (a.get("rationale") or "")

    if onc_b in _ONCO and onc_a in _NOT_ONCO:
        # Rule calls it a driver; LLM reads the evidence and does not. The headline
        # "beyond rules" case (and the verifier often drove the LLM here).
        return "rule_overcall_corrected_by_llm"
    if onc_a in _ONCO and onc_b in _NOT_ONCO:
        return "llm_overcall_vs_rule"
    if verifier and tier_a != tier_b:
        return "verifier_tier_downgrade"
    if onc_a != onc_b and onc_a in _ONCO and onc_b in _ONCO:
        return "oncogenic_confidence"          # Oncogenic vs Likely Oncogenic
    if onc_a != onc_b and onc_a in _NOT_ONCO and onc_b in _NOT_ONCO:
        return "benign_label"                  # VUS vs Likely Benign (both not a driver)
    if onc_a == onc_b and tier_a != tier_b:
        return "tier_boundary"                 # same oncogenicity, different tier
    return "other"


def analyze(variants: List[dict]) -> dict:
    discordant = [v for v in variants if v.get("discordant")]
    cats: Dict[str, List[dict]] = defaultdict(list)
    cancer_cat = defaultdict(Counter)
    adjacent = gross = 0

    for v in discordant:
        cat = _category(v)
        a, b = v["mode_a"], v["mode_b"]
        onc_d = _ONCO_ORDER.get(a["oncogenicity"], 0) - _ONCO_ORDER.get(b["oncogenicity"], 0)
        tier_d = _TIER_ORDER.get(a["tier"], 0) - _TIER_ORDER.get(b["tier"], 0)
        if max(abs(onc_d), abs(tier_d)) <= 1:
            adjacent += 1
        else:
            gross += 1
        cats[cat].append({
            "variant": v["variant_key"], "cancer": v["cancer_type"],
            "mode_a": f"{a['oncogenicity']}/{a['tier']}",
            "mode_b": f"{b['oncogenicity']}/{b['tier']}",
            "llm_more_conservative": (onc_d < 0 or tier_d < 0),
            "confidence": a.get("confidence"),
        })
        cancer_cat[v["cancer_type"]][cat] += 1

    n = len(discordant)
    return {
        "n_total": len(variants),
        "n_discordant": n,
        "adjacent": adjacent,
        "gross": gross,
        "category_counts": {k: len(v) for k, v in sorted(cats.items(), key=lambda kv: -len(kv[1]))},
        "llm_more_conservative": sum(1 for vs in cats.values() for x in vs if x["llm_more_conservative"]),
        "by_cancer": {k: dict(c) for k, c in cancer_cat.items()},
        "categories": dict(cats),
    }
