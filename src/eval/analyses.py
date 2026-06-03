"""Additional deterministic analyses over a cohort_interpretation.json (no LLM).

Each function takes the `variants` list and returns a JSON-able dict:
  1. cross_cancer_consistency  — same variant across cancers: stable oncogenicity, context-dependent tier
  2. sensitivity_vs_resistance — does the system avoid calling resistance-only variants actionable?
  3. dense_recall_lift         — CIViC evidence recovered by the dense arm vs exact-match (needs aggregator)
  4. alphamissense_llm_agreement — computational (OP1/SBP1) vs LLM oncogenicity on AM-only variants
  5. confidence_calibration    — does low voting-confidence track discordance?
  6. discordance_concentration — by gene / cancer
  7. hotspot_vs_rare           — discordance on known hotspots vs other variants
"""
from collections import Counter, defaultdict
from typing import Dict, List

_ONCO = {"Oncogenic", "Likely Oncogenic"}
_BENIGN = {"Likely Benign", "Benign"}

# Well-established oncogenic hotspots present in / relevant to the cohort.
_HOTSPOTS = {
    ("BRAF", "V600E"), ("KRAS", "G12C"), ("KRAS", "G12D"), ("KRAS", "G12V"), ("KRAS", "G12R"),
    ("KRAS", "G13D"), ("NRAS", "Q61K"), ("NRAS", "Q61R"), ("EGFR", "L858R"), ("EGFR", "T790M"),
    ("PIK3CA", "H1047R"), ("PIK3CA", "E545K"), ("PIK3CA", "E542K"), ("IDH1", "R132H"),
}


def _norm(hgvsp: str) -> str:
    return (hgvsp[2:] if hgvsp.startswith("p.") else hgvsp).upper()


def _evs(v):
    return (v.get("bundle") or {}).get("evidences", [])


def cross_cancer_consistency(variants: List[dict]) -> dict:
    by_variant = defaultdict(list)
    for v in variants:
        by_variant[(v["gene"].upper(), _norm(v["hgvsp"]))].append(v)
    multi = {k: vs for k, vs in by_variant.items() if len({v["cancer_type"] for v in vs}) > 1}
    rows, stable_onc, variable_tier = [], 0, 0
    for (g, p), vs in sorted(multi.items()):
        oncs = {v["mode_a"]["oncogenicity"] for v in vs}
        tiers = {v["mode_a"]["tier"] for v in vs}
        if len(oncs) == 1:
            stable_onc += 1
        if len(tiers) > 1:
            variable_tier += 1
        rows.append({"variant": f"{g} {p}",
                     "per_cancer": {v["cancer_type"]: f"{v['mode_a']['oncogenicity']}/{v['mode_a']['tier']}" for v in vs}})
    return {"n_multi_cancer_variants": len(multi),
            "stable_oncogenicity": stable_onc, "variable_tier": variable_tier,
            "detail": rows}


def sensitivity_vs_resistance(variants: List[dict]) -> dict:
    """Profile sensitivity- vs resistance-bearing variants.

    NOTE: resistance markers are legitimately actionable (Tier I/II) under
    AMP/ASCO/CAP — a resistance biomarker guides therapy AWAY from a drug. So a
    resistance-only variant being tiered actionable is CORRECT, not an error. The
    open question (needs rationale-text analysis) is whether the EXPLANATION
    conveys use-vs-avoid; reported here descriptively.
    """
    sens_only = resist_only = both = 0
    resist_only_tiers = Counter()
    for v in variants:
        sens = sum(1 for e in _evs(v) if (e.get("significance") or "").lower() == "sensitivity/response"
                   and e.get("direction") == "Supports")
        resist = sum(1 for e in _evs(v) if (e.get("significance") or "").lower() == "resistance")
        if sens and not resist:
            sens_only += 1
        elif resist and not sens:
            resist_only += 1
            resist_only_tiers[v["mode_a"]["tier"]] += 1
        elif sens and resist:
            both += 1
    return {"sensitivity_only": sens_only, "resistance_only": resist_only,
            "both": both, "resistance_only_tier_distribution": dict(resist_only_tiers),
            "note": "Resistance markers are appropriately Tier I/II (guide therapy away). Not errors."}


def dense_recall_lift(variants: List[dict], aggregator) -> dict:
    """CIViC evidence count: dense-enriched (in output) vs structured exact-match."""
    from src.models import Variant
    gained, total_lift = 0, 0
    examples = []
    for v in variants:
        dense_civic = sum(1 for e in _evs(v) if e.get("source") == "CIViC")
        var = Variant(chrom="", pos=0, ref="", alt="", gene=v["gene"], hgvsp=v["hgvsp"],
                      cancer_type=v["cancer_type"], variant_type=v["variant_type"])
        struct = aggregator.for_variant_obj(var)
        struct_civic = sum(1 for e in struct.evidences if e.source == "CIViC")
        lift = dense_civic - struct_civic
        if lift > 0:
            gained += 1
            total_lift += lift
            examples.append({"variant": v["variant_key"], "structured": struct_civic, "dense": dense_civic})
    examples.sort(key=lambda x: x["structured"] - x["dense"])
    return {"variants_gaining_evidence": gained, "total_civic_added": total_lift,
            "examples": examples[:10]}


