"""Input-context ablation — is interpretation invariant to how the variant is written?

A variant reaches this system as a gene symbol plus a protein change, and both
are written differently by different sources: a legacy pathology report says
HER2 where HGNC says ERBB2, some pipelines emit ``p.Val600Glu`` where others
emit ``p.V600E``, older tools write ``p.R130X`` for what HGVS calls ``p.R130*``,
and the same genomic change annotated against a different transcript lands on a
different residue number. None of the first three should change the answer. The
fourth should not be silently accepted, because it denotes a different residue.

This ablation applies each perturbation to the input and measures what moves.
It is structured in two parts:

* **Retrieval sweep (no LLM, exhaustive).** Every cohort variant is re-retrieved
  under every HGNC alternative symbol for its gene, and under each notation
  perturbation. This is deterministic and free, so it covers every alternative
  rather than a sample. It answers: does the evidence bundle survive?
* **Classification arm (LLM).** One deterministic perturbation per class is run
  through Generative-mode classification at temperature 0, to answer the
  question the retrieval sweep cannot: when the bundle degrades, does the system
  abstain safely, or does it fall back on parametric knowledge and issue a
  confident call anyway?

The second question is the safety-relevant one. A terminology mismatch that
produces an honest abstention is a recall failure; one that produces a confident
oncogenic call on evidence the system never actually retrieved is a faithfulness
failure, and a far more serious one.

Usage::

    python -m scripts.run_context_ablation --no-llm     # retrieval sweep only, offline
    python -m scripts.run_context_ablation              # full; needs OPENAI_API_KEY
    python -m scripts.run_context_ablation --limit 10   # bound the cost while developing
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ALIASES = Path("data/knowledge/gene_aliases.json")
OUT = Path("data/outputs/context_ablation.json")
#: Per-variant checkpoint. A full run is a few hundred model calls, long enough
#: that an interrupted run is a real possibility; each finished variant is
#: appended here immediately so a restart resumes instead of starting over.
CHECKPOINT = Path("data/outputs/context_ablation.partial.jsonl")

#: Residue offset used by the synthetic transcript-numbering perturbation.
#: The real phenomenon is that one genomic change maps to different residue
#: numbers on different transcripts (CDKN2A p16INK4a versus p14ARF being the
#: textbook case). We emulate it with a fixed offset rather than re-annotating
#: against alternative transcripts, so this arm is explicitly SYNTHETIC: it
#: tests whether a wrong residue number is caught, not how often one occurs.
TRANSCRIPT_OFFSET = 12

AA3 = {
    "A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys", "Q": "Gln",
    "E": "Glu", "G": "Gly", "H": "His", "I": "Ile", "L": "Leu", "K": "Lys",
    "M": "Met", "F": "Phe", "P": "Pro", "S": "Ser", "T": "Thr", "W": "Trp",
    "Y": "Tyr", "V": "Val", "*": "Ter",
}

MISSENSE = re.compile(r"^p\.([A-Z])(\d+)([A-Z])$")
NONSENSE = re.compile(r"^p\.([A-Z])(\d+)\*$")
ANY_POS = re.compile(r"^p\.([A-Z])(\d+)(.*)$")


# --------------------------------------------------------------------------- #
# Perturbations. Each returns the perturbed hgvsp/gene, or None when it does
# not apply to that variant form (excluded from that arm's denominator).
# --------------------------------------------------------------------------- #
def perturb_case_lower(gene: str, hgvsp: str) -> Optional[Tuple[str, str]]:
    """Negative control: lowercase the symbol. Lookups upper-case, so invariant."""
    return gene.lower(), hgvsp


def perturb_three_letter(gene: str, hgvsp: str) -> Optional[Tuple[str, str]]:
    """p.V600E -> p.Val600Glu; p.R130* -> p.Arg130Ter. Both are valid HGVS."""
    m = MISSENSE.match(hgvsp)
    if m:
        ref, pos, alt = m.groups()
        if ref in AA3 and alt in AA3:
            return gene, f"p.{AA3[ref]}{pos}{AA3[alt]}"
        return None
    m = NONSENSE.match(hgvsp)
    if m:
        ref, pos = m.groups()
        if ref in AA3:
            return gene, f"p.{AA3[ref]}{pos}Ter"
    return None


def perturb_legacy_stop(gene: str, hgvsp: str) -> Optional[Tuple[str, str]]:
    """p.R130* -> p.R130X, the pre-HGVS nonsense notation still seen in reports."""
    m = NONSENSE.match(hgvsp)
    return (gene, f"p.{m.group(1)}{m.group(2)}X") if m else None


def perturb_transcript_shift(gene: str, hgvsp: str) -> Optional[Tuple[str, str]]:
    """Shift the residue number, emulating a different transcript's numbering.

    Unlike the others this SHOULD change the answer: it names a different
    residue. Correct behaviour is to find no evidence and abstain.
    """
    m = ANY_POS.match(hgvsp)
    if not m:
        return None
    ref, pos, tail = m.groups()
    return gene, f"p.{ref}{int(pos) + TRANSCRIPT_OFFSET}{tail}"


NOTATION_ARMS = {
    "case_lower": perturb_case_lower,
    "three_letter": perturb_three_letter,
    "legacy_stop": perturb_legacy_stop,
    "transcript_shift": perturb_transcript_shift,
}

#: Arms whose output must match the baseline exactly. ``transcript_shift`` is
#: excluded: it denotes a different residue, so a change there is correct.
INVARIANCE_ARMS = ["case_lower", "alias", "three_letter", "legacy_stop"]


def load_aliases() -> Dict[str, dict]:
    if not ALIASES.exists():
        raise SystemExit(f"missing {ALIASES}; run `python -m scripts.fetch_gene_aliases` first")
    return json.loads(ALIASES.read_text())["genes"]


def alternative_symbols(rec: dict) -> List[str]:
    """All HGNC alternatives: withdrawn previous symbols first, then aliases."""
    seen, out = set(), []
    for s in list(rec.get("prev_symbol", [])) + list(rec.get("alias_symbol", [])):
        if s and s.upper() not in seen:
            seen.add(s.upper())
            out.append(s)
    return out


def primary_alias(rec: dict) -> Optional[str]:
    """The single alias used in the LLM arm (deterministic: first alternative)."""
    alts = alternative_symbols(rec)
    return alts[0] if alts else None


# --------------------------------------------------------------------------- #
#: Sources keyed on the gene symbol / protein-change text, which a symbol or
#: notation perturbation can therefore break. AlphaMissense is deliberately not
#: here: it is keyed on genomic coordinates, which no perturbation touches.
TEXT_KEYED_SOURCES = {"CIViC"}


def _bundle_summary(bundle) -> dict:
    by_source: Dict[str, List[str]] = defaultdict(list)
    for e in bundle.evidences:
        by_source[e.source].append(e.id)
    clinical = [e.id for e in bundle.evidences if e.source in TEXT_KEYED_SOURCES]
    return {
        "n_evidence": len(bundle.evidences),
        "n_clinical_evidence": len(clinical),
        "ids": sorted(e.id for e in bundle.evidences),
        "clinical_ids": sorted(clinical),
        "by_source": {k: sorted(v) for k, v in sorted(by_source.items())},
        "n_drugs": len(bundle.drugs),
        "n_trials": len(bundle.trials),
    }


def _jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def _fingerprint(result) -> dict:
    return {
        "oncogenicity": result.oncogenicity.value,
        "tier": result.tier.value,
        "abstained": bool(result.abstained),
        "citations": sorted(result.citations),
    }


def _grounding(fingerprint: dict, ids: List[str]) -> dict:
    """Were the cited identifiers actually in the bundle the model was shown?

    Recorded per arm at run time because the bundle is not kept in the output:
    without this, the claim that no ablation citation fell outside its bundle
    cannot be recomputed from the report. This arm calls the classifier
    directly, so no faithfulness gate has filtered the citations first and the
    check is a measurement rather than a restatement of the contract.
    """
    available = set(ids)
    outside = [c for c in fingerprint["citations"] if c not in available]
    return {
        "n_citations": len(fingerprint["citations"]),
        "n_outside_bundle": len(outside),
        "outside_bundle": sorted(outside),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-llm", action="store_true", help="retrieval sweep only (offline, free)")
    ap.add_argument("--limit", type=int, default=None, help="use at most N cohort variants")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--checkpoint", type=Path, default=CHECKPOINT)
    ap.add_argument("--restart", action="store_true",
                    help="discard the checkpoint and re-run every variant")
    args = ap.parse_args()

    from dotenv import load_dotenv

    from src.classify.llm import LLMClassifier
    from src.classify.select import select_for_classification
    from src.cohort.loader import load_cohort
    from src.knowledge.factory import build_aggregator
    from src.pipeline import ENV_PATH, build_retriever
    from src.provenance import build_provenance
    from src.retrieval.graph import KnowledgeGraph

    load_dotenv(ENV_PATH, override=True)
    aliases = load_aliases()

    agg = build_aggregator(offline=True)
    selected = select_for_classification(agg, load_cohort())
    if args.limit:
        selected = selected[:args.limit]
    kg = KnowledgeGraph.from_civic()
    retriever = build_retriever(agg=agg, kg=kg)

    llm = LLMClassifier()
    use_llm = not args.no_llm
    if use_llm and not llm.available():
        raise SystemExit("OPENAI_API_KEY not set; pass --no-llm for the retrieval sweep only")

    # Resume: read the checkpoint first, then only run what is missing. Rows are
    # keyed by gene/protein-change/cancer so a re-run cannot duplicate or reorder.
    done: Dict[str, dict] = {}
    if args.restart and args.checkpoint.exists():
        args.checkpoint.unlink()
    elif args.checkpoint.exists():
        for line in args.checkpoint.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done[f"{r['gene']}|{r['hgvsp']}|{r['cancer_type']}"] = r
        print(f"[*] resuming: {len(done)} variant(s) already in {args.checkpoint}", flush=True)

    print(f"[*] {len(selected)} variants · retrieval sweep over all HGNC alternatives"
          + (" + LLM classification arm" if use_llm else " (no LLM)"), flush=True)

    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    for i, s in enumerate(selected, 1):
        v = s.variant
        ckey = f"{v.gene}|{v.hgvsp}|{v.cancer_type}"
        if ckey in done:
            rows.append(done[ckey])
            print(f"    {i}/{len(selected)} {ckey} (cached)", flush=True)
            continue
        rec = aliases.get(v.gene.upper())
        base_ret = retriever.retrieve(v)
        base = _bundle_summary(base_ret.bundle)
        row = {
            "gene": v.gene, "hgvsp": v.hgvsp, "cancer_type": v.cancer_type,
            "evidence_tier": s.tier,
            "baseline": base,
            "alias_sweep": [],
            "arms": {},
        }
        if use_llm:
            row["baseline"]["classification"] = _fingerprint(
                llm.classify(v, base_ret.bundle, base_ret.graph, temperature=0.0))
            row["baseline"]["citation_grounding"] = _grounding(
                row["baseline"]["classification"], base["ids"])

        # --- exhaustive alias sweep (retrieval only, free) ------------------ #
        for alt in (alternative_symbols(rec) if rec else []):
            pv = v.model_copy(update={"gene": alt})
            pb = _bundle_summary(retriever.retrieve(pv).bundle)
            row["alias_sweep"].append({
                "symbol": alt,
                "n_evidence": pb["n_evidence"],
                "n_clinical_evidence": pb["n_clinical_evidence"],
                "jaccard": round(_jaccard(base["ids"], pb["ids"]), 4),
                "clinical_jaccard": round(_jaccard(base["clinical_ids"], pb["clinical_ids"]), 4),
                "clinical_collapsed": bool(base["n_clinical_evidence"] and not pb["n_clinical_evidence"]),
                "n_drugs": pb["n_drugs"],
                "by_source": pb["by_source"],
            })

        # --- one deterministic perturbation per arm ------------------------- #
        arms: Dict[str, Optional[Tuple[str, str]]] = {
            name: fn(v.gene, v.hgvsp) for name, fn in NOTATION_ARMS.items()
        }
        alias_pick = primary_alias(rec) if rec else None
        arms["alias"] = (alias_pick, v.hgvsp) if alias_pick else None

        for name, pert in arms.items():
            if pert is None:
                row["arms"][name] = {"applicable": False}
                continue
            g2, p2 = pert
            pv = v.model_copy(update={"gene": g2, "hgvsp": p2})
            pret = retriever.retrieve(pv)
            pb = _bundle_summary(pret.bundle)
            entry = {
                "applicable": True,
                "input": f"{g2} {p2}",
                "n_evidence": pb["n_evidence"],
                "n_clinical_evidence": pb["n_clinical_evidence"],
                "jaccard": round(_jaccard(base["ids"], pb["ids"]), 4),
                "clinical_jaccard": round(_jaccard(base["clinical_ids"], pb["clinical_ids"]), 4),
                "by_source": pb["by_source"],
                "n_drugs": pb["n_drugs"],
                "evidence_collapsed": bool(base["n_evidence"] and not pb["n_evidence"]),
                # The decision-relevant loss: curated clinical evidence gone,
                # even though the coordinate-keyed computational prior remains.
                "clinical_collapsed": bool(base["n_clinical_evidence"] and not pb["n_clinical_evidence"]),
                "prior_only_after": bool(pb["n_evidence"] and not pb["n_clinical_evidence"]),
            }
            if use_llm:
                entry["classification"] = _fingerprint(
                    llm.classify(pv, pret.bundle, pret.graph, temperature=0.0))
                entry["citation_grounding"] = _grounding(entry["classification"], pb["ids"])
            row["arms"][name] = entry

        rows.append(row)
        # Append-only: a finished variant is durable before the next one starts.
        with args.checkpoint.open("a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        print(f"    {i}/{len(selected)} {ckey}", flush=True)

    report = {
        "provenance": build_provenance(
            live=use_llm,
            model_name=llm.model if use_llm else None,
            n_variants=len(rows),
            techniques=["dense-RAG", "single-pass", "temperature=0", "input-context-ablation"],
            retrieval_index=retriever.index_fingerprint(),
        ).model_dump(mode="json"),
        "design": {
            "transcript_offset": TRANSCRIPT_OFFSET,
            "invariance_arms": INVARIANCE_ARMS,
            "detection_arms": ["transcript_shift"],
            "alias_source": "HGNC REST (data/knowledge/gene_aliases.json)",
            "note": ("transcript_shift is a SYNTHETIC residue offset emulating a different "
                     "transcript's numbering; it is not a re-annotation against real "
                     "alternative transcripts."),
        },
        "summary": summarise(rows, use_llm),
        "variants": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"[+] wrote {args.out}")
    print_summary(report["summary"], use_llm)
    return 0


# --------------------------------------------------------------------------- #
def summarise(rows: List[dict], use_llm: bool) -> dict:
    """Aggregate the per-variant rows into the numbers the manuscript reports."""
    out: dict = {"n_variants": len(rows), "arms": {}}

    with_ev = [r for r in rows if r["baseline"]["n_clinical_evidence"] > 0]
    out["n_with_baseline_clinical_evidence"] = len(with_ev)

    # Exhaustive alias sweep, scored on curated clinical (CIViC) evidence: the
    # coordinate-keyed AlphaMissense prior survives every perturbation by
    # construction, so counting it would mask the loss that matters.
    sweep_total = sweep_lost = 0
    sweep_by_gene: Dict[str, dict] = {}
    for r in with_ev:
        agg = sweep_by_gene.setdefault(r["gene"], {"n_symbol_tests": 0, "n_clinical_collapsed": 0})
        for a in r["alias_sweep"]:
            sweep_total += 1
            agg["n_symbol_tests"] += 1
            if a["clinical_collapsed"]:
                sweep_lost += 1
                agg["n_clinical_collapsed"] += 1
    out["alias_sweep"] = {
        "n_symbol_tests": sweep_total,
        "n_clinical_evidence_collapsed": sweep_lost,
        "clinical_collapse_rate": round(sweep_lost / sweep_total, 4) if sweep_total else None,
        "by_gene": sweep_by_gene,
    }

    for arm in list(NOTATION_ARMS) + ["alias"]:
        appl = [r for r in rows if r["arms"].get(arm, {}).get("applicable")]
        appl_ev = [r for r in appl if r["baseline"]["n_clinical_evidence"] > 0]
        stats = {
            "n_applicable": len(appl),
            "n_applicable_with_clinical_evidence": len(appl_ev),
            "n_clinical_collapsed": sum(1 for r in appl_ev if r["arms"][arm]["clinical_collapsed"]),
            "n_prior_only_after": sum(1 for r in appl_ev if r["arms"][arm]["prior_only_after"]),
            "mean_clinical_jaccard": (
                round(sum(r["arms"][arm]["clinical_jaccard"] for r in appl_ev) / len(appl_ev), 4)
                if appl_ev else None),
        }
        if use_llm:
            flips_onco = flips_tier = flips_abst = 0
            unsafe, safe_abstain = 0, 0
            for r in appl:
                b, p = r["baseline"].get("classification"), r["arms"][arm].get("classification")
                if not b or not p:
                    continue
                flips_onco += b["oncogenicity"] != p["oncogenicity"]
                flips_tier += b["tier"] != p["tier"]
                flips_abst += b["abstained"] != p["abstained"]
                if r["arms"][arm].get("clinical_collapsed"):
                    # After losing all curated clinical evidence, did the system
                    # still assert a driver? That is the faithfulness-relevant
                    # failure; an abstention here is the safe outcome.
                    if p["oncogenicity"] in ("Oncogenic", "Likely Oncogenic"):
                        unsafe += 1
                    else:
                        safe_abstain += 1
            n = len(appl)
            stats.update({
                "oncogenicity_flips": flips_onco,
                "tier_flips": flips_tier,
                "abstention_flips": flips_abst,
                "oncogenicity_flip_rate": round(flips_onco / n, 4) if n else None,
                "driver_calls_after_clinical_loss": unsafe,
                "safe_downgrades_after_clinical_loss": safe_abstain,
            })
        out["arms"][arm] = stats

    if use_llm:
        # Summed over the arms only. The baseline is reported separately because
        # it is the un-perturbed reference, and rows carried over from a
        # checkpoint written before this field existed are counted as missing
        # rather than as zero, so a partial resume cannot read as a clean run.
        n_cit = n_out = n_missing = 0
        for r in rows:
            for name, entry in r["arms"].items():
                if not entry.get("applicable") or not entry.get("classification"):
                    continue
                cg = entry.get("citation_grounding")
                if cg is None:
                    n_missing += 1
                    continue
                n_cit += cg["n_citations"]
                n_out += cg["n_outside_bundle"]
        base_cg = [r["baseline"].get("citation_grounding") for r in rows]
        out["citation_grounding"] = {
            "arms": {"n_citations": n_cit, "n_outside_bundle": n_out},
            "baseline": {
                "n_citations": sum(c["n_citations"] for c in base_cg if c),
                "n_outside_bundle": sum(c["n_outside_bundle"] for c in base_cg if c),
            },
            "n_classifications_without_record": n_missing,
        }
    return out


def print_summary(s: dict, use_llm: bool) -> None:
    sw = s["alias_sweep"]
    print(f"\n  variants: {s['n_variants']} ({s['n_with_baseline_clinical_evidence']} with curated "
          f"clinical evidence at baseline)")
    print(f"  HGNC alias sweep: {sw['n_clinical_evidence_collapsed']}/{sw['n_symbol_tests']} symbol tests "
          f"lost ALL curated clinical evidence (rate {sw['clinical_collapse_rate']})")
    hdr = f"  {'arm':18s} {'appl':>5s} {'clinLost':>9s} {'priorOnly':>10s} {'meanJ':>7s}"
    if use_llm:
        hdr += f" {'oncoFlip':>9s} {'tierFlip':>9s} {'abstFlip':>9s} {'driver!':>8s} {'safe':>5s}"
    print(hdr)
    for arm, st in s["arms"].items():
        line = (f"  {arm:18s} {st['n_applicable']:5d} {st['n_clinical_collapsed']:9d} "
                f"{st['n_prior_only_after']:10d} {str(st['mean_clinical_jaccard']):>7s}")
        if use_llm:
            line += (f" {st.get('oncogenicity_flips', 0):9d} {st.get('tier_flips', 0):9d}"
                     f" {st.get('abstention_flips', 0):9d}"
                     f" {st.get('driver_calls_after_clinical_loss', 0):8d}"
                     f" {st.get('safe_downgrades_after_clinical_loss', 0):5d}")
        print(line)
    cg = s.get("citation_grounding")
    if cg:
        print(f"  citations outside the retrieved bundle: "
              f"{cg['arms']['n_outside_bundle']} of {cg['arms']['n_citations']} (arms), "
              f"{cg['baseline']['n_outside_bundle']} of {cg['baseline']['n_citations']} (baseline)")
        if cg["n_classifications_without_record"]:
            print(f"  [!] {cg['n_classifications_without_record']} classification(s) carried over "
                  f"from an older checkpoint with no grounding record")


if __name__ == "__main__":
    sys.exit(main())
