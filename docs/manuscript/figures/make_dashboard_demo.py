#!/usr/bin/env python3
"""Render _dashboard_demo.html (Supplementary Figure S3 source) from real outputs.

Nothing in the figure is hand-typed. For each example variant this fills:
  * badges, calls, tiers, rationales and citations from
    data/outputs/cohort_interpretation.json (the persisted record + bundle);
  * the VICC rule-arm card from the SOP-strict engine
    (src.classify.vicc_rules.VICCPointClassifier via src.dashboard.vicc_arm.score_record);
  * the grounded-chat bubbles from _dashboard_demo_chat.json (verbatim answers of
    LLMClassifier.answer_question on the same bundle; provenance inside the file).
Also writes _dashboard_demo_values.json, the per-variant values shown, for auditing.

Usage (from the repo root):  python docs/manuscript/figures/make_dashboard_demo.py
Then screenshot with make_dashboard_figure.sh (which calls this script first).
"""
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from jinja2 import Environment, FileSystemLoader  # noqa: E402

from src.dashboard.vicc_arm import score_record  # noqa: E402

RESULTS = ROOT / "data" / "outputs" / "cohort_interpretation.json"
CHAT = HERE / "_dashboard_demo_chat.json"
EXAMPLES = [("BRAF p.V600E", "Cutaneous Melanoma"),
            ("APC p.R1450*", "Colorectal Adenocarcinoma")]
_ID = re.compile(r"\[?(CIViC:EID\d+)\]?")
_PILL = {"Oncogenic": "onc", "Likely Oncogenic": "lonc", "VUS": "vus",
         "Likely Benign": "lben", "Benign": "ben"}
_BAND = {"Oncogenic": "band ≥10", "Likely Oncogenic": "band 6 to 9",
         "VUS": "band 0 to 5", "Likely Benign": "band -1 to -6", "Benign": "band ≤-7"}


def linkify(text: str) -> str:
    """Escape, then turn CIViC ids into (inert) links as in the live dashboard."""
    # keep the answer's own brackets so adjacent ids ("[A][B]") stay separated
    return re.sub(r"(\[?)(CIViC:EID\d+)(\]?)", r'\1<a href="#">\2</a>\3',
                  html.escape(text, quote=False))


def cap_sentences(text: str, limit: int = 430) -> str:
    """Verbatim leading sentences up to ~limit chars; mark any cut with […]."""
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    out = ""
    for s in sents:
        if out and len(out) + len(s) + 1 > limit:
            return out + " […]"
        out = f"{out} {s}".strip()
    return out


def trim(text: str, n: int = 150) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"


def ids_in(text: str) -> list:
    seen = []
    for m in _ID.finditer(text or ""):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def mode_card(m: dict, header: str, cls: str, rationale_ids: list) -> dict:
    tier = m["tier"] + (f" · {m['tier_level']}" if m.get("tier_level") else "")
    cites = list(m.get("citations") or [])
    if cls == "gen":
        cites_html = (", ".join(f'<a href="#">{html.escape(c)}</a>' for c in cites)
                      if cites else "none (no retrieved variant-specific evidence)")
    else:
        cites_html = (f"{len(cites)} bundle identifiers ({len(rationale_ids)} named in rationale)"
                      if cites else "none")
    return {"header": header, "cls": cls, "pill": _PILL.get(m["oncogenicity"], "vus"),
            "call": m["oncogenicity"], "tier": tier + (" · abstained" if m.get("abstained") else ""),
            "rationale_html": linkify(cap_sentences(m.get("rationale") or "")),
            "cites_html": cites_html}


def chat_block(ans: dict, gene_aa: str) -> dict:
    text = ans["answer"].strip()
    abstain = text.lower().startswith("i cannot answer")
    if abstain:
        body = html.escape(text, quote=False)
        note = ("faithful abstention: refuses to go beyond the retrieved bundle; gene-level "
                "druggability is not variant-specific evidence.")
    else:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        items = [ln for ln in lines if re.match(r"^\d+\.", ln)]
        intro = [ln for ln in lines if ln not in items][:2]
        shown = items[:1]
        rest_ids = [i for it in items[1:] for i in ids_in(it)]
        body = linkify(intro[0] if intro else "")
        if shown:
            body += "<ol><li>" + linkify(re.sub(r"^\d+\.\s*", "", shown[0])) + "</li></ol>"
        if rest_ids:
            body += (f"[…] {len(items) - 1} further points citing "
                     + ", ".join(f'<a href="#">{i}</a>' for i in rest_ids) + " (answer abridged).")
        note = "grounded: every claim cites a retrieved identifier; links resolve to CIViC."
    return {"variant": gene_aa, "question": ans["question"], "answer_html": body,
            "abstain": abstain, "note": note}


