"""Ablation: rule-only vs LLM-no-retrieval vs LLM+retrieval (Phase b).

Reuses rule + LLM+retrieval from the existing cohort_interpretation.json and adds
a fresh LLM-no-retrieval (parametric) pass for the SAME variants, then reports:
  * tier accuracy vs the CIViC-assertion benchmark (small),
  * inter-method agreement (Cohen's kappa),
  * faithfulness — the no-RAG arm cannot ground citations.

Run:  python -m scripts.run_ablation
Output: data/outputs/ablation_report.json
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.models import Variant
from src.classify.llm import LLMClassifier
from src.eval.metrics import cohens_kappa
from src.eval.benchmark import load_truth

RESULT = Path("data/outputs/cohort_interpretation.json")
OUT = Path("data/outputs/ablation_report.json")
ENV = Path(__file__).resolve().parent.parent / ".env"


def _acc(preds, truth_keyed):
    matched = [(k, t) for k, t in truth_keyed.items() if k in preds]
    if not matched:
        return None, 0
    return round(sum(preds[k] == t for k, t in matched) / len(matched), 3), len(matched)


def main():
    load_dotenv(ENV, override=True)
    if not RESULT.exists():
        print(f"[!] {RESULT} not found.")
        return 1
    data = json.loads(RESULT.read_text())
    variants = data["variants"]
    llm = LLMClassifier()
    if not llm.available():
        print("[!] OPENAI_API_KEY missing — cannot run the no-retrieval arm.")
        return 1

    print(f"[*] LLM-no-retrieval pass over {len(variants)} variants…")
    rows = []
    for i, v in enumerate(variants, 1):
        var = Variant(chrom="", pos=0, ref="", alt="", gene=v["gene"], hgvsp=v["hgvsp"],
                      cancer_type=v["cancer_type"], variant_type=v["variant_type"])
        try:
            p = llm.classify_parametric(var)
            rows.append({"variant_key": v["variant_key"], "gene": v["gene"], "hgvsp": v["hgvsp"],
                         "rule": (v["mode_b"]["oncogenicity"], v["mode_b"]["tier"]),
                         "llm_rag": (v["mode_a"]["oncogenicity"], v["mode_a"]["tier"]),
                         "llm_norag": (p.oncogenicity.value, p.tier.value),
                         "norag_citations": p.citations})
        except Exception as e:  # noqa: BLE001
            print(f"    [!] {v['variant_key']}: {e}")
        if i % 10 == 0:
            print(f"    {i}/{len(variants)}")

    def key(r):
        hg = r["hgvsp"][2:] if r["hgvsp"].startswith("p.") else r["hgvsp"]
        return (r["gene"].upper(), hg.upper())

    truth = load_truth()
    a_rule = {key(r): r["rule"][1] for r in rows}
    a_rag = {key(r): r["llm_rag"][1] for r in rows}
    a_norag = {key(r): r["llm_norag"][1] for r in rows}

    # no-RAG arm cannot legitimately cite evidence — count any citations as ungrounded.
    norag_with_cites = sum(1 for r in rows if r["norag_citations"])

    report = {
        "n": len(rows),
        "tier_accuracy_vs_civic": {
            "rule_only": _acc(a_rule, truth)[0],
            "llm_no_retrieval": _acc(a_norag, truth)[0],
            "llm_with_retrieval": _acc(a_rag, truth)[0],
            "n_matched": _acc(a_rag, truth)[1],
        },
        "tier_kappa": {
            "norag_vs_rag": cohens_kappa([r["llm_norag"][1] for r in rows], [r["llm_rag"][1] for r in rows]),
            "rule_vs_rag": cohens_kappa([r["rule"][1] for r in rows], [r["llm_rag"][1] for r in rows]),
        },
        "oncogenicity_kappa": {
            "norag_vs_rag": cohens_kappa([r["llm_norag"][0] for r in rows], [r["llm_rag"][0] for r in rows]),
        },
        "faithfulness": {
            "norag_ungrounded_citations": norag_with_cites,
            "note": "no-retrieval arm has no evidence bundle, so any citation it emits is ungrounded.",
        },
        "rows": rows,
    }
    OUT.write_text(json.dumps(report, indent=2))
    t = report["tier_accuracy_vs_civic"]
    print(f"[+] tier accuracy vs CIViC (n={t['n_matched']}): rule={t['rule_only']} "
          f"no-RAG={t['llm_no_retrieval']} RAG={t['llm_with_retrieval']}")
    print(f"[+] tier kappa: noRAG-vs-RAG={report['tier_kappa']['norag_vs_rag']} "
          f"rule-vs-RAG={report['tier_kappa']['rule_vs_rag']}")
    print(f"[+] no-RAG ungrounded citations: {norag_with_cites}/{len(rows)}")
    print(f"[+] wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
