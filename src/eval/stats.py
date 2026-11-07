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


def wilson_ci(k: int, n: int, alpha: float = 0.05) -> dict:
    """Wilson score interval for a binomial proportion k/n.

    Unlike the percentile bootstrap, it does not collapse to a zero-width
    interval when k == 0 or k == n, so it is the interval to report for
    proportions at the boundary (e.g. 37/37).
    """
    if n <= 0:
        return {"point": None, "lo": None, "hi": None, "k": int(k), "n": int(n),
                "method": "wilson"}
    from scipy.stats import norm
    z = float(norm.ppf(1 - alpha / 2))
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return {"point": round(p, 3), "lo": round(max(0.0, centre - half), 3),
            "hi": round(min(1.0, centre + half), 3), "k": int(k), "n": int(n),
            "method": "wilson"}


def clopper_pearson_ci(k: int, n: int, alpha: float = 0.05) -> dict:
    """Exact (Clopper-Pearson) two-sided interval for a binomial proportion k/n."""
    if n <= 0:
        return {"point": None, "lo": None, "hi": None, "k": int(k), "n": int(n),
                "method": "clopper_pearson"}
    from scipy.stats import beta
    lo = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return {"point": round(k / n, 3), "lo": round(lo, 3), "hi": round(hi, 3),
            "k": int(k), "n": int(n), "method": "clopper_pearson"}


def zero_event_upper_bound(n: int, alpha: float = 0.05) -> dict:
    """One-sided upper bounds on a rate when 0 events are observed in n trials.

    Returns the exact one-sided Clopper-Pearson bound ``1 - alpha**(1/n)`` and
    the rule-of-three approximation ``3/n`` (valid for alpha = 0.05).
    """
    if n <= 0:
        return {"n": int(n), "one_sided_level": 1 - alpha, "clopper_pearson_upper": None,
                "rule_of_three_upper": None}
    return {"n": int(n), "one_sided_level": round(1 - alpha, 3),
            "clopper_pearson_upper": round(1 - alpha ** (1 / n), 4),
            "rule_of_three_upper": round(3 / n, 4)}


def boundary_ci(k: int, n: int, alpha: float = 0.05) -> dict:
    """Both exact-style intervals for a proportion, for use beside bootstrap fields."""
    return {"wilson": wilson_ci(k, n, alpha), "clopper_pearson": clopper_pearson_ci(k, n, alpha)}


def onc_vs_rest_exact_ci(pred3, gold3, positive: str = "ONC", alpha: float = 0.05) -> dict:
    """Wilson + Clopper-Pearson intervals for positive-vs-rest sensitivity and specificity."""
    tp = sum(1 for p, g in zip(pred3, gold3) if g == positive and p == positive)
    fn = sum(1 for p, g in zip(pred3, gold3) if g == positive and p != positive)
    tn = sum(1 for p, g in zip(pred3, gold3) if g != positive and p != positive)
    fp = sum(1 for p, g in zip(pred3, gold3) if g != positive and p == positive)
    return {"sensitivity": boundary_ci(tp, tp + fn, alpha),
            "specificity": boundary_ci(tn, tn + fp, alpha)}
