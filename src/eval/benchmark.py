"""External tier-accuracy check against CIViC Assertions (expert gold standard).

Small and class-skewed (mostly Tier I), and shares the CIViC evidence corpus
(leakage) — so it is a secondary sanity check, reported with caveats. A larger,
leakage-controlled benchmark (e.g. ClinGen/CGC/VICC + temporal split) is future
work.
"""
import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_PATH = Path("data/benchmark/civic_assertions.tsv")
_TIER_RE = re.compile(r"Tier (IV|III|II|I)")


def normalize_tier(amp_category: str) -> Optional[str]:
    m = _TIER_RE.search(amp_category or "")
    return f"Tier {m.group(1)}" if m else None


def _gv(molecular_profile: str) -> Tuple[str, str]:
    parts = (molecular_profile or "").split()
    return (parts[0].upper(), " ".join(parts[1:]).upper()) if parts else ("", "")


def load_truth(path: Path = DEFAULT_PATH) -> Dict[Tuple[str, str], str]:
    """(gene, variant) -> expert AMP tier. Keeps the most actionable if several."""
    path = Path(path)
    truth: Dict[Tuple[str, str], str] = {}
    if not path.exists():
        return truth
    rank = {"Tier I": 3, "Tier II": 2, "Tier III": 1, "Tier IV": 0}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            tier = normalize_tier(row.get("amp_category", ""))
            if not tier:
                continue
            key = _gv(row["molecular_profile"])
            if key not in truth or rank[tier] > rank[truth[key]]:
                truth[key] = tier
    return truth


def benchmark_tier_accuracy(variants: List[dict], path: Path = DEFAULT_PATH) -> dict:
    truth = load_truth(path)
    matched, a_correct, b_correct = [], 0, 0
    for v in variants:
        key = (v["gene"].upper(), (v["hgvsp"][2:] if v["hgvsp"].startswith("p.") else v["hgvsp"]).upper())
        if key not in truth:
            continue
        gt = truth[key]
        matched.append({
            "variant": v["variant_key"], "cancer": v["cancer_type"], "truth_tier": gt,
            "mode_a_tier": v["mode_a"]["tier"], "mode_b_tier": v["mode_b"]["tier"]})
        a_correct += int(v["mode_a"]["tier"] == gt)
        b_correct += int(v["mode_b"]["tier"] == gt)
    n = len(matched)
    return {
        "n_assertions_total": len(truth),
        "n_matched_cohort": n,
        "mode_a_tier_accuracy": round(a_correct / n, 3) if n else None,
        "mode_b_tier_accuracy": round(b_correct / n, 3) if n else None,
        "matches": matched,
        "note": "Small, Tier-I-skewed, shares CIViC corpus (leakage). Secondary check only.",
    }