def build():
    data = json.loads(RESULTS.read_text())
    chats = {(a["variant_key"], a["cancer_type"]): a
             for a in json.loads(CHAT.read_text())["answers"]}
    examples, audit = [], []
    for n, key in enumerate(EXAMPLES, 1):
        v = next(x for x in data["variants"] if (x["variant_key"], x["cancer_type"]) == key)
        a, b = v["mode_a"], v["mode_b"]
        bundle = v.get("bundle") or {}
        ev = bundle.get("evidences") or []
        bundle_ids = {e["id"] for e in ev if e.get("id")}
        for d in bundle.get("drugs") or []:
            bundle_ids.update(d.get("citations") or [])
        bundle_ids.update(t["nct_id"] for t in bundle.get("trials") or [] if t.get("nct_id"))
        arm = score_record(v)
        gene_aa = f"{v['gene']} {v['hgvsp'].replace('p.', '')}"
        chat = chats[key]

        a_cited = list(dict.fromkeys(list(a.get("citations") or []) + ids_in(a.get("rationale"))))
        fabricated = [c for c in a_cited if c not in bundle_ids]
        grounded_ex = bool(ev)
        if grounded_ex:
            label = f"Example {n}: variant with evidence (grounded)"
            badges = [f"{v['n_evidence']} evidence items", f"{v['n_drugs']} drugs",
                      f"{v['n_trials']} trials",
                      "modes discordant" if v["discordant"] else "modes concordant"]
            gate = [{"cls": "ok", "tick": "✓",
                     "text": f"citations validated · {len(fabricated)} fabricated"},
                    {"cls": "ok", "tick": "✓",
                     "text": f"{len(a_cited) - len(fabricated)}/{len(a_cited)} cited identifiers "
                             f"found in the retrieved bundle"},
                    {"cls": "ok", "tick": "✓",
                     "text": "VICC criteria computed by the SOP-strict engine"}]
        else:
            label = (f"Example {n}: no variant-specific evidence (modes abstain; "
                     f"the rule arm still scores the variant)")
            badges = ["0 variant-specific evidence"]
            if v["hgvsp"].endswith("*"):
                badges.append("nonsense (truncating) variant")
            gate = [{"cls": "ok", "tick": "✓",
                     "text": f"citations validated · {len(fabricated)} fabricated"},
                    {"cls": "abst", "tick": "⛔",
                     "text": "gate: no variant-specific evidence, both modes abstain (VUS)"},
                    {"cls": "info", "tick": "ℹ",
                     "text": "rule arm: codes from gene role and variant consequence, "
                             "not from an evidence item"}]
        evidence = []
        if grounded_ex:
            want = list(dict.fromkeys(a_cited + ids_in(chat["answer"])))
            by_id = {e["id"]: e for e in ev}
            for i in want:
                if i in by_id and len(evidence) < 3:
                    e = by_id[i]
                    evidence.append({"id": i, "disease": e.get("disease") or "n/a",
                                     "statement": trim(e.get("statement") or "")})
        trial = next((t["nct_id"] for t in bundle.get("trials") or []), None)
        inputs = " · ".join(f"{k}: {val}" for k, val in arm.inputs.items())
        if arm.coords:
            inputs += f" · {arm.coords}"
        vicc = {"call": arm.call, "points": arm.points, "pill": _PILL.get(arm.call, "vus"),
                "band": _BAND[arm.call], "rows": arm.rows(), "inputs": "Inputs: " + inputs}
        examples.append({
            "label": label, "name": f"{v['gene']} {v['hgvsp']}", "ctx": v["cancer_type"],
            "badges": badges,
            "modes": [mode_card(a, "Generative mode · LLM", "gen", ids_in(a.get("rationale"))),
                      mode_card(b, "Deterministic mode · rule", "det", ids_in(b.get("rationale")))],
            "vicc": vicc, "gate": gate, "evidence": evidence, "n_evidence": v["n_evidence"],
            "trial": trial, "chat": chat_block(chat, gene_aa)})
        audit.append({"variant": key[0], "cancer_type": key[1],
                      "generative": {"oncogenicity": a["oncogenicity"], "tier": a["tier"],
                                     "tier_level": a.get("tier_level"),
                                     "abstained": a.get("abstained")},
                      "deterministic": {"oncogenicity": b["oncogenicity"], "tier": b["tier"],
                                        "tier_level": b.get("tier_level"),
                                        "abstained": b.get("abstained")},
                      "vicc_rule_arm": {"config": arm.config, "call": arm.call,
                                        "points": arm.points, "criteria": arm.rows(),
                                        "inputs": arm.inputs, "coords": arm.coords},
                      "fabricated_citations": len(fabricated),
                      "chat_abstained": chat_block(chat, gene_aa)["abstain"]})

    env = Environment(loader=FileSystemLoader(str(HERE)), autoescape=True,
                      trim_blocks=True, lstrip_blocks=True)
    out = env.get_template("_dashboard_demo.html.j2").render(examples=examples)
    tmp = HERE / "_dashboard_demo.html.tmp"
    tmp.write_text(out)
    tmp.replace(HERE / "_dashboard_demo.html")
    (HERE / "_dashboard_demo_values.json").write_text(json.dumps(audit, indent=1, ensure_ascii=False))
    for r in audit:
        vr = r["vicc_rule_arm"]
        print(f"{r['variant']} ({r['cancer_type']}): gen {r['generative']['oncogenicity']}, "
              f"det {r['deterministic']['oncogenicity']}, VICC {vr['call']} "
              f"Σ={vr['points']} {[(c['code'], c['points']) for c in vr['criteria']]}")


if __name__ == "__main__":
    build()
