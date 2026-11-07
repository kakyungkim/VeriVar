#!/usr/bin/env python3
"""Deterministic manuscript verifier — anti-hallucination gate.

Why this exists
---------------
LLMs (including the ones used to draft and to *critique* this paper) fabricate
plausible specifics from parametric memory — the exact failure mode the paper is
about. Re-running an LLM "critic" does not reliably catch its own hallucinations.
This script is the deterministic, no-LLM counter-measure: it recomputes every
headline number from the committed result JSONs and checks that the prose matches,
checks that every variant named in the docs actually exists in the data, scans for
unverified-fact tags, and (optionally, online) resolves every DOI via Crossref.

It is the ground truth that a human, a `paper-critic` pass, or a second engine
(`codex`, see scripts/verify_with_codex.sh) can all defer to. Exit code is non-zero
if any check fails, so it can gate a commit / CI.

Usage
-----
    python -m scripts.verify_manuscript                 # offline checks
    python -m scripts.verify_manuscript --online        # + Crossref DOI resolution
    python -m scripts.verify_manuscript --json report.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "outputs"
BENCH = ROOT / "data" / "benchmark"

PREPRINT = ROOT / "docs" / "manuscript" / "preprint.md"
PREPRINT_KO = ROOT / "docs" / "manuscript" / "preprint_ko.md"
SUMMARY = ROOT / "docs" / "STUDY_SUMMARY.md"
WORKSHEET = ROOT / "notes" / "expert_adjudication_worksheet.md"

ONCO_LEAN = {"Oncogenic", "Likely Oncogenic"}


# --------------------------------------------------------------------------- #
# result-checking infrastructure
# --------------------------------------------------------------------------- #
class Report:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"check": name, "ok": bool(ok), "skipped": False, "detail": detail})

    def skip(self, name: str, detail: str = "") -> None:
        """Record a check that could not run (input absent). Neither PASS nor FAIL.

        A check whose input is missing must not report PASS: in a public clone the
        private worksheet is absent, and a vacuous PASS would claim a verification
        that never happened.
        """
        self.checks.append({"check": name, "ok": True, "skipped": True, "detail": detail})

    @property
    def failed(self) -> list[dict]:
        return [c for c in self.checks if not c["ok"]]

    @property
    def skipped(self) -> list[dict]:
        return [c for c in self.checks if c.get("skipped")]

    def print(self) -> None:
        for c in self.checks:
            mark = "SKIP" if c.get("skipped") else ("PASS" if c["ok"] else "FAIL")
            line = f"[{mark}] {c['check']}"
            if c["detail"]:
                line += f" — {c['detail']}"
            print(line)
        n, f, s = len(self.checks), len(self.failed), len(self.skipped)
        ran = n - s
        print("-" * 64)
        print(f"{ran - f}/{ran} checks passed"
              + (f"; {s} skipped" if s else "")
              + (f"; {f} FAILED" if f else " — all good"))


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def text(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def appears(needle: str, *haystacks: str) -> bool:
    """True if the literal string appears in any document."""
    return any(needle in h for h in haystacks)


# --------------------------------------------------------------------------- #
# A. headline-number consistency (JSON is ground truth; prose must match)
# --------------------------------------------------------------------------- #
def check_numbers(rep: Report, docs: dict[str, str]) -> None:
    preprint, summary = docs["preprint"], docs["summary"]
    both = preprint + "\n" + summary

    # --- ablation: fabrication count & over-call->VUS count recomputed from rows
    abl = load(OUT / "ablation_report.json")
    rows = abl["rows"]
    n = len(rows)
    rep.add("ablation n == 56", n == 56, f"n={n}")

    fab = abl["faithfulness"]["norag_ungrounded_citations"]
    rep.add(
        "no-RAG fabrication count (26) in prose",
        fab == 26 and appears("26", both) and appears("46", both),
        f"json fab={fab}; expect 26/56 ~46% in prose",
    )

    def onco(pair):
        return (pair[0] or "").strip() if pair else ""

    over = [r for r in rows if onco(r["llm_norag"]) in ONCO_LEAN and onco(r["llm_rag"]) == "VUS"]
    pct = round(len(over) / n * 100, 1)
    rep.add(
        "over-call->VUS count (12/56, 21.4%) recomputed & in prose",
        len(over) == 12 and appears("12", both) and appears("21.4", both),
        f"recomputed={len(over)}/{n} ({pct}%)",
    )

    # --- faithfulness (eval_report)
    ev = load(OUT / "eval_report.json")
    hall = ev["hallucination"]["hallucination_rate"]
    rep.add("hallucination rate == 0.0 & in prose", hall == 0.0 and appears("0.0", both), f"json={hall}")
    grounded = ev["citation_grounding"]["grounding_rate"]
    rep.add("citation grounding == 1.0 & in prose", grounded == 1.0 and appears("1.0", both), f"json={grounded}")
    # abstention recall + its denominator (M3: report the denominator so 100% can't mislead)
    ab = ev["abstention"]
    denom = ab["no_evidence_variants"]
    num = ab["abstained_when_no_evidence"]
    rep.add(
        "abstention recall == 1.0 with denominator stated in prose",
        ab["abstention_recall"] == 1.0 and appears(f"{denom}/{denom}", both),
        f"json recall=1.0 ({num}/{denom}); prose should state '{denom}/{denom}'",
    )

    # --- Horak 3-class accuracy (stats CI) and McNemar
    stats = load(OUT / "stats_report.json")
    acc_ci = stats["horak_3class_accuracy_ci"]
    mc = stats["horak_mcnemar"]
    # the prose must NOT claim significance: every reported p should be > 0.05
    ps = [v for k, v in _flatten(mc).items() if k.endswith("p") or "p_value" in k or k == "p"]
    rep.add(
        "Horak McNemar p-values all > 0.05 (non-significant)",
        all(p > 0.05 for p in ps) if ps else False,
        f"p-values={ps}",
    )
    rep.add(
        "stats_report has 3-class accuracy CIs for all three arms",
        isinstance(acc_ci, dict) and len(acc_ci) >= 3,
        f"keys={list(acc_ci) if isinstance(acc_ci, dict) else acc_ci}",
    )

    # --- the headline citation-existence endpoint (2026-09-27 taxonomy), both arms
    #     scored by one rule. stats_report's older norag_citation_fabrication_ci is the
    #     retired endpoint and is deliberately NOT asserted here.
    tax = load(OUT / "citation_taxonomy.json")["headline"]["arms"]
    norag = tax["no_retrieval_E_empty_bundle"]["variant_any_fabricated_or_misattributed"]
    rep.add(
        "no-retrieval fabricated-or-misattributed CI excludes zero",
        norag["wilson_95"][0] > 0,
        f"{norag['k']}/{norag['n']} = {norag['rate']}, Wilson {norag['wilson_95']}",
    )
    for arm in ("retrieval_gpt4o_mini_106", "primary_pipeline_postgate"):
        ids = tax[arm]["identifier_tokens_out_of_bundle"]
        rep.add(
            f"{arm}: no identifier citation outside the bundle",
            ids["k"] == 0,
            f"{ids['k']}/{ids['n']}",
        )
    prose_pairs = [
        (f"{norag['k']} of {norag['n']}", "no-retrieval variant count"),
        (f"{norag['rate']:.3f}", "no-retrieval rate"),
        (f"0 of {tax['retrieval_gpt4o_mini_106']['identifier_tokens_out_of_bundle']['n']}",
         "retrieval identifier count"),
    ]
    missing = [label for txt, label in prose_pairs if txt not in docs["preprint"]]
    rep.add(
        "preprint quotes the taxonomy endpoint verbatim",
        not missing,
        "all present" if not missing else f"missing: {missing}",
    )

    # --- Horak oncogenic recall sanity (prose says 0.79)
    hk = load(BENCH / "horak_results.json")
    rec = _first_num(hk.get("summary_llm_rag", {}), prefer=("oncogenic_recall", "recall"))
    if rec is None:
        rec = _deep_find(hk, "oncogenic_recall")
    rep.add(
        "Horak oncogenic recall ~0.79 consistent with json",
        rec is not None and abs(rec - 0.79) < 0.02 and appears("0.79", both),
        f"json recall={rec}",
    )


def _flatten(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, f"{prefix}{k}."))
    else:
        out[prefix.rstrip(".")] = d
    return out


def _first_num(d, prefer=()):  # find a float in a dict, preferring certain key substrings
    if not isinstance(d, dict):
        return d if isinstance(d, (int, float)) else None
    flat = _flatten(d)
    for want in prefer:
        for k, v in flat.items():
            if want in k.lower() and isinstance(v, (int, float)):
                return v
    for v in flat.values():
        if isinstance(v, (int, float)):
            return v
    return None


def _deep_find(d, key):
    flat = _flatten(d)
    for k, v in flat.items():
        if k.endswith(key) and isinstance(v, (int, float)):
            return v
    return None


# --------------------------------------------------------------------------- #
# B. variant existence — any "GENE p.X" / "GENE V600E" named in docs must exist
# --------------------------------------------------------------------------- #
# protein change ends in *, letter, or fs*N — note no trailing \b (it fails after '*')
VARIANT_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9})\s+(?:p\.)?([A-Z]\d{1,4}(?:fs\*?\d*|_splice|del|dup|[A-Z*])?)")
# words that look like GENE but are not, to reduce false positives
GENE_STOPWORDS = {
    "VICC", "AMP", "ASCO", "CAP", "VUS", "RAG", "LLM", "DOI", "PMID", "CI", "API",
    "TCGA", "BM", "RRF", "JSON", "HTML", "PDF", "OVS", "OP", "SBP", "LOVO", "II",
    "III", "IV", "CGC", "CC", "NSCLC", "OR", "AND", "ID", "DBD", "ABD", "LBD",
}


def check_worksheet(rep: Report, known: set[tuple[str, str]], worksheet: Path) -> None:
    """Variant-existence checks on the expert-adjudication worksheet.

    The worksheet lives in notes/, which is not shipped. When it is absent both
    checks are reported as SKIP rather than PASS (an empty file would otherwise
    pass vacuously); locally they keep their PASS/FAIL behaviour.
    """
    names = (
        "worksheet TABLE variants all exist in cohort/benchmark data",
        "worksheet prose external-variant mentions (review-only, never fails)",
    )
    if not worksheet.exists():
        shown = worksheet.relative_to(ROOT) if worksheet.is_relative_to(ROOT) else worksheet
        for name in names:
            rep.skip(name, f"{shown} not present (private notes/, not shipped); not verified")
        return
    ws_lines = worksheet.read_text().splitlines()

    # HARD check: variants quoted in MARKDOWN TABLE ROWS are presented as OUR
    # system's results — every one must exist in the cohort/benchmark data. This
    # is exactly where a fabricated "system said X" value would hide. We skip
    # header/separator rows and provenance/correction notes (which legitimately
    # quote a fabricated example to document that it was wrong).
    def is_provenance(line: str) -> bool:
        low = line.lower()
        return any(w in low for w in ("fabricat", "non-existent", "wrongly", "corrected", "earlier draft", "invented"))

    table_unknown = []
    for line in ws_lines:
        if not line.lstrip().startswith("|"):
            continue
        if set(line.strip()) <= {"|", "-", " ", ":"}:  # separator row
            continue
        if is_provenance(line):
            continue
        for m in VARIANT_RE.finditer(line):
            gene, prot = m.group(1), m.group(2)
            if gene in GENE_STOPWORDS:
                continue
            if (gene, prot) not in known:
                table_unknown.append(f"{gene} {prot}")
    table_unknown = list(dict.fromkeys(table_unknown))
    rep.add(
        "worksheet TABLE variants all exist in cohort/benchmark data",
        not table_unknown,
        ("FABRICATION RISK: " + ", ".join(table_unknown[:15])) if table_unknown else "all table variants known",
    )

    # SOFT check: prose mentions of non-cohort variants are listed for human
    # review (external biology legitimately names hotspots not in our cohort);
    # never a hard fail, but surfaced so a reviewer can eyeball them.
    prose_unknown = []
    for line in ws_lines:
        if line.lstrip().startswith("|") or is_provenance(line):
            continue
        for m in VARIANT_RE.finditer(line):
            gene, prot = m.group(1), m.group(2)
            if gene in GENE_STOPWORDS or (gene, prot) in known:
                continue
            prose_unknown.append(f"{gene} {prot}")
    prose_unknown = list(dict.fromkeys(prose_unknown))
    rep.add(
        "worksheet prose external-variant mentions (review-only, never fails)",
        True,
        ("eyeball these external refs: " + ", ".join(prose_unknown[:20])) if prose_unknown else "none",
    )


def check_variants(rep: Report) -> None:
    ci = load(OUT / "cohort_interpretation.json")
    cohort_keys = {v["variant_key"] for v in ci["variants"]}
    # normalised set: gene + protein, no "p."
    cohort_norm = set()
    cohort_by_pair = {}
    for v in ci["variants"]:
        g = v["variant_key"].split()[0]
        prot = v["variant_key"].split("p.")[-1] if "p." in v["variant_key"] else v["variant_key"].split()[-1]
        cohort_norm.add((g, prot))
        cohort_by_pair.setdefault((g, prot), v["cancer_type"])

    # Horak benchmark variants (also legitimately citable)
    horak = load(BENCH / "horak_results.json")
    horak_norm = set()
    for r in horak.get("rows", []):
        g = r.get("gene") or ""
        p = (r.get("protein") or r.get("hgvsp") or "").replace("p.", "")
        if g and p:
            horak_norm.add((g, p))

    known = cohort_norm | horak_norm
    check_worksheet(rep, known, WORKSHEET)

    # cancer-type cross-check for the three beyond-rules variants quoted in worksheet
    expectations = {
        ("PIK3CA", "R88Q"): "Colorectal",
        ("PTEN", "R130*"): "Melanoma",
        ("ESR1", "E247K"): "Colorectal",
    }
    ct_problems = []
    for (g, p), expect in expectations.items():
        real = cohort_by_pair.get((g, p))
        if real is None:
            ct_problems.append(f"{g} {p}: not in cohort")
            continue
        # check the worksheet associates the right cancer near the variant mention
        if expect not in real:
            ct_problems.append(f"{g} {p}: cohort={real} != expected~{expect}")
    rep.add(
        "beyond-rules variant cancer-types match cohort JSON",
        not ct_problems,
        "; ".join(ct_problems) if ct_problems else "PIK3CA/PTEN/ESR1 contexts correct",
    )


# --------------------------------------------------------------------------- #
# C. unverified-fact tag scan (convention: mark anything unconfirmed)
# --------------------------------------------------------------------------- #
TAGS = ["[UNVERIFIED]", "[CHECK]", "[TODO", "???", "FIXME", "XXX-"]


def check_context_ablation(rep: Report, docs: dict[str, str]) -> None:
    """Input-context ablation: harness sanity + the prose matching the report.

    The negative control carries the weight here. Every other arm is expected to
    destroy the curated evidence, so a run in which *everything* collapses looks
    identical to a run in which the harness is simply broken. The control is what
    separates those two, and it must show perfect invariance.
    """
    path = OUT / "context_ablation.json"
    if not path.exists():
        rep.add("context ablation (not run; skipped)", True, f"no {path.name}")
        return
    both = docs["preprint"] + "\n" + docs["summary"]
    s = load(path)["summary"]

    # Retrieval under the control must be bit-identical: that is deterministic
    # code, and any movement means the harness is broken. Its *label* flips are
    # a different matter — the model is not perfectly reproducible even at
    # temperature 0 — so they are the nondeterminism floor, not a failure, and
    # the prose has to state that floor for the other arms to be readable.
    ctrl = s["arms"].get("case_lower", {})
    rep.add(
        "context ablation: negative control retrieval is bit-identical",
        ctrl.get("n_clinical_collapsed") == 0 and ctrl.get("mean_clinical_jaccard") == 1.0,
        f"control: collapsed={ctrl.get('n_clinical_collapsed')}, J={ctrl.get('mean_clinical_jaccard')}",
    )
    floor = ctrl.get("oncogenicity_flips", 0)
    rep.add(
        "context ablation: control nondeterminism floor is stated in prose",
        appears(f"{floor} of {ctrl.get('n_applicable')}", both) or appears(f"{floor}/{ctrl.get('n_applicable')}", both),
        f"control label flips at temperature 0 = {floor}/{ctrl.get('n_applicable')}",
    )

    sw = s["alias_sweep"]
    rep.add(
        "alias-sweep counts appear in prose",
        appears(str(sw["n_symbol_tests"]), both)
        and appears(str(sw["n_clinical_evidence_collapsed"]), both),
        f"{sw['n_clinical_evidence_collapsed']}/{sw['n_symbol_tests']} symbol tests lost "
        f"all curated evidence",
    )

    # Report the alias arm on its own, not a sum over arms: the same variants
    # recur in every arm, so a cross-arm total triple-counts them and would put
    # an inflated number in front of the reader.
    al = s["arms"].get("alias", {})
    drivers = al.get("driver_calls_after_clinical_loss", 0)
    safe = al.get("safe_downgrades_after_clinical_loss", 0)
    collapsed = al.get("n_clinical_collapsed", 0)
    # Both halves of the outcome must appear as an explicit "N of M", so the
    # prose cannot state the reassuring number and quietly drop the other.
    rep.add(
        "post-evidence-loss outcome (alias arm) is stated as N of M in prose",
        (appears(f"{drivers} of {collapsed}", both) or appears(f"{drivers}/{collapsed}", both))
        and appears(str(safe), both),
        f"alias arm: {drivers} driver call(s) and {safe} safe downgrade(s) "
        f"among {collapsed} variants that lost all curated evidence",
    )

    # The ablation output records citations but not the identifiers that were
    # available to the model, so the "no citation fell outside its bundle" claim
    # is not recomputable from it. scripts/check_ablation_citation_grounding.py
    # rebuilds the bundles (retrieval only, no model calls) and writes the
    # counts here; without that file the claim stands unverified and the gate
    # says so rather than passing quietly.
    gpath = OUT / "context_ablation_grounding.json"
    if not gpath.exists():
        rep.add(
            "context ablation: citation grounding recomputed",
            False,
            f"missing {gpath.name}; run scripts.check_ablation_citation_grounding",
        )
        return
    g = load(gpath)
    self_check = g["baseline_self_check"]
    # If the baseline identifiers no longer reproduce, retrieval has moved since
    # the run and every arm number below is measuring a different system.
    rep.add(
        "context ablation: retrieval reproduces baseline identifiers",
        self_check["trustworthy"],
        f"{self_check['n_reproduced']} reproduced, {self_check['n_drifted']} drifted",
    )
    arms = g["arms_total"]
    rep.add(
        "context ablation: no arm citation outside its retrieved bundle",
        arms["n_outside_bundle"] == 0,
        f"{arms['n_outside_bundle']} of {arms['n_citations']} outside bundle",
    )
    rep.add(
        "context ablation: citation-grounding count stated in prose",
        appears(f"{arms['n_outside_bundle']} of {arms['n_citations']}", both),
        f"prose should state '{arms['n_outside_bundle']} of {arms['n_citations']}'",
    )

    # The nondeterminism floor the ablation is read against. It has to come from
    # the fixed-prompt replicate run, not from the lower-case-symbol control:
    # that arm changes the prompt too, so its flips confound sampling noise with
    # case sensitivity and cannot set a floor on their own.
    rpath = OUT / "baseline_repeatability.json"
    if not rpath.exists():
        rep.add(
            "nondeterminism floor measured with a fixed prompt",
            False,
            f"missing {rpath.name}; run scripts.run_baseline_repeatability",
        )
        return
    pw = load(rpath)["summary"]["pairwise"]
    pct = {f: f"{r * 100:.1f}%" for f, r in pw["rate_by_field"].items()}
    pct["any"] = f"{pw['rate_any_field'] * 100:.1f}%"
    missing = [f"{f}={v}" for f, v in pct.items() if not appears(v, both)]
    rep.add(
        "nondeterminism floor rates stated in prose",
        not missing,
        f"over {pw['n_pairs']} replicate pairs: " + ", ".join(f"{f}={v}" for f, v in pct.items())
        + (f"; missing from prose: {', '.join(missing)}" if missing else ""),
    )


def check_tags(rep: Report, docs: dict[str, str]) -> None:
    hits = []
    for name in ("preprint", "summary"):
        for tag in TAGS:
            if tag in docs[name]:
                hits.append(f"{name}:{tag}")
    rep.add(
        "no unverified-fact tags left in preprint/summary",
        not hits,
        ", ".join(hits) if hits else "clean",
    )


# --------------------------------------------------------------------------- #
# E. SOP-strict rule arm, ClinVar holdout, HemaGuide, NLI support (added 2026-09-24)
# --------------------------------------------------------------------------- #
def _fmt3(x: float) -> str:
    return f"{x:.3f}"


def check_rule_arm_and_audits(rep: Report, docs: dict[str, str]) -> None:
    """Headline numbers introduced with the SOP-strict rule arm and the Type II audit.

    Each value is read from its result JSON and must appear verbatim in the preprint.
    A missing input (public clone before the data bundle lands) is a SKIP, not a PASS.
    """
    pre = docs["preprint"]

    def need(path: Path, name: str):
        if not path.exists():
            rep.skip(name, f"{path.relative_to(ROOT)} absent; not verified")
            return None
        return load(path)

    hv = need(BENCH / "horak_vicc.json", "rule arm (SOP-strict) headline in prose")
    if hv is not None:
        ci = hv["accuracy_3class_ci"]
        strs = [_fmt3(hv["accuracy_3class"]), f"{_fmt3(ci['lo'])}–{_fmt3(ci['hi'])}",
                _fmt3(hv["specificity_onc"]), _fmt3(hv["sensitivity_onc"]), _fmt3(hv["auroc_onc"])]
        missing = [x for x in strs if x not in pre]
        rep.add("rule arm (SOP-strict) headline in prose",
                hv.get("config") == "sop_strict" and not missing,
                f"config={hv.get('config')}; acc {strs[0]} [{strs[1]}], spec {strs[2]}, sens {strs[3]}, "
                f"AUROC {strs[4]}" + (f"; missing: {missing}" if missing else ""))

    hh = need(BENCH / "oncovi_headtohead.json", "OncoVI head-to-head (SOP-strict) in prose")
    if hh is not None:
        p = hh["paired_mcnemar_3class"]["p_two_sided"]
        strs = [_fmt3(hh["ours"]["accuracy_3class"]), _fmt3(hh["oncovi"]["accuracy_3class"]), f"p = {_fmt3(p)}"]
        missing = [x for x in strs if x not in pre]
        rep.add("OncoVI head-to-head (SOP-strict) in prose", p > 0.05 and not missing,
                f"ours {strs[0]} vs OncoVI {strs[1]}, {strs[2]} (non-significant required)"
                + (f"; missing: {missing}" if missing else ""))

    hg = need(BENCH / "hemaguide_headtohead.json", "HemaGuide head-to-head in prose")
    if hg is not None:
        p = hg["paired_mcnemar_3class"]["p_two_sided"]
        ci = hg["hemaguide"]["accuracy_3class_ci"]
        strs = [_fmt3(hg["hemaguide"]["accuracy_3class"]), f"{_fmt3(ci['lo'])}–{_fmt3(ci['hi'])}",
                _fmt3(hg["hemaguide"]["sensitivity_onc"]), _fmt3(hg["hemaguide"]["specificity_onc"]),
                f"p = {_fmt3(p)}"]
        missing = [x for x in strs if x not in pre]
        rep.add("HemaGuide head-to-head in prose", p > 0.05 and not missing,
                f"HemaGuide {strs[0]} [{strs[1]}], sens {strs[2]}, spec {strs[3]}, {strs[4]}"
                + (f"; missing: {missing}" if missing else ""))

    cv = need(BENCH / "clinvar_onc_holdout.json", "ClinVar oncogenicity holdout in prose")
    if cv is not None:
        strs = []
        for scope in ("all", "panel9"):
            d = cv["scopes"][scope]["detection"]
            for key in ("sensitivity", "specificity_on_gold_vus", "auroc_points"):
                c = d[key]
                strs += [_fmt3(c["point"]), f"{_fmt3(c['lo'])}–{_fmt3(c['hi'])}"]
        n_all = cv["scopes"]["all"]["detection"]["n"]
        strs.append(f"{n_all} ")
        missing = [x for x in strs if x not in pre]
        rep.add("ClinVar oncogenicity holdout in prose",
                cv["rule_arm_config"]["config"] == "sop_strict"
                and cv["rule_arm_config"]["OS1_known_oncogenic"] is False and not missing,
                f"all n={n_all}; config={cv['rule_arm_config']['config']}; OS1 off"
                + (f"; missing: {missing}" if missing else ""))

    nli = need(OUT / "nli_attribution_report.json", "NLI citation-support audit in prose")
    if nli is not None:
        sup = nli["arms"]["pipeline_rationale_arm"]["aggregate"]["citation_level"]["supported"]["iid"]
        kap = nli["arms"]["label_only_106_arm"]["imprecision_crosstab"]["cohens_kappa"]
        mt = nli["arms"]["label_only_106_arm"]["match_types"]
        strs = [_fmt3(sup["point"]), f"{_fmt3(sup['lo'])}–{_fmt3(sup['hi'])}", f"κ {_fmt3(kap)}",
                f"{sup['n']} citations"]
        missing = [x for x in strs if x not in pre]
        comp_ok = mt.get("bare_source") == 15 and mt.get("unresolvable") == 5
        rep.add("NLI citation-support audit in prose", comp_ok and not missing,
                f"supported {strs[0]} [{strs[1]}] of {sup['n']}; {strs[2]}; imprecision = "
                f"{mt.get('bare_source')} bare source + {mt.get('unresolvable')} non-identifier"
                + (f"; missing: {missing}" if missing else ""))


# --------------------------------------------------------------------------- #
# F. stale-number guard: withdrawn values may appear only in the correction note
# --------------------------------------------------------------------------- #
# Values withdrawn on 2026-09-24 (original rule-arm configuration and the retired
# ClinVar holdout). They are allowed only inside the correction-note section, which
# carries the sensitivity table (Table 3).
# A value directly after a dash is the upper bound of an interval ("0.650–0.902"),
# not a point estimate, so the lookbehind also excludes en dash and hyphen.
STALE_PATTERNS = {
    "0.843 (original rule-arm accuracy)": r"(?<![\d.\u2013-])0\.843(?![\d])",
    "0.902 (retired ClinVar AUROC)": r"(?<![\d.\u2013-])0\.902(?![\d])",
    "0.967 (retired ClinVar specificity)": r"(?<![\d.\u2013-])0\.967(?![\d])",
    "n = 458 (retired ClinVar holdout)": r"n\s*=\s*458\b",
    "0.464 (retired no-retrieval fabrication rate)": r"(?<![\d.\u2013-])0\.464(?![\d])",
    "46.4% (retired no-retrieval fabrication rate)": r"(?<![\d.])46\.4\s*(?:%|퍼센트)",
    "26 of 56 (retired no-retrieval variant count)": r"26\s*(?:of|/)\s*56\b|56개 중 26개",
    "p = 0.011 (withdrawn CancerVar test)": r"p\s*=\s*0\.011(?![\d])",
}
CORRECTION_HEADINGS = ("### Correction note", "### 정정 노트")


def strip_correction_note(text: str) -> tuple[str, bool]:
    """Remove every correction-note section (heading to the next ##/### heading)."""
    out, found = [], False
    lines = text.split("\n")
    skipping = False
    for line in lines:
        if any(line.startswith(h) for h in CORRECTION_HEADINGS):
            skipping, found = True, True
            continue
        if skipping and (line.startswith("## ") or line.startswith("### ")):
            skipping = False
        if not skipping:
            out.append(line)
    return "\n".join(out), found


def stale_hits(text: str) -> list[str]:
    body = re.split(r"\n## References", text)[0]
    body = re.sub(r"```.*?```", "", body, flags=re.S)
    body, _ = strip_correction_note(body)
    hits = []
    for label, pat in STALE_PATTERNS.items():
        for m in re.finditer(pat, body):
            ctx = body[max(0, m.start() - 40): m.end() + 20].replace("\n", " ")
            hits.append(f"{label}: ...{ctx}...")
    return hits


# --------------------------------------------------------------------------- #
# G. Supplementary Table S3 (pre-specified improvement round) against its JSON
# --------------------------------------------------------------------------- #
# Added 2026-11-07 after a re-review found a wrong specificity cell in this table
# that every other check passed over. The truth values sit in the repository, so
# the table is checked cell by cell instead of being left to review.
def _s3_section(text: str, heading: str) -> str:
    i = text.find(heading)
    if i < 0:
        return ""
    j = text.find("\n## ", i + 1)
    k = text.find("\n### ", i + 1)
    ends = [e for e in (j, k) if e > 0]
    return text[i: min(ends) if ends else len(text)]


def _ci(d: dict) -> str:
    return f"{d['point']:.3f} [{d['lo']:.3f}\u2013{d['hi']:.3f}]"


def check_table_s3(rep: Report, docs: dict[str, str]) -> None:
    path = BENCH / "vicc_config_comparison.json"
    if not path.exists():
        rep.skip("Supplementary Table S3 vs vicc_config_comparison.json", "file absent")
        return
    res = load(path)["results"]
    a, b = res["sop_strict"], res["sop_strict_v2"]
    vs = b["vs_sop_strict"]

    def mc(key: str) -> str:
        d = vs[key]
        p = d["p_value"]
        ptxt = "p < 0.001" if p < 0.001 else f"p = {p:.3f}" if p < 1 else "p = 1.0"
        return ptxt, f"{d['discordant_pairs']} discordant"

    ca, cb = a["clinvar_holdout"], b["clinvar_holdout"]
    expected = {
        "three-class accuracy": [f"{a['horak']['accuracy_3class']:.3f}",
                                 f"{b['horak']['accuracy_3class']:.3f}", *mc("horak_3class")],
        "oncogenic sensitivity": [f"{a['horak']['sensitivity_onc']:.3f}",
                                  f"{b['horak']['sensitivity_onc']:.3f}"],
        "oncogenic specificity": [f"{a['horak']['specificity_onc']:.3f}",
                                  f"{b['horak']['specificity_onc']:.3f}"],
        "AUROC": [f"{a['horak']['auroc_onc']:.3f}", f"{b['horak']['auroc_onc']:.3f}"],
        "panel (n = 236), sensitivity": [_ci(ca["panel9"]["sensitivity"]),
                                         _ci(cb["panel9"]["sensitivity"]), *mc("clinvar_panel9_binary")],
        "all genes (n = 712), sensitivity": [_ci(ca["all"]["sensitivity"]),
                                             _ci(cb["all"]["sensitivity"]), *mc("clinvar_all_binary")],
        "panel (n = 236), specificity": [f"{ca['panel9']['specificity_on_gold_vus']['point']:.3f}",
                                         f"{cb['panel9']['specificity_on_gold_vus']['point']:.3f}"],
        "all genes (n = 712), specificity": [f"{ca['all']['specificity_on_gold_vus']['point']:.3f}",
                                             f"{cb['all']['specificity_on_gold_vus']['point']:.3f}"],
    }
    sec = _s3_section(docs["preprint"], "### Supplementary Table S3")
    rows = [ln for ln in sec.split("\n") if ln.startswith("| ")]
    problems = []
    for label, want in expected.items():
        row = next((r for r in rows if label in r), None)
        if row is None:
            problems.append(f"no row for '{label}'")
            continue
        missing = [w for w in want if w not in row]
        if missing:
            problems.append(f"'{label}' lacks {missing}")
    rep.add("Supplementary Table S3 matches vicc_config_comparison.json (EN)",
            bool(sec) and not problems,
            "; ".join(problems[:4]) if problems else f"{len(expected)} rows match")

    # the Korean table must carry the same numbers as the English one
    if PREPRINT_KO.exists():
        ko = _s3_section(PREPRINT_KO.read_text(), "### 보충 표 S3")
        num = lambda t: sorted(re.findall(r"\d+\.\d+", "\n".join(l for l in t.split("\n") if l.startswith("|"))))
        rep.add("Supplementary Table S3 numbers identical in KO",
                bool(ko) and num(ko) == num(sec),
                "match" if ko and num(ko) == num(sec) else "KO table differs from EN")


def check_stale_numbers(rep: Report) -> None:
    for path in (PREPRINT, PREPRINT_KO):
        if not path.exists():
            rep.skip(f"stale-number guard ({path.name})", "file absent")
            continue
        t = path.read_text()
        _, found = strip_correction_note(t)
        hits = stale_hits(t)
        rep.add(f"stale-number guard ({path.name}): withdrawn values only in correction note",
                found and not hits,
                ("correction note missing; " if not found else "")
                + ("; ".join(hits[:6]) if hits else "no withdrawn value outside the correction note"))


# --------------------------------------------------------------------------- #
# D. DOI resolution (online, optional)
# --------------------------------------------------------------------------- #
DOI_RE = re.compile(r"10\.\d{4,}/[^\s)\"'}]+")  # stop before } (BibTeX), ) and quotes


def check_dois(rep: Report, docs: dict[str, str], online: bool) -> None:
    dois = sorted(set(m.group(0).rstrip(".,;}") for m in DOI_RE.finditer(docs["preprint"])))
    rep.add("preprint has DOIs", bool(dois), f"{len(dois)} unique DOIs")
    if not online:
        rep.add("DOI resolution (skipped; pass --online to enable)", True, f"{len(dois)} DOIs not checked")
        return
    import urllib.request

    bad = []
    for doi in dois:
        url = f"https://api.crossref.org/works/{doi}/agency"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "verify-manuscript/1.0 (mailto:kakyung.kim@gmail.com)"})
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status != 200:
                    bad.append(f"{doi} (HTTP {r.status})")
        except Exception as e:  # noqa: BLE001
            bad.append(f"{doi} ({type(e).__name__})")
    rep.add(
        "all preprint DOIs resolve on Crossref",
        not bad,
        ("unresolved: " + "; ".join(bad)) if bad else f"{len(dois)} DOIs resolve",
    )


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--online", action="store_true", help="resolve DOIs against Crossref (network)")
    ap.add_argument("--json", type=Path, help="write the machine-readable report here")
    args = ap.parse_args()

    docs = {"preprint": text(PREPRINT), "summary": text(SUMMARY)}
    rep = Report()

    if not PREPRINT.exists():
        rep.add("preprint.md exists", False, str(PREPRINT))
    else:
        check_numbers(rep, docs)
        check_variants(rep)
        check_context_ablation(rep, docs)
        check_tags(rep, docs)
        check_rule_arm_and_audits(rep, docs)
        check_stale_numbers(rep)
        check_table_s3(rep, docs)
        check_dois(rep, docs, args.online)

    rep.print()
    if args.json:
        args.json.write_text(json.dumps(rep.checks, indent=2))
        print(f"\nwrote {args.json}")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
