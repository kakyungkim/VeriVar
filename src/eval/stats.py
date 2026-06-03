"""Statistical rigor: bootstrap CIs + McNemar paired significance (no LLM)."""
from typing import List

import numpy as np


def bootstrap_ci(outcomes: List[float], n_boot: int = 5000, alpha: float = 0.05):
    """Percentile bootstrap CI for a proportion/mean over 0/1 (or float) outcomes."""
    a = np.asarray(outcomes, dtype=float)
    if a.size == 0:
        return {"point": None, "lo": None, "hi": None, "n": 0}
    rng = np.random.default_rng(0)  # fixed seed -> reproducible
    means = rng.choice(a, size=(n_boot, a.size), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {"point": round(float(a.mean()), 3), "lo": round(float(lo), 3),
            "hi": round(float(hi), 3), "n": int(a.size)}


def mcnemar(correct_a: List[bool], correct_b: List[bool]) -> dict:
    """Exact (binomial) McNemar test on paired correctness of two methods."""
    b = sum(1 for x, y in zip(correct_a, correct_b) if x and not y)  # a right, b wrong
    c = sum(1 for x, y in zip(correct_a, correct_b) if y and not x)  # b right, a wrong
    n = b + c
    if n == 0:
        return {"a_better": b, "b_better": c, "discordant_pairs": 0, "p_value": 1.0}
    from scipy.stats import binomtest
    p = binomtest(min(b, c), n, 0.5, alternative="two-sided").pvalue
    return {"a_better": b, "b_better": c, "discordant_pairs": n, "p_value": round(float(p), 4)}
