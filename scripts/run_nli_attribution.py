"""NLI attribution audit (Type II faithfulness) of already-emitted citations.

Purpose
-------
The manuscript's faithfulness headline ("106 citations, 0 outside the retrieved
bundle") is a Type I guarantee: every cited identifier *exists* in the bundle.
It says nothing about Type II, a real in-bundle identifier attached to a claim
the cited item does not support. This script measures Type II with an
off-the-shelf NLI cross-encoder (premise = cited evidence text, hypothesis =
the claim that cites it). **No LLM API call is made**; it re-reads committed
outputs only.

Two citation sets are audited, because they carry different claim text:

1. ``pipeline_rationale_arm`` -- the manuscript's generative RAG arm
   (``data/outputs/cohort_interpretation.json``; the same file the post-gate
   scorecard is computed from). Each variant has a free-text rationale plus a
   citation list. A citation whose identifier appears inline in the rationale
   is aligned to the sentence(s) carrying it (``inline``); otherwise it is
   scored against every rationale sentence and the best one is kept
   (``max_over_rationale``, a lenient upper bound on support).
2. ``label_only_106_arm`` -- the 106 citations behind the headline
   (``data/outputs/multimodel_faithfulness_gpt4o.json``, gpt-4o-mini, bundles
   from ``cohort_interpretation.json``). That run returned only
   ``{oncogenicity, tier, cited_ids}``; there is no rationale sentence. The
   claim a citation supports is therefore the emitted label itself, rendered
   by a template fixed before any score was seen. This arm is also
   cross-tabulated against the existing 18.9% (20/106) imprecision labels.

The no-retrieval arm is not audited: its citations ("ClinGen: BRAF", ...) do
not resolve to any evidence item with text, so no premise exists offline.

Decision rule (fixed a priori, not tuned)
-----------------------------------------
Per (premise chunk, hypothesis) pair the model yields P(entail/neutral/
contradict). Per citation, take the max over chunks and candidate sentences:
``supported`` if max P(entail) >= 0.5; else ``contradicted`` if max
P(contradict) >= 0.5; else ``neutral`` (unsupported). Variant level: fully
supported (all citations supported), partially (some), unsupported (none),
plus a separate any-contradicted flag. CIs are percentile bootstrap
(``src.eval.stats.bootstrap_ci``, 5000 draws, seed 0) over citations, with a
variant-clustered bootstrap reported alongside because citations nest in
variants.

Prerequisites
-------------
``transformers`` + ``torch`` (already installed with sentence-transformers;
nothing new in requirements.txt) and the NLI checkpoints, which must ship
safetensors (torch 2.2.2). First run downloads them to the HF cache:
``MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli`` (primary) and
``MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`` (sensitivity). CPU is fine
(a few minutes).

Run
---
::

    python -m scripts.run_nli_attribution
    python -m scripts.run_nli_attribution --no-sensitivity   # primary model only

Output
------
``data/outputs/nli_attribution_report.json``: provenance (model ids + resolved
revisions, thresholds, templates, input sha256), per-arm aggregates with CIs,
imprecision cross-tab + kappa, sensitivity analyses, a 10-row hand-inspection
sample per arm, and every per-citation record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from src.eval.metrics import cohens_kappa
from src.eval.stats import bootstrap_ci

COHORT = Path("data/outputs/cohort_interpretation.json")
LABEL_ONLY = Path("data/outputs/multimodel_faithfulness_gpt4o.json")
LABEL_ONLY_MODEL = "gpt-4o-mini"
OUT = Path("data/outputs/nli_attribution_report.json")

PRIMARY_MODEL = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
SENSITIVITY_MODEL = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"

ENTAIL_T = 0.5
CONTRA_T = 0.5
CHUNK_WORDS = 200          # premise chunk budget; 512-token model input
N_BOOT = 5000
SAMPLE_N = 10

ONC_TEMPLATE = "{gene} {protein} is an oncogenic mutation."
BEN_TEMPLATE = "{gene} {protein} is not an oncogenic mutation."

# (premise, hypothesis) -> {"entailment": p, "neutral": p, "contradiction": p}
Scorer = Callable[[Sequence[Tuple[str, str]]], List[Dict[str, float]]]

_CITE_GROUP = re.compile(
    r"\s*[\(\[]\s*(?:CIViC|AlphaMissense|DGIdb|ClinicalTrials|NCT|EID)[^\)\]]*[\)\]]")
_CITE_BARE = re.compile(r"\b(?:CIViC:EID\d+|AlphaMissense:[\w:>]+|EID\d+)\b")
_VERIFIER = re.compile(r"\[Verifier:\s*(.*?)\]\s*$", re.DOTALL)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\(\[])")


# ---------------------------------------------------------------------------
# Text alignment (pure, model-free)
# ---------------------------------------------------------------------------
def split_sentences(text: str) -> List[str]:
    """Split a rationale into sentences; unwrap a trailing ``[Verifier: ...]``."""
    text = (text or "").strip()
    m = _VERIFIER.search(text)
    parts = [text[:m.start()], m.group(1)] if m else [text]
    out: List[str] = []
    for p in parts:
        out.extend(s.strip() for s in _SENT_SPLIT.split(p.strip()) if s.strip())
    return out


def strip_citations(sentence: str) -> str:
    """Remove citation tokens so the hypothesis is the bare claim."""
    s = _CITE_GROUP.sub("", sentence)
    s = _CITE_BARE.sub("", s)
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def _mentions(sentence: str, cid: str) -> bool:
    suffix = cid.split(":", 1)[1] if ":" in cid else cid
    return cid in sentence or bool(re.search(rf"(?<![\w]){re.escape(suffix)}(?![\w])",
                                             sentence))


def align_citation(rationale: str, cid: str) -> Tuple[List[str], str]:
    """Return (candidate claim sentences, alignment type) for one citation."""
    sents = split_sentences(rationale)
    inline = [s for s in sents if _mentions(s, cid)]
    if inline:
        return [strip_citations(s) for s in inline], "inline"
    return [strip_citations(s) for s in sents], "max_over_rationale"


def build_premise(ev: dict, mode: str = "header+statement") -> str:
    """Evidence text of a cited item. ``header+statement`` prepends the item's
    own structured fields (gene, variant, disease, type, direction,
    significance); ``statement`` uses the free text alone."""
    stmt = (ev.get("statement") or "").strip()
    if mode == "statement":
        return stmt
    fields = [f"{ev.get('source', '')} evidence for {ev.get('gene', '')} "
              f"{ev.get('variant', '')}".strip()]
    if ev.get("disease"):
        fields.append(f"in {ev['disease']}")
    meta = [ev.get(k) for k in ("evidence_type", "direction", "significance") if ev.get(k)]
    head = " ".join(fields) + (f" ({'; '.join(meta)})" if meta else "") + "."
    return f"{head} {stmt}".strip()


def chunk_premise(text: str, max_words: int = CHUNK_WORDS) -> List[str]:
    """Greedy sentence-packing into chunks of <= max_words (long sentences split)."""
    sents = _SENT_SPLIT.split(text.strip()) if text.strip() else []
    chunks, cur = [], []
    for s in sents:
        words = s.split()
        while len(words) > max_words:
            if cur:
                chunks.append(" ".join(cur))
                cur = []
            chunks.append(" ".join(words[:max_words]))
            words = words[max_words:]
        if len(cur) + len(words) > max_words and cur:
            chunks.append(" ".join(cur))
            cur = []
        cur.extend(words)
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def resolve_citation(cid: str, bundle_ids: Sequence[str],
                     sources: Dict[str, str]) -> Tuple[Optional[str], str]:
    """Map an emitted token to a bundle id; return (id or None, match type).

    Match types reproduce the existing 18.9% measure: ``exact`` and
    ``normalized`` (prefix-stripped, e.g. ``EID6003`` -> ``CIViC:EID6003``)
    are precise; ``bare_source`` (e.g. ``AlphaMissense``) is imprecise but
    resolvable when the bundle holds exactly one item of that source;
    ``unresolvable`` is imprecise with no single target.
    """
    if cid in bundle_ids:
        return cid, "exact"
    norm = [i for i in bundle_ids if i.split(":", 1)[-1] == cid]
    if len(norm) == 1:
        return norm[0], "normalized"
    same_src = [i for i in bundle_ids if sources.get(i) == cid]
    if len(same_src) == 1:
        return same_src[0], "bare_source"
    return None, "unresolvable"


def label_template(label: str, gene: str, hgvsp: str) -> Optional[str]:
    """A-priori claim template for a label-only citation (None = not testable)."""
    protein = str(hgvsp or "").replace("p.", "")
    if label in ("Oncogenic", "Likely Oncogenic"):
        return ONC_TEMPLATE.format(gene=gene, protein=protein)
    if label in ("Benign", "Likely Benign"):
        return BEN_TEMPLATE.format(gene=gene, protein=protein)
    return None


# ---------------------------------------------------------------------------
# Scoring + labelling
# ---------------------------------------------------------------------------
def score_citation(scorer: Scorer, premise: str, hypotheses: Sequence[str]) -> dict:
    """Max entail / max contradict over premise chunks x candidate hypotheses."""
    chunks = chunk_premise(premise) or [""]
    pairs = [(c, h) for h in hypotheses for c in chunks]
    probs = scorer(pairs)
    best = max(range(len(pairs)), key=lambda i: probs[i]["entailment"])
    return {
        "max_entailment": round(max(p["entailment"] for p in probs), 4),
        "max_contradiction": round(max(p["contradiction"] for p in probs), 4),
        "best_hypothesis": pairs[best][1],
        "best_chunk": pairs[best][0],
        "n_chunks": len(chunks),
        "n_hypotheses": len(hypotheses),
    }


def label_scores(max_entail: float, max_contra: float,
                 entail_t: float = ENTAIL_T, contra_t: float = CONTRA_T) -> str:
    """A-priori decision rule: supported > contradicted > neutral."""
    if max_entail >= entail_t:
        return "supported"
    if max_contra >= contra_t:
        return "contradicted"
    return "neutral"


def cluster_bootstrap_ci(values: Sequence[float], clusters: Sequence[str],
                         n_boot: int = N_BOOT, alpha: float = 0.05) -> dict:
    """Percentile bootstrap resampling whole clusters (variants), seed 0."""
    by: Dict[str, List[float]] = defaultdict(list)
    for v, c in zip(values, clusters):
        by[c].append(float(v))
    keys = list(by)
    if not keys:
        return {"point": None, "lo": None, "hi": None, "n": 0, "n_clusters": 0}
    sums = np.array([sum(by[k]) for k in keys])
    cnts = np.array([len(by[k]) for k in keys])
    rng = np.random.default_rng(0)
    idx = rng.integers(0, len(keys), size=(n_boot, len(keys)))
    means = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {"point": round(float(sums.sum() / cnts.sum()), 3), "lo": round(float(lo), 3),
            "hi": round(float(hi), 3), "n": int(cnts.sum()), "n_clusters": len(keys)}


def aggregate(records: List[dict], key: str = "label") -> dict:
    """Citation- and variant-level rates with bootstrap CIs."""
    scored = [r for r in records if r.get(key)]
    out: dict = {"n_citations": len(scored), "n_variants":
                 len({r["variant_id"] for r in scored}), "counts": dict(Counter(
                     r[key] for r in scored))}
    rates = {}
    for lab in ("supported", "neutral", "contradicted"):
        vals = [1.0 if r[key] == lab else 0.0 for r in scored]
        rates[lab] = {"iid": bootstrap_ci(vals, n_boot=N_BOOT),
                      "variant_clustered": cluster_bootstrap_ci(
                          vals, [r["variant_id"] for r in scored])}
    out["citation_level"] = rates
    per_var: Dict[str, List[str]] = defaultdict(list)
    for r in scored:
        per_var[r["variant_id"]].append(r[key])
    cats = []
    for labs in per_var.values():
        k = sum(l == "supported" for l in labs)
        cats.append("fully" if k == len(labs) else "partially" if k else "unsupported")
    anyc = [1.0 if "contradicted" in labs else 0.0 for labs in per_var.values()]
    out["variant_level"] = {
        "n": len(cats), "counts": dict(Counter(cats)),
        **{c: bootstrap_ci([1.0 if x == c else 0.0 for x in cats], n_boot=N_BOOT)
           for c in ("fully", "partially", "unsupported")},
        "any_contradicted": bootstrap_ci(anyc, n_boot=N_BOOT),
    }
    return out


def imprecision_crosstab(records: List[dict], key: str = "label") -> dict:
    """NLI support vs the existing precise/imprecise labels (label-only arm)."""
    tab: Dict[str, Counter] = {"precise": Counter(), "imprecise": Counter()}
    for r in records:
        tab["imprecise" if r["imprecise"] else "precise"][r.get(key) or "not_testable"] += 1
    both = [r for r in records if r.get(key)]
    a = ["flag" if r["imprecise"] else "ok" for r in both]
    b = ["flag" if r[key] != "supported" else "ok" for r in both]
    agree = sum(x == y for x, y in zip(a, b))
    return {
        "table": {k: dict(v) for k, v in tab.items()},
        "binary_definition": "existing: imprecise vs precise; NLI: not-supported vs "
                             "supported; over citations with a resolvable premise",
        "n": len(both),
        "percent_agreement": round(agree / len(both), 3) if both else None,
        "cohens_kappa": cohens_kappa(a, b) if both else None,
    }


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------
def _vid(v: dict) -> str:
    return f"{v.get('variant_key')} | {v.get('cancer_type')}"


def pipeline_records(variants: Iterable[dict], premise_mode: str) -> List[dict]:
    """One record per (variant, citation) of the rationale-bearing arm."""
    recs = []
    for v in variants:
        a = v.get("mode_a") or {}
        evs = {e["id"]: e for e in (v.get("bundle") or {}).get("evidences", [])}
        for cid in a.get("citations") or []:
            ev = evs.get(cid)
            hyps, how = align_citation(a.get("rationale", ""), cid)
            recs.append({
                "variant_id": _vid(v), "call": a.get("oncogenicity"), "citation": cid,
                "source": (ev or {}).get("source"), "alignment": how,
                "premise": build_premise(ev, premise_mode) if ev else None,
                "hypotheses": hyps,
            })
    return recs


def label_only_records(results: Iterable[dict], cohort: Dict[str, dict],
                       premise_mode: str, model: str = LABEL_ONLY_MODEL) -> List[dict]:
    """One record per emitted token of the label-only (106) run."""
    recs = []
    for r in results:
        v = cohort[f"{r['variant_key']} | {r['cancer_type']}"]
        evs = {e["id"]: e for e in (v.get("bundle") or {}).get("evidences", [])}
        sources = {i: e.get("source") for i, e in evs.items()}
        pm = (r.get("per_model") or {}).get(model) or {}
        hyp = label_template(pm.get("oncogenicity"), r.get("gene"), r.get("hgvsp"))
        for tok in pm.get("cited_ids") or []:
            rid, how = resolve_citation(tok, list(evs), sources)
            recs.append({
                "variant_id": _vid(v), "call": pm.get("oncogenicity"), "citation": tok,
                "resolved_id": rid, "match": how,
                "imprecise": how in ("bare_source", "unresolvable"),
                "source": sources.get(rid) if rid else None,
                "premise": build_premise(evs[rid], premise_mode) if rid else None,
                "hypotheses": [hyp] if hyp else [],
            })
    return recs


def score_records(recs: List[dict], scorer: Scorer, key: str = "label") -> None:
    """Attach NLI scores + a-priori label in place (records w/o premise/hypothesis
    stay unlabelled and are reported as not testable)."""
    for r in recs:
        if not r.get("premise") or not r.get("hypotheses"):
            r[key] = None
            continue
        s = score_citation(scorer, r["premise"], r["hypotheses"])
        r[key + "_scores"] = s
        r[key] = label_scores(s["max_entailment"], s["max_contradiction"])


def hand_sample(recs: List[dict], n: int = SAMPLE_N, key: str = "label") -> List[dict]:
    """Deterministic stratified sample (seed 0) for human review."""
    scored = [r for r in recs if r.get(key)]
    rng = np.random.default_rng(0)
    order = rng.permutation(len(scored)).tolist()
    by: Dict[str, List[dict]] = defaultdict(list)
    for i in order:
        by[scored[i][key]].append(scored[i])
    picked: List[dict] = []
    while len(picked) < min(n, len(scored)):
        for lab in ("supported", "neutral", "contradicted"):
            if by[lab] and len(picked) < n:
                picked.append(by[lab].pop(0))
    return [{"variant_id": r["variant_id"], "call": r["call"], "citation": r["citation"],
             "premise_chunk": r[key + "_scores"]["best_chunk"],
             "hypothesis": r[key + "_scores"]["best_hypothesis"],
             "p_entail": r[key + "_scores"]["max_entailment"],
             "p_contradict": r[key + "_scores"]["max_contradiction"],
             "label": r[key]} for r in picked]


# ---------------------------------------------------------------------------
# HF scorer
# ---------------------------------------------------------------------------
class HFNLIScorer:
    """Batched CPU NLI cross-encoder with a cache keyed on (premise, hypothesis)."""

    def __init__(self, model_id: str, batch_size: int = 8):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_id, use_safetensors=True).eval()
        l2i = {k.lower(): v for k, v in self.model.config.label2id.items()}
        self.idx = {k: l2i[k] for k in ("entailment", "neutral", "contradiction")}
        self.model_id = model_id
        self.revision = getattr(self.model.config, "_commit_hash", None)
        self.batch_size = batch_size
        self.cache: Dict[Tuple[str, str], Dict[str, float]] = {}
        torch.set_num_threads(max(1, torch.get_num_threads()))

    def __call__(self, pairs: Sequence[Tuple[str, str]]) -> List[Dict[str, float]]:
        todo = [p for p in dict.fromkeys(pairs) if p not in self.cache]
        for i in range(0, len(todo), self.batch_size):
            batch = todo[i:i + self.batch_size]
            x = self.tok([p for p, _ in batch], [h for _, h in batch], return_tensors="pt",
                         truncation="only_first", max_length=512, padding=True)
            with self.torch.no_grad():
                probs = self.model(**x).logits.softmax(-1).numpy()
            for pair, pr in zip(batch, probs):
                self.cache[pair] = {k: float(pr[j]) for k, j in self.idx.items()}
        return [self.cache[p] for p in pairs]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strip(recs: List[dict], key: str) -> List[dict]:
    keep = ("variant_id", "call", "citation", "resolved_id", "match", "imprecise",
            "source", "alignment", key)
    out = []
    for r in recs:
        d = {k: r[k] for k in keep if k in r}
        s = r.get(key + "_scores")
        if s:
            d.update({"p_entail": s["max_entailment"], "p_contradict": s["max_contradiction"],
                      "best_hypothesis": s["best_hypothesis"]})
        out.append(d)
    return out


def run_arm(name: str, recs: List[dict], scorer: Scorer, crosstab: bool) -> dict:
    score_records(recs, scorer)
    arm = {"n_citations_total": len(recs),
           "n_not_testable": sum(1 for r in recs if not r.get("label")),
           "aggregate": aggregate(recs)}
    if "alignment" in recs[0]:
        arm["by_alignment"] = {a: aggregate([r for r in recs if r["alignment"] == a])
                               for a in ("inline", "max_over_rationale")}
    arm["by_source"] = {s: aggregate([r for r in recs if r.get("source") == s])
                        for s in sorted({r.get("source") for r in recs if r.get("source")})}
    if crosstab:
        arm["match_types"] = dict(Counter(r["match"] for r in recs))
        arm["imprecision_crosstab"] = imprecision_crosstab(recs)
        arm["not_testable_reasons"] = dict(Counter(
            "unresolvable token" if not r.get("premise") else "VUS call (no template)"
            for r in recs if not r.get("label")))
    arm["hand_inspection_sample"] = hand_sample(recs)
    arm["records"] = _strip(recs, "label")
    return arm


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=PRIMARY_MODEL)
    ap.add_argument("--sensitivity-model", default=SENSITIVITY_MODEL)
    ap.add_argument("--no-sensitivity", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    cohort_vs = json.load(open(COHORT))["variants"]
    cohort = {_vid(v): v for v in cohort_vs}
    lo_results = json.load(open(LABEL_ONLY))["results"]

    primary = HFNLIScorer(args.model)
    arms = {
        "pipeline_rationale_arm": run_arm(
            "pipeline", pipeline_records(cohort_vs, "header+statement"), primary, False),
        "label_only_106_arm": run_arm(
            "label_only", label_only_records(lo_results, cohort, "header+statement"),
            primary, True),
    }

    def headline(recs_fn, scorer) -> dict:
        recs = recs_fn()
        score_records(recs, scorer)
        agg = aggregate(recs)
        res = {"counts": agg["counts"], "n": agg["n_citations"],
               "supported": agg["citation_level"]["supported"]["iid"],
               "contradicted": agg["citation_level"]["contradicted"]["iid"]}
        if recs and "imprecise" in recs[0]:
            res["imprecision_crosstab"] = imprecision_crosstab(recs)
        return res

    sens: dict = {"premise_statement_only__primary_model": {
        "pipeline_rationale_arm": headline(
            lambda: pipeline_records(cohort_vs, "statement"), primary),
        "label_only_106_arm": headline(
            lambda: label_only_records(lo_results, cohort, "statement"), primary)}}
    models = [{"role": "primary", "id": primary.model_id, "revision": primary.revision}]
    if not args.no_sensitivity:
        base = HFNLIScorer(args.sensitivity_model)
        models.append({"role": "sensitivity", "id": base.model_id, "revision": base.revision})
        sens["sensitivity_model__header+statement"] = {
            "pipeline_rationale_arm": headline(
                lambda: pipeline_records(cohort_vs, "header+statement"), base),
            "label_only_106_arm": headline(
                lambda: label_only_records(lo_results, cohort, "header+statement"), base)}

    report = {
        "purpose": "Type II attribution audit: does each in-bundle cited item entail the "
                   "claim that cites it? Zero LLM API calls.",
        "provenance": {
            "models": models,
            "decision_rule": {"entail_threshold": ENTAIL_T, "contradict_threshold": CONTRA_T,
                              "rule": "supported if max P(entail)>=0.5, else contradicted if "
                                      "max P(contradict)>=0.5, else neutral; max over premise "
                                      "chunks x candidate claim sentences; fixed a priori",
                              "chunk_words": CHUNK_WORDS, "max_length_tokens": 512},
            "premise_primary": "header+statement (item's own gene/variant/disease/type/"
                               "direction/significance fields + statement)",
            "label_only_templates": {"Oncogenic|Likely Oncogenic": ONC_TEMPLATE,
                                     "Benign|Likely Benign": BEN_TEMPLATE,
                                     "VUS": "not testable (no template)"},
            "bootstrap": {"n_boot": N_BOOT, "seed": 0, "method": "percentile; iid over "
                          "citations (src.eval.stats.bootstrap_ci) + variant-clustered"},
            "inputs": {str(COHORT): _sha(COHORT), str(LABEL_ONLY): _sha(LABEL_ONLY)},
            "llm_api_calls": 0,
        },
        "arms": arms,
        "no_retrieval_arm": {"audited": False, "reason": "its citations (e.g. 'ClinGen: "
                             "BRAF') resolve to no evidence item with text; no offline "
                             "premise exists"},
        "sensitivity": sens,
        "caveats": [
            "NLI models are trained on general-domain text; short clinical evidence "
            "snippets and templated claims make scores noisy.",
            "label_only_106_arm has no rationale; its claim is the emitted label rendered "
            "by an a-priori template, so it tests label-level support, not sentence-level.",
            "max_over_rationale alignment picks the best of all rationale sentences and is "
            "an optimistic upper bound on support.",
            "'neutral' means the NLI model did not find entailment; it is not proof the "
            "citation is wrong (e.g. computational scores vs 'oncogenic' claims).",
            "'contradicted' is the least reliable label: the model scores 'AlphaMissense "
            "predicts X as pathogenic' as contradicting 'X is an oncogenic mutation' "
            "(see by_source), and under max_over_rationale the max contradiction can come "
            "from a sentence unrelated to the cited item. Read contradicted rows by hand "
            "before treating any as a real contradiction.",
            "Scoring is per cited item; a sentence that conjoins facts from two co-cited "
            "items (e.g. a cohort size from one, a hazard ratio from another) is not "
            "entailed by either alone, which biases 'supported' downward.",
            "Rationale sentences often append an inference ('..., supporting its oncogenic "
            "role') that no evidence item states; NLI then withholds entailment even when "
            "the factual clause is supported, again biasing 'supported' downward.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2))
    tmp.replace(args.out)

    for name, arm in arms.items():
        agg = arm["aggregate"]
        s = agg["citation_level"]
        print(f"[{name}] n={agg['n_citations']} (not testable {arm['n_not_testable']}) "
              f"counts={agg['counts']}")
        for lab in ("supported", "neutral", "contradicted"):
            c = s[lab]["iid"]
            print(f"   {lab:12s} {c['point']} [{c['lo']}, {c['hi']}]")
        if "imprecision_crosstab" in arm:
            x = arm["imprecision_crosstab"]
            print(f"   crosstab {x['table']} agreement={x['percent_agreement']} "
                  f"kappa={x['cohens_kappa']}")
    print(f"[+] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