def alphamissense_llm_agreement(variants: List[dict]) -> dict:
    checked = agree = 0
    detail = []
    for v in variants:
        if v.get("evidence_tier") != "alphamissense":
            continue
        am = next((e for e in _evs(v) if e.get("source") == "AlphaMissense" and e.get("score") is not None), None)
        if not am:
            continue
        am_path = am["score"] >= 0.564
        am_benign = am["score"] <= 0.34
        onc = v["mode_a"]["oncogenicity"]
        if not (am_path or am_benign):
            continue  # ambiguous AM — skip
        checked += 1
        ok = (am_path and onc in _ONCO) or (am_benign and onc in _BENIGN)
        agree += int(ok)
        if not ok:
            detail.append({"variant": v["variant_key"], "am_score": round(am["score"], 3), "llm": onc})
    return {"checked": checked, "agree": agree,
            "agreement_rate": round(agree / checked, 3) if checked else None,
            "disagreements": detail[:10]}


def confidence_calibration(variants: List[dict]) -> dict:
    bins = defaultdict(lambda: {"n": 0, "discordant": 0, "verifier_downgraded": 0})
    for v in variants:
        c = v["mode_a"].get("confidence")
        if c is None:
            continue
        key = "high (>=0.9)" if c >= 0.9 else ("mid (0.7-0.9)" if c >= 0.7 else "low (<0.7)")
        b = bins[key]
        b["n"] += 1
        b["discordant"] += int(bool(v["discordant"]))
        b["verifier_downgraded"] += int("[Verifier:" in (v["mode_a"].get("rationale") or ""))
    out = {}
    for k, b in bins.items():
        out[k] = {**b, "discordance_rate": round(b["discordant"] / b["n"], 3) if b["n"] else None}
    return out


def discordance_concentration(variants: List[dict]) -> dict:
    gene = defaultdict(lambda: [0, 0])   # [discordant, total]
    cancer = defaultdict(lambda: [0, 0])
    for v in variants:
        gene[v["gene"]][1] += 1
        gene[v["gene"]][0] += int(bool(v["discordant"]))
        cancer[v["cancer_type"]][1] += 1
        cancer[v["cancer_type"]][0] += int(bool(v["discordant"]))
    def fmt(d):
        return {k: {"discordant": a, "total": b, "rate": round(a / b, 3)}
                for k, (a, b) in sorted(d.items(), key=lambda kv: -kv[1][0] / kv[1][1])}
    return {"by_gene": fmt(gene), "by_cancer": fmt(cancer)}


def hotspot_vs_rare(variants: List[dict]) -> dict:
    def grp(is_hot):
        sel = [v for v in variants if ((v["gene"].upper(), _norm(v["hgvsp"])) in _HOTSPOTS) == is_hot]
        n = len(sel)
        d = sum(int(bool(v["discordant"])) for v in sel)
        return {"n": n, "discordant": d, "discordance_rate": round(d / n, 3) if n else None}
    return {"hotspot": grp(True), "non_hotspot": grp(False)}


_TIER_RANK = {"Tier IV": 0, "Tier III": 1, "Tier II": 2, "Tier I": 3}


def verifier_effect(verified: List[dict], noverify: List[dict]) -> dict:
    """Did the agentic verifier move Mode A toward or away from the rule (Mode B)?

    Compares a --verify run against a --vote --dense run without the verifier.
    Also reports the change in Mode-A/Mode-B tier concordance.
    """
    def key(v):
        return (v["gene"], v["hgvsp"], v["cancer_type"])

    nv = {key(v): v for v in noverify}
    changed = toward = away = 0
    examples = []
    for vv in verified:
        if key(vv) not in nv:
            continue
        a_ver, a_nov = vv["mode_a"]["tier"], nv[key(vv)]["mode_a"]["tier"]
        rule = vv["mode_b"]["tier"]
        if a_ver == a_nov:
            continue
        changed += 1
        d_ver = abs(_TIER_RANK[a_ver] - _TIER_RANK[rule])
        d_nov = abs(_TIER_RANK[a_nov] - _TIER_RANK[rule])
        if d_ver < d_nov:
            toward += 1
        elif d_ver > d_nov:
            away += 1
        examples.append({"variant": vv["variant_key"], "cancer": vv["cancer_type"],
                         "no_verify": a_nov, "verified": a_ver, "rule": rule})

    def tier_concord(variants):
        n = len(variants)
        return round(sum(v["mode_a"]["tier"] == v["mode_b"]["tier"] for v in variants) / n, 3) if n else None

    return {
        "tier_changed_by_verifier": changed,
        "moved_toward_rule": toward,
        "moved_away_from_rule": away,
        "tier_concordance_no_verify": tier_concord(noverify),
        "tier_concordance_verified": tier_concord(verified),
        "examples": examples[:12],
    }


def run_all(variants: List[dict], aggregator=None) -> dict:
    out = {
        "cross_cancer_consistency": cross_cancer_consistency(variants),
        "sensitivity_vs_resistance": sensitivity_vs_resistance(variants),
        "alphamissense_llm_agreement": alphamissense_llm_agreement(variants),
        "confidence_calibration": confidence_calibration(variants),
        "discordance_concentration": discordance_concentration(variants),
        "hotspot_vs_rare": hotspot_vs_rare(variants),
    }
    if aggregator is not None:
        out["dense_recall_lift"] = dense_recall_lift(variants, aggregator)
    return out
