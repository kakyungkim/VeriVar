"""Dual-mode comparison — the project's headline output.

Computes per-variant agreement between Mode A (LLM) and Mode B (rule) on both
axes, and aggregates discordance overall and per cancer type. Discordances are
the analytical signal (flag-for-review), not errors.
"""
from collections import defaultdict
from typing import Dict, List

from src.models import (
    ClassificationResult, Variant, VariantModeComparison,
)


def compare(variant: Variant, llm: ClassificationResult, rule: ClassificationResult) -> VariantModeComparison:
    return VariantModeComparison(
        variant_key=variant.key,
        cancer_type=variant.cancer_type,
        llm_oncogenicity=llm.oncogenicity,
        rule_oncogenicity=rule.oncogenicity,
        llm_tier=llm.tier,
        rule_tier=rule.tier,
        oncogenicity_concordant=(llm.oncogenicity == rule.oncogenicity),
        tier_concordant=(llm.tier == rule.tier),
    )


def discordance_summary(comparisons: List[VariantModeComparison]) -> Dict:
    """Overall + per-cancer concordance/discordance rates."""
    def _rates(items: List[VariantModeComparison]) -> Dict:
        n = len(items)
        if n == 0:
            return {"n": 0}
        onc_disc = sum(not c.oncogenicity_concordant for c in items)
        tier_disc = sum(not c.tier_concordant for c in items)
        any_disc = sum(c.discordant for c in items)
        return {
            "n": n,
            "oncogenicity_discordant": onc_disc,
            "tier_discordant": tier_disc,
            "any_discordant": any_disc,
            "oncogenicity_concordance_rate": round(1 - onc_disc / n, 3),
            "tier_concordance_rate": round(1 - tier_disc / n, 3),
        }

    by_cancer: Dict[str, List[VariantModeComparison]] = defaultdict(list)
    for c in comparisons:
        by_cancer[c.cancer_type or "Unknown"].append(c)

    return {
        "overall": _rates(comparisons),
        "by_cancer": {k: _rates(v) for k, v in sorted(by_cancer.items())},
        "discordant_variants": [
            {"variant": c.variant_key, "cancer": c.cancer_type,
             "llm": f"{c.llm_oncogenicity.value if c.llm_oncogenicity else '?'}/{c.llm_tier.value if c.llm_tier else '?'}",
             "rule": f"{c.rule_oncogenicity.value if c.rule_oncogenicity else '?'}/{c.rule_tier.value if c.rule_tier else '?'}"}
            for c in comparisons if c.discordant
        ],
    }
