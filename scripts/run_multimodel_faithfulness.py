#!/usr/bin/env python3
"""Multi-model faithfulness ensembling (method A) over a FIXED evidence set.

Runs several open-weight LLMs as independent *raters* over each variant's already
retrieved evidence bundle (no re-retrieval, no tool-calling), then:
  - cross-model agreement on the call AND the cited evidence IDs -> calibrated confidence;
  - disagreement (or majority-VUS) -> abstain to VUS;
  - optional NLI attribution gate (each oncogenic call must be entailed by a cited passage);
  - risk-coverage curve when gold labels are present.

This inverts Ferber et al.'s negative result: open models are unreliable as agent
*drivers*, but fine as *raters* over fixed evidence — and agreement becomes a
faithfulness/abstention signal. Nothing here is run for the manuscript yet.

Backends (all OpenAI-compatible chat):
  mock    no deps/network — replays committed mode_a with deterministic variation (plumbing only)
  ollama  local CPU/GPU via Ollama   (base_url http://localhost:11434/v1)
  vllm    GPU via a vLLM server      (base_url http://localhost:8000/v1)
  hosted  OpenRouter/Together/etc.   (base_url + --api-key-env)

Offline smoke test (no models, no GPU, no network):
  python -m scripts.run_multimodel_faithfulness --backend mock --limit 5 --no-nli

Real local (CPU) via Ollama:
  ollama pull llama3.1:8b && ollama pull mistral:7b && ollama pull qwen2.5:7b
  python -m scripts.run_multimodel_faithfulness --backend ollama \
      --models llama3.1:8b mistral:7b qwen2.5:7b --limit 10

GPU via vLLM (serve a 70B), or hosted (OpenRouter):
  python -m scripts.run_multimodel_faithfulness --backend vllm \
      --models meta-llama/Llama-3.1-70B-Instruct --base-url http://localhost:8000/v1
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "data", "outputs")

ONC = ["Oncogenic", "Likely Oncogenic", "VUS", "Likely Benign", "Benign"]
TIERS = ["Tier I", "Tier II", "Tier III", "Tier IV"]
# Validated instrument (tuned with a negative control: real cite vs mismatched cite).
# large + "pathogenic cancer mutation" -> support 0.83 on real, 0.03 on mismatched.
NLI_MODEL = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
NLI_HYPOTHESIS = "{gene} {hgvsp} is a pathogenic cancer mutation."


def collapse3(label):
    if label in ("Oncogenic", "Likely Oncogenic"):
        return "ONC"
    if label in ("Benign", "Likely Benign"):
        return "BEN"
    return "VUS"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_variants(path, limit):
    d = json.load(open(path))
    rows = d["variants"] if isinstance(d, dict) and "variants" in d else (
        d if isinstance(d, list) else list(d.values())[0])
    if limit:
        rows = rows[:limit]
    return rows


def evidence_block(bundle, max_items=20):
    evs = (bundle or {}).get("evidences", [])[:max_items]
    lines, ids = [], []
    for e in evs:
        eid = e.get("id", "")
        ids.append(eid)
        dis = f" [{e.get('disease')}]" if e.get("disease") else ""
        lines.append(f"- {eid}{dis}: {e.get('statement', '')[:200]}")
    return "\n".join(lines) if lines else "(no variant-specific evidence)", ids


PROMPT_SYS = (
    "You are a somatic variant interpreter. Classify ONLY from the evidence provided. "
    f"oncogenicity must be one of {ONC}. tier must be one of {TIERS}. "
    "Cite ONLY evidence IDs that appear in the list. If no variant-specific evidence "
    "supports an oncogenic call, return VUS with an empty cited_ids list. "
    'Respond with ONLY a JSON object: '
    '{"oncogenicity": "...", "tier": "...", "cited_ids": ["..."]}'
)


def build_user(v, ev_text):
    return (f"Variant: {v.get('gene')} {v.get('hgvsp')} in {v.get('cancer_type')}\n"
            f"Evidence:\n{ev_text}\n\nReturn the JSON now.")


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------
def make_client(backend, base_url, api_key_env):
    if backend == "mock":
        return None
    from openai import OpenAI
    if backend == "ollama":
        return OpenAI(base_url=base_url or "http://localhost:11434/v1", api_key="ollama")
    if backend == "vllm":
        return OpenAI(base_url=base_url or "http://localhost:8000/v1", api_key="EMPTY")
    if backend == "hosted":
        key = os.environ.get(api_key_env, "")
        if not key:
            sys.exit(f"[!] hosted backend needs env var {api_key_env}")
        return OpenAI(base_url=base_url or "https://openrouter.ai/api/v1", api_key=key)
    sys.exit(f"unknown backend {backend}")


def parse_json(text):
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return None
    onc = obj.get("oncogenicity")
    return {
        "oncogenicity": onc if onc in ONC else "VUS",
        "tier": obj.get("tier") if obj.get("tier") in TIERS else "Tier III",
        "cited_ids": [c for c in obj.get("cited_ids", []) if isinstance(c, str)],
    }


def call_real(client, model, v, ev_text, temperature):
    resp = client.chat.completions.create(
        model=model, temperature=temperature, max_tokens=300,
        messages=[{"role": "system", "content": PROMPT_SYS},
                  {"role": "user", "content": build_user(v, ev_text)}])
    return parse_json(resp.choices[0].message.content) or {
        "oncogenicity": "VUS", "tier": "Tier III", "cited_ids": []}


def call_mock(model, v, valid_ids):
    """Deterministic plumbing stand-in: replays committed mode_a with a per-model
    perturbation that mimics the real low-evidence -> disagreement phenomenon.
    NOT a model output; used only to exercise the ensemble logic offline."""
    a = v.get("mode_a", {}) or {}
    onc = a.get("oncogenicity", "VUS")
    cites = [c for c in (a.get("citations") or []) if c in valid_ids]
    n_ev = v.get("n_evidence", len(valid_ids))
    seed = (sum(map(ord, model)) + sum(map(ord, v.get("variant_key", "")))) % 3
    if seed == 1 and n_ev <= 1:            # a skeptic model abstains on thin evidence
        return {"oncogenicity": "VUS", "tier": "Tier III", "cited_ids": []}
    if seed == 2 and onc == "Likely Oncogenic":
        onc = "Oncogenic"                  # a confident model upgrades
    return {"oncogenicity": onc, "tier": a.get("tier", "Tier III"), "cited_ids": cites}


# ---------------------------------------------------------------------------
# Ensemble + NLI gate
# ---------------------------------------------------------------------------
def ensemble(per_model, abstain_threshold):
    calls3 = [collapse3(r["oncogenicity"]) for r in per_model.values()]
    n = len(calls3)
    winner = max(set(calls3), key=calls3.count)
    agreement = calls3.count(winner) / n
    abstain = agreement < abstain_threshold or winner == "VUS"
    # citations the agreeing models share (faithful, intersected)
    agree_models = [m for m, r in per_model.items() if collapse3(r["oncogenicity"]) == winner]
    cite_sets = [set(per_model[m]["cited_ids"]) for m in agree_models]
    shared = set.intersection(*cite_sets) if cite_sets else set()
    return {
        "ensemble_call": "VUS" if abstain else winner,
        "agreement": round(agreement, 3),
        "confidence": round(agreement, 3),
        "abstained": abstain,
        "shared_citations": sorted(shared),
        "per_model": per_model,
    }


class NLIGate:
    def __init__(self):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.tok = AutoTokenizer.from_pretrained(NLI_MODEL)
        self.model = AutoModelForSequenceClassification.from_pretrained(NLI_MODEL)
        self.entail_idx = self.model.config.label2id.get("entailment", 0)

    def entailed(self, premise, hypothesis):
        import torch
        x = self.tok(premise, hypothesis, return_tensors="pt", truncation=True, max_length=256)
        with torch.no_grad():
            probs = self.model(**x).logits.softmax(-1)[0]
        return float(probs[self.entail_idx])

    def check(self, v, call, cited_ids, bundle):
        """An oncogenic ensemble call should be entailed by >=1 cited passage."""
        if collapse3(call) != "ONC" or not cited_ids:
            return {"gated": False, "max_entailment": None}
        by_id = {e.get("id"): e.get("statement", "") for e in (bundle or {}).get("evidences", [])}
        hyp = NLI_HYPOTHESIS.format(gene=v.get("gene"),
                                    hgvsp=str(v.get("hgvsp", "")).replace("p.", ""))
        scores = [self.entailed(by_id.get(cid, ""), hyp) for cid in cited_ids if by_id.get(cid)]
        mx = max(scores) if scores else 0.0
        return {"gated": mx < 0.5, "max_entailment": round(mx, 3)}


# ---------------------------------------------------------------------------
# Risk-coverage (needs gold)
# ---------------------------------------------------------------------------
def risk_coverage(results, gold_field):
    # ensemble_call is already a 3-class code (ONC/VUS/BEN); gold is a 5-class label.
    items = [(r["confidence"], r["ensemble_call"] == collapse3(r[gold_field]))
             for r in results if r.get(gold_field)]
    if not items:
        return None
    items.sort(key=lambda t: -t[0])
    out = []
    for k in range(1, len(items) + 1):
        sub = items[:k]
        out.append({"coverage": round(k / len(items), 3),
                    "selective_accuracy": round(sum(c for _, c in sub) / k, 3),
                    "confidence_threshold": sub[-1][0]})
    return out


def plot_risk_coverage(curve, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    cov = [p["coverage"] for p in curve]
    acc = [p["selective_accuracy"] for p in curve]
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    ax.plot(cov, acc, "-o", color="#0072B2", ms=3, lw=1.6)
    ax.set_xlabel("Coverage (fraction answered)")
    ax.set_ylabel("Selective accuracy")
    ax.set_ylim(0, 1.02)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    return True


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", default="mock", choices=["mock", "ollama", "vllm", "hosted"])
    ap.add_argument("--models", nargs="+",
                    default=["llama3.1:8b", "mistral:7b", "qwen2.5:7b"])
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    ap.add_argument("--input", default=os.path.join(OUT, "cohort_interpretation.json"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--abstain-threshold", type=float, default=0.66,
                    help="min cross-model agreement to NOT abstain")
    ap.add_argument("--nli", dest="nli", action="store_true", default=True)
    ap.add_argument("--no-nli", dest="nli", action="store_false")
    ap.add_argument("--gold-field", default="gold")
    ap.add_argument("--out", default=os.path.join(OUT, "multimodel_faithfulness.json"))
    args = ap.parse_args()

    models = ["mock-A", "mock-B", "mock-C"] if args.backend == "mock" else args.models
    variants = load_variants(args.input, args.limit)
    client = make_client(args.backend, args.base_url, args.api_key_env)
    gate = NLIGate() if (args.nli and args.backend != "mock") else None
    if args.nli and args.backend == "mock":
        print("[i] NLI gate skipped under mock backend.")

    results = []
    for v in variants:
        ev_text, valid_ids = evidence_block(v.get("bundle", {}))
        per_model = {}
        for m in models:
            if args.backend == "mock":
                per_model[m] = call_mock(m, v, valid_ids)
            else:
                per_model[m] = call_real(client, m, v, ev_text, args.temperature)
        ens = ensemble(per_model, args.abstain_threshold)
        rec = {"variant_key": v.get("variant_key"), "gene": v.get("gene"),
               "hgvsp": v.get("hgvsp"), "cancer_type": v.get("cancer_type"),
               "n_evidence": v.get("n_evidence", len(valid_ids)), **ens}
        if gate is not None:
            rec["nli"] = gate.check(v, ens["ensemble_call"], ens["shared_citations"],
                                    v.get("bundle", {}))
            if rec["nli"]["gated"]:                       # unsupported -> abstain
                rec["ensemble_call"] = "VUS"
                rec["abstained"] = True
        if v.get(args.gold_field):
            rec[args.gold_field] = v[args.gold_field]
        results.append(rec)

    n = len(results)
    abst = sum(r["abstained"] for r in results)
    summary = {
        "backend": args.backend, "models": models, "n_variants": n,
        "abstain_threshold": args.abstain_threshold,
        "abstained": abst, "abstention_rate": round(abst / n, 3) if n else 0.0,
        "mean_agreement": round(sum(r["agreement"] for r in results) / n, 3) if n else 0.0,
        "nli_enabled": gate is not None,
    }
    curve = risk_coverage(results, args.gold_field)
    if curve:
        summary["risk_coverage_points"] = len(curve)
        png = os.path.splitext(args.out)[0] + "_risk_coverage.png"
        summary["risk_coverage_plot"] = png if plot_risk_coverage(curve, png) else None

    report = {"summary": summary, "results": results, "risk_coverage": curve}
    json.dump(report, open(args.out, "w"), indent=2)
    print(json.dumps(summary, indent=2))
    print(f"[*] wrote {args.out}")


if __name__ == "__main__":
    main()
