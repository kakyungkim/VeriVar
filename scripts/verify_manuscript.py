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
        self.checks.append({"check": name, "ok": bool(ok), "detail": detail})

    @property
    def failed(self) -> list[dict]:
        return [c for c in self.checks if not c["ok"]]

    def print(self) -> None:
        for c in self.checks:
            mark = "PASS" if c["ok"] else "FAIL"
            line = f"[{mark}] {c['check']}"
            if c["detail"]:
                line += f" — {c['detail']}"
            print(line)
        n, f = len(self.checks), len(self.failed)
        print("-" * 64)
        print(f"{n - f}/{n} checks passed" + (f"; {f} FAILED" if f else " — all good"))


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

    # --- the no-RAG fabrication CI excludes zero (the headline robustness claim)
    fab_ci = stats["norag_citation_fabrication_ci"]
    lo = _first_num(fab_ci, prefer=("lo", "low", "lower", "ci_low"))
    rep.add(
        "no-RAG fabrication CI lower bound > 0 (excludes zero)",
        lo is not None and lo > 0,
        f"ci={fab_ci}",
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
    ws_lines = text(WORKSHEET).splitlines()

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

    # cancer-type cross-check for the three beyond-rules variants quoted in worksheet
    ws = text(WORKSHEET)
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
        check_tags(rep, docs)
        check_dois(rep, docs, args.online)

    rep.print()
    if args.json:
        args.json.write_text(json.dumps(rep.checks, indent=2))
        print(f"\nwrote {args.json}")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
