"""Apply one citation taxonomy to every arm and write ``citation_taxonomy.json``.

Purpose
-------
Peer review 2026-09-24 (P0-1, P0-2) found that the faithfulness headline
compared two different criteria: "0 of 106 retrieval-arm citations outside the
bundle" exempted bare source names and digit tokens, while "fabricated
citations on 26/56 no-retrieval variants" counted every emitted token. This
script scores all arms with the single rule set in the module docstring of
``src/eval/citation_taxonomy.py`` (categories a / b1 / b2 / c / d); nothing
here tunes those rules.

Prerequisites
-------------
Committed outputs ``data/outputs/{cohort_interpretation,multimodel_faithfulness_gpt4o,
ablation_report}.json`` and the NCBI lookup cache
``data/outputs/citation_lookup_cache.json`` (written by
``python -m scripts.fetch_citation_lookup``, the only step that uses the
network). Runs offline; no LLM calls.

Run
---
::

    python -m scripts.run_citation_taxonomy [--cache PATH] [--out PATH]

Exit code 1 if any out-of-bundle identifier is missing from the cache.

Output
------
``data/outputs/citation_taxonomy.json``: ``headline`` (the per-arm numbers to
quote), per-arm category counts at citation and variant level with Wilson and
Clopper-Pearson 95% intervals and bootstrap intervals, zero-event upper bounds,
paired exact McNemar contrasts, and per-variant / per-citation audit rows.

Arms (same 56 variants, same order in all three files; checked at run time)
---------------------------------------------------------------------------
* ``retrieval_gpt4o_mini_106`` -- ``multimodel_faithfulness_gpt4o.json``,
  gpt-4o-mini single rater, labels + ``cited_ids`` only, NO citation gate.
  Bundles are those stored in ``cohort_interpretation.json`` (as in the NLI
  audit; per-variant bundle sizes match ``n_evidence``). Pre-gate measurement.
* ``primary_pipeline_postgate`` -- ``cohort_interpretation.json`` ``mode_a``
  (voting + verifier + citation gate). A different run from the 106 run; its
  in-bundle rate is enforced by the gate, so it is reported for completeness,
  not as an emergent measurement.
* ``no_retrieval_E_empty_bundle`` -- ``ablation_report.json``
  ``rows[].norag_citations``, gpt-4o-mini with no evidence bundle, no gate;
  scored with bundle = empty set (definition E).
* ``no_retrieval_R_reference_bundle`` -- the same tokens scored against the
  retrieval bundle of the same variant (definition R).

Statistics
----------
Citation-level rates: Wilson and Clopper-Pearson 95% intervals (iid), plus a
variant-clustered percentile bootstrap (5000 draws, seed 0). Variant-level
rates (denominator = 56 variants): Wilson, Clopper-Pearson and the project's
percentile bootstrap (``src.eval.stats.bootstrap_ci``; degenerate [0, 0] at
k = 0, so quote Wilson there). Paired arm contrasts on variant-level flags:
exact McNemar (``src.eval.stats.mcnemar``). Zero-event bounds: one-sided 95%
Clopper-Pearson ``1 - 0.05**(1/n)`` and rule of three ``3/n``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np

from src.eval.citation_taxonomy import (CATEGORY_ORDER, OUT_OF_BUNDLE_IDENTIFIER,
                                        VARIANT_FLAGS, CitationCategory, CitationRecord,
                                        VariantInput, classify_variants,
                                        existence_only_category, variant_flags)
from src.eval.stats import (bootstrap_ci, clopper_pearson_ci, mcnemar, wilson_ci,
                            zero_event_upper_bound)

COHORT = Path("data/outputs/cohort_interpretation.json")
LABEL_ONLY = Path("data/outputs/multimodel_faithfulness_gpt4o.json")
ABLATION = Path("data/outputs/ablation_report.json")
CACHE = Path("data/outputs/citation_lookup_cache.json")
OUT = Path("data/outputs/citation_taxonomy.json")
LABEL_ONLY_MODEL = "gpt-4o-mini"
ARMS = ("retrieval_gpt4o_mini_106", "primary_pipeline_postgate",
        "no_retrieval_E_empty_bundle", "no_retrieval_R_reference_bundle")
NORAG_ARMS = ("no_retrieval_E_empty_bundle", "no_retrieval_R_reference_bundle")
RAG_ARMS = ("retrieval_gpt4o_mini_106", "primary_pipeline_postgate")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _vid(v: dict) -> str:
    return f"{v.get('variant_key')} | {v.get('cancer_type')}"


def build_arms(cohort: dict, label_only: dict, ablation: dict) -> Dict[str, List[VariantInput]]:
    """Assemble the three arms as index-aligned VariantInput lists."""
    cv = cohort["variants"]
    lr = label_only["results"]
    ar = ablation["rows"]
    keys = [v["variant_key"] for v in cv]
    if keys != [r["variant_key"] for r in lr] or keys != [r["variant_key"] for r in ar]:
        raise ValueError("arms are not index-aligned on variant_key")
    if [v["cancer_type"] for v in cv] != [r["cancer_type"] for r in lr]:
        raise ValueError("106 run and cohort differ in cancer_type order")

    def bundle(v: dict) -> dict:
        evs = (v.get("bundle") or {}).get("evidences") or []
        return {"bundle_ids": [e["id"] for e in evs],
                "bundle_sources": {e["id"]: e.get("source") for e in evs},
                "bundle_pmids": {e["id"]: [str(x) for x in (e.get("pmids") or [])]
                                 for e in evs}}

    arms: Dict[str, List[VariantInput]] = {name: [] for name in ARMS}
    for i, (v, r, a) in enumerate(zip(cv, lr, ar)):
        ref = bundle(v)
        common = dict(variant_index=i, variant_id=_vid(v), gene=v["gene"], hgvsp=v["hgvsp"])
        pm = (r.get("per_model") or {}).get(LABEL_ONLY_MODEL) or {}
        norag = list(a.get("norag_citations") or [])
        arms["retrieval_gpt4o_mini_106"].append(VariantInput(
            **common, citations=list(pm.get("cited_ids") or []), **ref))
        arms["primary_pipeline_postgate"].append(VariantInput(
            **common, citations=list((v.get("mode_a") or {}).get("citations") or []), **ref))
        arms["no_retrieval_E_empty_bundle"].append(VariantInput(**common, citations=norag))
        arms["no_retrieval_R_reference_bundle"].append(VariantInput(
            **common, citations=norag, **ref))
    return arms


def cluster_bootstrap(values: Sequence[float], clusters: Sequence[int],
                      n_boot: int = 5000, seed: int = 0) -> dict:
    """Percentile bootstrap of a citation-level mean, resampling variants."""
    if not values:
        return {"point": None, "lo": None, "hi": None, "n": 0, "n_clusters": 0}
    groups: Dict[int, List[float]] = {}
    for x, c in zip(values, clusters):
        groups.setdefault(c, []).append(float(x))
    keys = list(groups)
    sums = np.array([sum(groups[k]) for k in keys])
    cnts = np.array([len(groups[k]) for k in keys])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), size=(n_boot, len(keys)))
    means = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {"point": round(float(np.mean(values)), 3), "lo": round(float(lo), 3),
            "hi": round(float(hi), 3), "n": len(values), "n_clusters": len(keys)}


def rate_block(k: int, n: int, outcomes: Sequence[float] = (),
               clusters: Sequence[int] = ()) -> dict:
    out = {"k": k, "n": n, "wilson": wilson_ci(k, n), "clopper_pearson": clopper_pearson_ci(k, n)}
    if clusters:
        out["bootstrap_variant_clustered"] = cluster_bootstrap(list(outcomes), list(clusters))
    elif outcomes:
        out["bootstrap"] = bootstrap_ci(list(outcomes))
    return out


def summarise_arm(variants: List[VariantInput], records: List[CitationRecord]) -> dict:
    n_cit = len(records)
    cats = [r.category for r in records]
    clusters = [r.variant_index for r in records]
    cc = Counter(cats)
    citation_level = {}
    for cat in CATEGORY_ORDER:
        ind = [1.0 if c == cat else 0.0 for c in cats]
        citation_level[cat.value] = rate_block(cc.get(cat, 0), n_cit, ind, clusters)

    bad = {CitationCategory.FABRICATED, CitationCategory.REAL_UNRELATED}
    ind_bad = [1.0 if c in bad else 0.0 for c in cats]
    citation_level["fabricated_or_misattributed_b1_or_c"] = rate_block(
        int(sum(ind_bad)), n_cit, ind_bad, clusters)

    ident = [r for r in records if r.category != CitationCategory.NON_IDENTIFIER]
    n_ident = len(ident)
    out_ident = sum(1 for r in ident if r.category in OUT_OF_BUNDLE_IDENTIFIER)
    ident_variants = sorted({r.variant_index for r in ident})
    out_variants = sorted({r.variant_index for r in ident if r.category in OUT_OF_BUNDLE_IDENTIFIER})

    rows = variant_flags(variants, records)
    n_var = len(variants)
    variant_level = {}
    for flag in VARIANT_FLAGS:
        ind = [1.0 if r[flag] else 0.0 for r in rows]
        variant_level[flag] = rate_block(int(sum(ind)), n_var, ind)
    n_citing = sum(1 for r in rows if r["any_citation"])
    variant_level_among_citing = {}
    for flag in VARIANT_FLAGS[1:]:
        ind = [1.0 if r[flag] else 0.0 for r in rows if r["any_citation"]]
        variant_level_among_citing[flag] = rate_block(int(sum(ind)), n_citing, ind)

    rows_eo = variant_flags(variants, records, existence_only=True)
    eo_cats = Counter(existence_only_category(r) for r in records)
    sensitivity = {
        "rule": ("existence-only: placeholder-pattern identifiers that resolve to a real "
                 "record are re-binned by gene relevance instead of counted fabricated"),
        "citation_counts": {k.value: eo_cats.get(k, 0) for k in CATEGORY_ORDER},
        "variant_any_fabricated": rate_block(sum(r["any_fabricated"] for r in rows_eo), n_var),
        "variant_any_fabricated_or_misattributed": rate_block(
            sum(r["any_fabricated_or_misattributed"] for r in rows_eo), n_var),
    }

    non_id = Counter(r.reasons[0].split(":", 1)[1] for r in records
                     if r.category == CitationCategory.NON_IDENTIFIER)
    fab_reasons = Counter("+".join(r.reasons) for r in records
                          if r.category == CitationCategory.FABRICATED)
    looked_up = [r for r in records if r.record_exists is not None]
    return {
        "n_variants": n_var,
        "n_variants_with_citations": n_citing,
        "n_citations": n_cit,
        "citation_counts": {k.value: cc.get(k, 0) for k in CATEGORY_ORDER},
        "n_in_bundle_via_backing_pmid": sum(1 for r in records if r.resolved_bundle_id
                                            and "#PMID" in r.resolved_bundle_id),
        "citation_level": citation_level,
        "non_identifier_breakdown": dict(non_id),
        "fabricated_reason_breakdown": dict(fab_reasons),
        "identifier_bearing": {
            "n_citations": n_ident,
            "n_out_of_bundle": out_ident,
            "rate_out_of_bundle": rate_block(out_ident, n_ident),
            "n_variants_citing_identifiers": len(ident_variants),
            "n_variants_with_out_of_bundle_identifier": len(out_variants),
            "zero_event_bound_citation_level": (zero_event_upper_bound(n_ident)
                                                if out_ident == 0 else None),
            "zero_event_bound_variant_level": (zero_event_upper_bound(len(ident_variants))
                                               if out_ident == 0 else None),
            "n_fabricated_or_misattributed": sum(1 for r in ident if r.category in bad),
            "n_real_and_gene_relevant_out_of_bundle": sum(
                1 for r in ident if r.category == CitationCategory.REAL_RELATED),
        },
        "identifier_bearing_plus_uniquely_resolvable_source_names": _plus_unique(records),
        "lookups": {
            "n_identifiers_looked_up": len(looked_up),
            "n_record_exists": sum(1 for r in looked_up if r.record_exists),
            "n_record_exists_mentions_gene": sum(1 for r in looked_up
                                                 if r.record_exists and r.mentions_gene),
            "n_record_exists_mentions_protein_change": sum(
                1 for r in looked_up if r.record_exists and r.mentions_protein_change),
        },
        "variant_level": variant_level,
        "variant_level_among_citing_variants": variant_level_among_citing,
        "sensitivity_existence_only": sensitivity,
        "variants": rows,
        "citations": [r.model_dump(mode="json") for r in records],
    }


def _mcnemar_exact(a: List[bool], b: List[bool]) -> dict:
    """``src.eval.stats.mcnemar`` plus the unrounded exact p-value."""
    from scipy.stats import binomtest
    res = mcnemar(a, b)
    n = res["discordant_pairs"]
    res["p_value_exact"] = (float(binomtest(min(res["a_better"], res["b_better"]), n, 0.5)
                                  .pvalue) if n else 1.0)
    return res


def _plus_unique(records: List[CitationRecord]) -> dict:
    """Secondary view: count bare source names that name the single bundle item of
    that source (e.g. bare ``AlphaMissense``) as in-bundle, as the NLI audit did.
    Only possible when a bundle exists, so it never changes the no-retrieval arm."""
    uniq = [r for r in records if r.category == CitationCategory.NON_IDENTIFIER
            and r.uniquely_resolvable_in_bundle]
    ident = [r for r in records if r.category != CitationCategory.NON_IDENTIFIER]
    n = len(ident) + len(uniq)
    k = sum(1 for r in ident if r.category in OUT_OF_BUNDLE_IDENTIFIER)
    return {"n_uniquely_resolvable_source_names": len(uniq), "n_citations": n,
            "n_out_of_bundle": k, "rate_out_of_bundle": rate_block(k, n),
            "zero_event_bound": zero_event_upper_bound(n) if k == 0 else None,
            "n_remaining_non_identifiers": len(records) - n}


def paired_contrasts(flag_rows: Dict[str, List[dict]]) -> dict:
    """Exact McNemar on variant-level flags, each no-retrieval definition vs
    each retrieval arm. ``a_better`` = variants clean in the retrieval arm and
    flagged in the no-retrieval arm."""
    out = {}
    for base_name in NORAG_ARMS:
        base = flag_rows[base_name]
        for arm in RAG_ARMS:
            other = flag_rows[arm]
            out[f"{base_name}_vs_{arm}"] = {
                flag: {"no_retrieval_k": sum(r[flag] for r in base),
                       "retrieval_k": sum(r[flag] for r in other),
                       "mcnemar": _mcnemar_exact([not r[flag] for r in other],
                                                 [not r[flag] for r in base])}
                for flag in ("any_fabricated", "any_fabricated_or_misattributed",
                             "any_out_of_bundle_identifier")
            }
    return out


def _brief(block: dict) -> dict:
    """k/n with Wilson and (when present) bootstrap bounds, for the headline."""
    out = {"k": block["k"], "n": block["n"], "rate": block["wilson"]["point"],
           "wilson_95": [block["wilson"]["lo"], block["wilson"]["hi"]]}
    boot = block.get("bootstrap") or block.get("bootstrap_variant_clustered")
    if boot:
        out["bootstrap_95"] = [boot["lo"], boot["hi"]]
    return out


def headline(report_arms: Dict[str, dict], contrasts: dict, old: dict) -> dict:
    """The consistent-criterion numbers to quote, one entry per arm."""
    arms = {}
    for name, a in report_arms.items():
        idb = a["identifier_bearing"]
        pu = a["identifier_bearing_plus_uniquely_resolvable_source_names"]
        arms[name] = {
            "n_citations": a["n_citations"],
            "n_variants_with_citations": a["n_variants_with_citations"],
            "citation_counts": a["citation_counts"],
            "variant_any_fabricated_identifier": _brief(a["variant_level"]["any_fabricated"]),
            "variant_any_fabricated_or_misattributed": _brief(
                a["variant_level"]["any_fabricated_or_misattributed"]),
            "variant_any_non_identifier": _brief(a["variant_level"]["any_non_identifier"]),
            "citation_fabricated_or_misattributed": _brief(
                a["citation_level"]["fabricated_or_misattributed_b1_or_c"]),
            "identifier_tokens_out_of_bundle": {
                "k": idb["n_out_of_bundle"], "n": idb["n_citations"],
                "n_variants": idb["n_variants_citing_identifiers"],
                "wilson_95": [idb["rate_out_of_bundle"]["wilson"]["lo"],
                              idb["rate_out_of_bundle"]["wilson"]["hi"]],
                "zero_event_bound_citation_level": idb["zero_event_bound_citation_level"],
                "zero_event_bound_variant_level": idb["zero_event_bound_variant_level"]},
            "identifier_tokens_plus_uniquely_resolvable_source_names_out_of_bundle": {
                "k": pu["n_out_of_bundle"], "n": pu["n_citations"],
                "zero_event_bound": pu["zero_event_bound"]},
        }
    e, r = (report_arms[n]["citation_counts"] for n in NORAG_ARMS)
    return {
        "criterion": ("fabricated identifier = b1 (placeholder-pattern number, identifier "
                      "under a namespace with no numeric scheme, or no NCBI record); "
                      "misattributed = c (real record whose title/abstract does not name "
                      "the variant's gene); non-identifiers (d) are counted separately "
                      "as imprecision in every arm"),
        "no_retrieval_definitions_agree": e == r,
        "arms": arms,
        "paired_mcnemar_exact_p": {
            k: {f: v[f]["mcnemar"]["p_value_exact"] for f in v} for k, v in contrasts.items()},
        "previous_headlines": old,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=CACHE)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    cohort = json.loads(COHORT.read_text())
    label_only = json.loads(LABEL_ONLY.read_text())
    ablation = json.loads(ABLATION.read_text())
    cache = json.loads(args.cache.read_text())

    arms = build_arms(cohort, label_only, ablation)
    report_arms = {}
    flag_rows = {}
    for name, variants in arms.items():
        recs = classify_variants(variants, cache)
        report_arms[name] = summarise_arm(variants, recs)
        flag_rows[name] = report_arms[name]["variants"]

    old = {
        "no_retrieval_previous_headline": {
            "definition": "variants emitting any citation (every token counted ungrounded)",
            "k": ablation["faithfulness"]["norag_ungrounded_citations"], "n": ablation["n"],
            "source": "data/outputs/ablation_report.json faithfulness.norag_ungrounded_citations",
        },
        "retrieval_106_previous_headline": {
            "definition": "0 of 106 tokens outside the bundle (non-identifiers exempted)",
            "n_tokens": report_arms["retrieval_gpt4o_mini_106"]["n_citations"],
        },
    }
    contrasts = paired_contrasts(flag_rows)
    report = {
        "purpose": ("One citation taxonomy applied identically to the retrieval, primary "
                    "post-gate and no-retrieval arms (peer review 2026-09-24 P0-1/P0-2)."),
        "rules": "see src/eval/citation_taxonomy.py module docstring (pre-specified)",
        "categories": [c.value for c in CATEGORY_ORDER],
        "headline": headline(report_arms, contrasts, old),
        "provenance": {
            "inputs": {str(p): _sha(p) for p in (COHORT, LABEL_ONLY, ABLATION, args.cache)},
            "lookup_retrieved_utc": cache.get("retrieved_utc"),
            "lookup_source": cache.get("source"),
            "arm_notes": {
                "retrieval_gpt4o_mini_106": "gpt-4o-mini, single rater, no citation gate (pre-gate)",
                "primary_pipeline_postgate": ("voting + verifier + citation gate; different run "
                                              "from the 106 run; in-bundle by construction"),
                "no_retrieval_E_empty_bundle": ("gpt-4o-mini, no evidence bundle, no gate; "
                                                "scored against the empty set"),
                "no_retrieval_R_reference_bundle": ("same tokens scored against the retrieval "
                                                    "bundle of the same variant"),
            },
        },
        "previous_headlines_for_comparison": old,
        "arms": report_arms,
        "paired_contrasts_variant_level": contrasts,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    print(f"[+] wrote {args.out}")
    for name, a in report_arms.items():
        vl = a["variant_level"]
        idb = a["identifier_bearing"]
        print(f"\n== {name}: {a['n_citations']} citations over "
              f"{a['n_variants_with_citations']}/{a['n_variants']} variants")
        print("   citation counts:", a["citation_counts"])
        print("   non-identifier:", a["non_identifier_breakdown"],
              "| fabricated reasons:", a["fabricated_reason_breakdown"])
        print(f"   identifier-bearing out of bundle: {idb['n_out_of_bundle']}/{idb['n_citations']}"
              f" over {idb['n_variants_citing_identifiers']} variants; bound:",
              idb["zero_event_bound_citation_level"])
        for f in VARIANT_FLAGS:
            w = vl[f]["wilson"]
            print(f"   {f:34s} {vl[f]['k']:2d}/{vl[f]['n']} = {w['point']} "
                  f"Wilson [{w['lo']}, {w['hi']}] boot [{vl[f]['bootstrap']['lo']}, "
                  f"{vl[f]['bootstrap']['hi']}]")
        pu = a["identifier_bearing_plus_uniquely_resolvable_source_names"]
        print(f"   + uniquely resolvable source names: {pu['n_out_of_bundle']}/{pu['n_citations']}"
              f" bound {pu['zero_event_bound']}")
        cb = a["citation_level"]["fabricated_or_misattributed_b1_or_c"]
        print(f"   citation-level b1|c: {cb['k']}/{cb['n']} Wilson {cb['wilson']['lo']}-"
              f"{cb['wilson']['hi']}")
        se = a["sensitivity_existence_only"]
        print("   existence-only sensitivity: any_fab",
              se["variant_any_fabricated"]["k"], "any_fab_or_mis",
              se["variant_any_fabricated_or_misattributed"]["k"])
    for k, v in report["paired_contrasts_variant_level"].items():
        print(f"\n{k}:")
        for f, d in v.items():
            print(f"   {f}: {d}")
    unchecked = sum(a["citation_counts"][CitationCategory.UNCHECKED.value]
                    for a in report_arms.values())
    if unchecked:
        print(f"\n[!] {unchecked} out-of-bundle identifiers were not in the lookup cache; "
              "run scripts/fetch_citation_lookup.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
