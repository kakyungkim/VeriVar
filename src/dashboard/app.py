"""Streamlit dashboard for the dual-mode interpretation results.

Run:  streamlit run src/dashboard/app.py

Tabs: cohort overview, discordance explorer, and per-variant drill-down with a
faithfulness-grounded NL Q&A (answers only from retrieved evidence, abstains
otherwise).
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

# `streamlit run src/dashboard/app.py` puts the script dir (not the project root)
# on sys.path, so `import src.*` would fail. Add the project root explicitly.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
import streamlit as st

RESULT_PATH = _PROJECT_ROOT / "data/outputs/cohort_interpretation.json"

# Turn evidence/trial ids in free text into clickable markdown links.
_EID_RE = re.compile(r"\[?CIViC:EID(\d+)\]?")
_NCT_RE = re.compile(r"\[?(NCT\d+)\]?")


def linkify(text: str) -> str:
    text = _EID_RE.sub(r"[CIViC:EID\1](https://civicdb.org/links/evidence_items/\1)", text)
    text = _NCT_RE.sub(r"[\1](https://clinicaltrials.gov/study/\1)", text)
    return text


def drug_link(name: str) -> str:
    """Markdown link for a drug name (lookup, not a recommendation).

    Prefers a ChEMBL compound card when an embedded CHEMBL id is present,
    otherwise a DGIdb drug search. Drugs are gene-level DGIdb context, NOT
    variant-specific actionability (faithfulness contract).
    """
    n = (name or "").strip()
    if not n:
        return n
    m = re.search(r"(CHEMBL\d+)", n, re.I)
    if m:
        return f"[{n}](https://www.ebi.ac.uk/chembl/compound_report_card/{m.group(1).upper()}/)"
    return f"[{n}](https://www.dgidb.org/results?searchType=drug&searchTerms={quote(n)})"


# cBioPortal needs a study in the query — a bare ?gene_list=GENE crashes its SPA
# ("Cannot read properties of undefined (reading 'split')"). Map our cohort's
# cancer types to their TCGA PanCancer Atlas study ids; fall back to all five.
_CBIO_STUDY = {
    "Breast Carcinoma": "brca_tcga_pan_can_atlas_2018",
    "Colorectal Adenocarcinoma": "coadread_tcga_pan_can_atlas_2018",
    "Cutaneous Melanoma": "skcm_tcga_pan_can_atlas_2018",
    "Lung Adenocarcinoma (NSCLC)": "luad_tcga_pan_can_atlas_2018",
    "Pancreatic Adenocarcinoma": "paad_tcga_pan_can_atlas_2018",
}
_CBIO_ALL = ",".join(_CBIO_STUDY.values())


def _cbioportal_url(gene: str, cancer_type: str | None) -> str:
    """Valid cBioPortal results query (single cohort study if known, else all five)."""
    study = _CBIO_STUDY.get(cancer_type or "")
    if study:
        params = f"cancer_study_list={study}&case_set_id={study}_all"
    else:
        params = f"cancer_study_list={_CBIO_ALL}&case_set_id=all"
    return ("https://www.cbioportal.org/results/mutations?"
            f"{params}&gene_list={gene}&tab_index=tab_visualize&Action=Submit")


def ext_links(gene: str, hgvsp: str, cancer_type: str | None = None) -> str:
    """External knowledgebase links for a variant (markdown)."""
    alt = hgvsp[2:] if hgvsp.startswith("p.") else hgvsp
    return " · ".join([
        f"[OncoKB](https://www.oncokb.org/gene/{gene}/{alt})",
        f"[ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/?term={gene}%20{alt})",
        f"[cBioPortal]({_cbioportal_url(gene, cancer_type)})",
        f"[COSMIC](https://cancer.sanger.ac.uk/cosmic/search?q={gene}%20{alt})",
        f"[DGIdb](https://dgidb.org/results?searchType=gene&searchTerms={gene})",
    ])


# ── VICC / ClinGen / CGC criterion code → human-readable meaning ──────────────
# Reused from the engine: meanings are taken verbatim from the criterion
# definitions documented in `src/classify/vicc_rules.py` (the Criterion statement
# templates + their inline comments; Horak et al. 2022 point-based combining rules).
# Points are the same _PTS table used by that engine. We do NOT invent meanings.
_VICC_CRITERIA = {
    # Oncogenic — very strong / strong / moderate / supporting
    "OVS1": ("Null (LoF) variant in a tumour-suppressor gene", 8),
    "OS1":  ("Same amino-acid change as an established oncogenic variant", 4),
    "OS2":  ("Well-established functional study shows loss-of-function / damaging", 4),
    "OS3":  ("Recurs in ≥50 samples at a cancerhotspots.org hotspot residue", 4),
    "OM1":  ("Located in a well-established functional domain (UniProt)", 2),
    "OM3":  ("Recurs in 10–49 samples at a hotspot residue", 2),
    "OM4":  ("CIViC evidence supports an oncogenic role", 2),
    "OP1":  ("Computational evidence (AlphaMissense) predicts pathogenic", 1),
    "OP3":  ("Located at a cancerhotspots.org hotspot residue", 1),
    "OP4":  ("Absent / very rare in population databases (gnomAD)", 1),
    # Benign — very strong / strong / supporting
    "SBVS1": ("Population allele frequency ≥5% in gnomAD (common → benign)", -8),
    "SBS1":  ("Population allele frequency ≥1% in gnomAD", -4),
    "SBS2":  ("Functional study / CIViC evidence shows neutral / refutes oncogenic role", -4),
    "SBP1":  ("Computational evidence (AlphaMissense) predicts benign", -1),
}


def vicc_criterion_label(code: str) -> str:
    """Human-readable meaning for a fired VICC criterion code (from the engine)."""
    return _VICC_CRITERIA.get(code, ("(criterion documented in the engine)", 0))[0]


def vicc_criterion_points(code: str):
    return _VICC_CRITERIA.get(code, (None, None))[1]


@st.cache_data
def load_results():
    if not RESULT_PATH.exists():
        return None
    return json.loads(RESULT_PATH.read_text())


@st.cache_data
def load_json(name: str):
    """Load a committed output JSON by filename; None if absent/unparsable."""
    p = _PROJECT_ROOT / "data/outputs" / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _pct(x):
    """Format a 0..1 rate as a percent string, or 'n/a' if missing."""
    return f"{x * 100:.1f}%" if isinstance(x, (int, float)) else "n/a"


# ── Protein lollipop / domain context ─────────────────────────────────────
# Brand palette (colorblind-safe navy + teal, matching the project figures).
_BRAND_NAVY = "#1B2E5E"
_BRAND_TEAL = "#2EB8A6"
_DOMAINS_PATH = _PROJECT_ROOT / "data/knowledge/domains/uniprot_domains.json"


@st.cache_data
def load_domains() -> dict:
    """Load the UniProt domain/feature map (keyed by gene symbol); {} if absent."""
    if not _DOMAINS_PATH.exists():
        return {}
    try:
        return json.loads(_DOMAINS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def parse_residue(hgvsp: str) -> int | None:
    """Parse the 1-based residue number from a 1-letter protein change.

    Handles substitutions (``p.V600E`` → 600), nonsense (``p.E941*`` → 941),
    and frameshift (``p.S100fs`` → 100) by taking the *leading* residue number
    after the reference amino acid. Returns ``None`` when no number is present
    (e.g. unparsable / splice notations).
    """
    if not hgvsp:
        return None
    s = hgvsp[2:] if hgvsp.startswith("p.") else hgvsp
    # Match a leading amino-acid letter(s) followed by the (first) residue number.
    m = re.search(r"[A-Za-z]+(\d+)", s)
    return int(m.group(1)) if m else None


def render_protein_context(gene: str, hgvsp: str):
    """Render a compact protein track with domain/region context + a lollipop
    marking the variant's residue. Research/education only.

    Shades ``Domain`` and ``Region`` features as labeled rectangles, shows
    single-residue ``Binding/Active site`` features as faint ticks, and draws
    the variant as a navy/teal lollipop. Falls back to a position-only track for
    genes with no UniProt annotation, and skips gracefully if the residue can't
    be parsed.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt

    res = parse_residue(hgvsp)
    if res is None:
        st.caption(f"Protein context unavailable — could not parse a residue "
                   f"position from {hgvsp!r}.")
        return

    feats = (load_domains() or {}).get(gene, [])
    has_anno = bool(feats)

    ends = [f[1] for f in feats] + [res]
    length = max(ends)
    pad = max(int(length * 0.05), 5)
    xmax = length + pad

    fig, ax = plt.subplots(figsize=(9, 1.9))
    track_y, track_h = 0.0, 0.5

    # Backbone track.
    ax.add_patch(mpatches.Rectangle((1, track_y), length - 1, track_h,
                                    facecolor="#E7ECF3", edgecolor="#B7C2D4",
                                    linewidth=0.8, zorder=1))

    # Colorblind-safe fills for shaded domains/regions (Okabe-Ito derived).
    domain_fills = ["#56B4E9", "#E69F00", "#009E73", "#CC79A7",
                    "#F0E442", "#0072B2", "#D55E00"]
    di = 0
    for start, end, ftype, label in feats:
        if ftype in ("Domain", "Region"):
            color = domain_fills[di % len(domain_fills)]
            di += 1
            ax.add_patch(mpatches.Rectangle(
                (start, track_y), max(end - start, 1), track_h,
                facecolor=color, edgecolor="#33373D", linewidth=0.6,
                alpha=0.55, zorder=2))
            name = label or ftype
            if len(name) > 22:
                name = name[:21] + "…"
            ax.text((start + end) / 2, track_y + track_h / 2, name,
                    ha="center", va="center", fontsize=7, color="#1A1A1A",
                    zorder=3, clip_on=True)
        elif ftype in ("Binding site", "Active site"):
            # Faint ticks for single-residue functional sites (reduce clutter).
            ax.plot([start, start], [track_y, track_y + track_h],
                    color="#8A93A3", linewidth=0.6, alpha=0.6, zorder=2)

    # Variant lollipop: navy stem + teal-filled circle.
    stem_top = track_y + track_h + 0.55
    ax.plot([res, res], [track_y + track_h, stem_top],
            color=_BRAND_NAVY, linewidth=1.8, zorder=4)
    ax.scatter([res], [stem_top], s=130, facecolor=_BRAND_TEAL,
               edgecolor=_BRAND_NAVY, linewidth=1.4, zorder=5)
    change = hgvsp[2:] if hgvsp.startswith("p.") else hgvsp
    ax.annotate(change, (res, stem_top), xytext=(0, 9),
                textcoords="offset points", ha="center", fontsize=8.5,
                fontweight="bold", color=_BRAND_NAVY, zorder=6)

    ax.set_xlim(0, xmax)
    ax.set_ylim(-0.35, stem_top + 0.55)
    ax.set_yticks([])
    for spine in ("top", "left", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_position(("data", -0.2))
    ax.set_xlabel("Residue position (aa)", fontsize=8)
    ax.tick_params(axis="x", labelsize=7)
    ax.set_title(f"{gene} protein — domains & this variant", fontsize=10,
                 color=_BRAND_NAVY, loc="left")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    if not has_anno:
        st.caption(f"No UniProt domain annotation available for {gene} "
                   f"(showing position only).")
    st.caption("Domain/region context from UniProt · research & education only.")


@st.cache_resource
def get_llm():
    """Lazy-load the LLM client for the grounded chat."""
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env", override=True)
    from src.classify.llm import LLMClassifier
    return LLMClassifier()


@st.cache_resource
def get_aggregator_kg():
    """Fallback retrieval (only used if a row has no persisted bundle)."""
    from src.knowledge.factory import build_aggregator
    from src.retrieval.graph import KnowledgeGraph
    return build_aggregator(offline=True), KnowledgeGraph.from_civic()


@st.cache_resource
def get_upload_retriever():
    """Build the full hybrid retriever ONCE for the Upload-VCF tab.

    First call loads the dense index + embedder (a few seconds); subsequent
    calls reuse the cached instance. Returns ``None`` if building fails so the
    caller can degrade to the offline aggregator path (``retriever=None``).
    """
    from src.interpret import get_default_retriever
    try:
        return get_default_retriever(am_online=True)
    except Exception:  # noqa: BLE001
        return None


def _fired_criteria_rows(v: dict):
    """Collect fired VICC codes from both modes → list of (code, meaning, points, modes)."""
    codes = {}
    for mode_key, mode_label in (("mode_b", "Deterministic"), ("mode_a", "Generative")):
        for c in (v.get(mode_key, {}) or {}).get("oncogenicity_codes") or []:
            codes.setdefault(c, set()).add(mode_label)
    rows = []
    for code in sorted(codes, key=lambda c: -(vicc_criterion_points(c) or 0)):
        pts = vicc_criterion_points(code)
        rows.append({
            "code": code,
            "meaning": vicc_criterion_label(code),
            "points": pts if pts is not None else "",
            "fired in": " + ".join(sorted(codes[code])),
        })
    return rows


def render_criteria_fired(v: dict):
    """Feature 1 — per-criterion VICC rationale panel (the auditability headline)."""
    st.markdown("**Which ClinGen / CGC / VICC criteria fired (auditable)**")
    rows = _fired_criteria_rows(v)
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("Criterion meanings are taken from the rule engine "
                   "(`src/classify/vicc_rules.py`, Horak et al. 2022 point-based rules). "
                   "Positive points → oncogenic direction, negative → benign.")
    else:
        st.info("No named VICC criteria fired for this variant — the call rests on the "
                "overall evidence tier (or honest abstention to VUS). Not an error.")


def render_grouped_evidence(bundle, cancer_type: str | None):
    """Feature 2 — evidence grouped by source + level, with matched/off-label tags."""
    if not bundle.evidences:
        st.caption("No variant-specific evidence retrieved for this variant.")
        return
    ct = (cancer_type or "").lower()

    def _matches(disease: str | None) -> bool:
        if not disease or not ct:
            return False
        d = disease.lower()
        return d in ct or ct in d

    # Group by source; within a source sort by evidence_level (A best → Z, blanks last).
    by_source: dict[str, list] = {}
    for e in bundle.evidences:
        by_source.setdefault(e.source or "other", []).append(e)
    for source in sorted(by_source):
        items = sorted(by_source[source],
                       key=lambda e: (e.evidence_level or "~", e.id or ""))
        st.markdown(f"**{source}** · {len(items)} item(s)")
        for e in items[:25]:
            lvl = f"level {e.evidence_level}" if e.evidence_level else "level —"
            dis = e.disease or "—"
            tag = ("✓ this cancer type" if _matches(e.disease)
                   else "↔ other cancer (off-label evidence)")
            st.markdown(f"- {linkify(e.id)} · {lvl} · *{dis}* · {tag}: "
                        f"{(e.statement or '')[:160]}")
        if len(items) > 25:
            st.caption(f"… and {len(items) - 25} more from {source}")


@st.cache_data
def cohort_gene_context(gene: str):
    """Feature 3 — count cohort variants + distinct samples in the same gene."""
    res = load_results()
    if not res:
        return None
    same = [x for x in res.get("variants", []) if x.get("gene") == gene]
    if not same:
        return None
    samples = set()
    for x in same:
        samples.update(x.get("sample_ids") or [])
    return {"n_variants": len(same), "n_samples": len(samples)}


def _esc(s) -> str:
    """Minimal HTML escaping for the export string."""
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build_variant_html_report(v: dict, bundle) -> str:
    """Feature 4 — self-contained single-variant HTML report (research/education only)."""
    a, b = v["mode_a"], v["mode_b"]
    gene, hgvsp = v.get("gene", ""), v.get("hgvsp", "")
    cancer = v.get("cancer_type") or "context-free"

    def _call(m):
        s = f"{_esc(m.get('oncogenicity'))} / {_esc(m.get('tier'))}"
        if m.get("tier_level"):
            s += f" ({_esc(m['tier_level'])})"
        if m.get("abstained"):
            s += " · abstained"
        return s

    crit_rows = "".join(
        f"<tr><td><b>{_esc(r['code'])}</b></td><td>{_esc(r['meaning'])}</td>"
        f"<td>{_esc(r['points'])}</td><td>{_esc(r['fired in'])}</td></tr>"
        for r in _fired_criteria_rows(v)
    ) or "<tr><td colspan='4'>No named VICC criteria fired (call rests on evidence tier / VUS).</td></tr>"

    ct = (v.get("cancer_type") or "").lower()
    ev_rows = ""
    for e in bundle.evidences[:50]:
        dis = e.disease or "—"
        matched = bool(e.disease and ct and (e.disease.lower() in ct or ct in e.disease.lower()))
        tag = "this cancer type" if matched else "off-label"
        url = getattr(e, "url", None) or ""
        idcell = f'<a href="{_esc(url)}">{_esc(e.id)}</a>' if url else _esc(e.id)
        ev_rows += (f"<tr><td>{_esc(e.source)}</td><td>{idcell}</td>"
                    f"<td>{_esc(e.evidence_level or '—')}</td><td>{_esc(dis)}</td>"
                    f"<td>{_esc(tag)}</td><td>{_esc((e.statement or '')[:240])}</td></tr>")
    ev_rows = ev_rows or "<tr><td colspan='6'>No variant-specific evidence.</td></tr>"

    drugs = ", ".join(sorted({_esc(d.drug) for d in bundle.drugs})) or "none"
    trial_rows = "".join(
        f"<tr><td><a href='https://clinicaltrials.gov/study/{_esc(t.nct_id)}'>{_esc(t.nct_id)}</a></td>"
        f"<td>{_esc(t.phase or '—')}</td><td>{_esc(t.status or '—')}</td>"
        f"<td>{_esc(', '.join(t.conditions or []))}</td><td>{_esc((t.title or '')[:120])}</td></tr>"
        for t in bundle.trials) or "<tr><td colspan='5'>none</td></tr>"
    rel = ", ".join(_esc(x) for x in (v.get("related_cancers") or [])) or "—"

    bundle_ids = {e.id for e in bundle.evidences if e.id}
    for d in bundle.drugs:
        bundle_ids.update(getattr(d, "citations", None) or [])
    bundle_ids.update(t.nct_id for t in bundle.trials if getattr(t, "nct_id", None))
    cited = list(a.get("citations") or [])
    out_of_bundle = [c for c in cited if c not in bundle_ids]
    audit = (f"Generative mode cited {len(cited)} identifier(s); "
             f"{len(out_of_bundle)} out-of-bundle (ungrounded). "
             "Out-of-bundle citations = 0 by contract (faithfulness gate).")

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>VeriVar — {_esc(gene)} {_esc(hgvsp)}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#222;line-height:1.45}}
h1{{margin-bottom:.2rem}} h2{{border-bottom:2px solid #eee;padding-bottom:.2rem;margin-top:1.6rem}}
.disc{{background:#fde8e8;border:2px solid #e74c3c;color:#922;padding:.8rem 1rem;border-radius:8px;font-weight:600}}
table{{border-collapse:collapse;width:100%;font-size:.9rem;margin:.4rem 0}}
th,td{{border:1px solid #ddd;padding:.35rem .5rem;text-align:left;vertical-align:top}}
th{{background:#f5f5f5}} .calls{{display:flex;gap:1rem}} .calls>div{{flex:1;background:#f8f9fa;border-radius:8px;padding:.6rem 1rem}}
.muted{{color:#666;font-size:.85rem}}
</style></head><body>
<p class="disc">⚠️ Research / education / demo only — NOT for clinical use. Do not use to make any
clinical, diagnostic, or treatment (prescribing) decision.</p>
<h1>{_esc(gene)} {_esc(hgvsp)}</h1>
<p class="muted">Cancer context: {_esc(cancer)} · evidence tier: {_esc(v.get('evidence_tier'))} ·
{_esc(v.get('n_evidence'))} evidence · {_esc(v.get('n_drugs', 0))} drug(s) · {_esc(v.get('n_trials', 0))} trial(s)</p>
<h2>Calls</h2>
<div class="calls">
<div><b>Generative mode (LLM)</b><br>{_call(a)}<p>{_esc(a.get('rationale', ''))}</p></div>
<div><b>Deterministic mode (rule)</b><br>{_call(b)}<p>{_esc(b.get('rationale', ''))}</p></div>
</div>
<h2>VICC / ClinGen / CGC criteria fired (auditable)</h2>
<table><tr><th>code</th><th>meaning</th><th>points</th><th>fired in</th></tr>{crit_rows}</table>
<p class="muted">Meanings from the rule engine (Horak et al. 2022 point-based rules).</p>
<h2>Evidence</h2>
<table><tr><th>source</th><th>id</th><th>level</th><th>disease</th><th>match</th><th>statement</th></tr>{ev_rows}</table>
<h2>Drugs</h2><p>{drugs}</p>
<h2>Clinical trials</h2>
<table><tr><th>NCT</th><th>phase</th><th>status</th><th>conditions</th><th>title</th></tr>{trial_rows}</table>
<h2>Related cancers (inferred from evidence)</h2><p>{rel}</p>
<h2>Faithfulness / audit</h2><p class="muted">{_esc(audit)}</p>
<hr><p class="muted">Generated by VeriVar (dual-mode somatic variant interpretation, research/education demo).
Public data only (CIViC, DGIdb, AlphaMissense, ClinicalTrials.gov). Not for clinical use.</p>
</body></html>"""


def render_evidence_and_audit(v: dict, bundle):
    """Render the per-variant dual-mode detail, audit trail, and evidence list.

    Pure rendering of a single cohort-shaped variant dict ``v`` (the same shape
    produced by ``interpret_variants`` and by ``cohort_interpretation.json``)
    given its already-built :class:`EvidenceBundle`. Used by the Upload-VCF tab;
    the existing Variant-detail tab keeps its own inline rendering + chat
    unchanged.
    """
    a, b = v["mode_a"], v["mode_b"]
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Generative mode — LLM")
        st.markdown(f"**{a['oncogenicity']} / {a['tier']}**"
                    + (f" ({a['tier_level']})" if a.get("tier_level") else "")
                    + (" · ⚠️ abstained" if a.get("abstained") else ""))
        if a.get("confidence") is not None:
            st.caption(f"confidence {a.get('confidence')}")
        st.markdown(linkify(a.get("rationale", "")))
        if a.get("citations"):
            st.markdown("**cites:** " + linkify(", ".join(a["citations"])))
    with col2:
        st.markdown("### Deterministic mode — rule")
        st.markdown(f"**{b['oncogenicity']} / {b['tier']}**"
                    + (f" ({b['tier_level']})" if b.get("tier_level") else ""))
        st.write(b.get("rationale", ""))
    st.divider()
    st.caption(f"Evidence tier: {v['evidence_tier']} · {v['n_evidence']} evidence · "
               f"{v.get('n_drugs', 0)} drug(s) · {v.get('n_trials', 0)} trial(s)")
    render_criteria_fired(v)
    with st.expander("🧬 Protein context", expanded=False):
        render_protein_context(v["gene"], v["hgvsp"])
    rel = v.get("related_cancers") or []
    if rel:
        st.markdown("**Related cancers (inferred from evidence):** " + ", ".join(rel))
    st.markdown("🔗 **External:** " + ext_links(v["gene"], v["hgvsp"], v.get("cancer_type")))

    bundle_ids = {e.id for e in bundle.evidences if e.id}
    for d in bundle.drugs:
        bundle_ids.update(getattr(d, "citations", None) or [])
    bundle_ids.update(t.nct_id for t in bundle.trials if getattr(t, "nct_id", None))

    cited = list(a.get("citations") or [])
    for m in _EID_RE.finditer(a.get("rationale", "")):
        cid = f"CIViC:EID{m.group(1)}"
        if cid not in cited:
            cited.append(cid)
    for m in _NCT_RE.finditer(a.get("rationale", "")):
        if m.group(1) not in cited:
            cited.append(m.group(1))
    grounded = [c for c in cited if c in bundle_ids]
    out_of_bundle = [c for c in cited if c not in bundle_ids]
    n_onco = a.get("oncogenicity", "")
    claim_no_source = (not a.get("abstained")) and (not cited) and \
        n_onco not in ("", "—", "VUS", "Uncertain", "Uncertain significance")
    badge = "❌" if out_of_bundle else ("⚠️" if claim_no_source else "✓")
    with st.expander(f"🔍 Audit trail — Generative mode  ({badge} "
                     f"{len(grounded)} grounded / {len(out_of_bundle)} out-of-bundle)"):
        st.caption(
            "Every assertion is traceable to a retrieved identifier. "
            "**Out-of-bundle citations = 0 by contract** — any non-zero value here is a "
            "hallucinated/ungrounded citation and the reason this view exists.")
        if a.get("abstained"):
            st.success("✅ Generative mode **abstained** (VUS) / not run — honest behaviour "
                       "when variant-specific evidence is absent. Not an error.")
        elif claim_no_source:
            st.warning(f"⚠️ Generative mode made a non-abstained **{n_onco}** call with **zero cited "
                       "sources** — a claim without a cited source.")
        if grounded:
            st.markdown("**Grounded (in bundle ✓):** "
                        + linkify(" · ".join(f"{c}" for c in grounded)))
        if out_of_bundle:
            st.error("**Out-of-bundle (✗ ungrounded):** " + linkify(" · ".join(out_of_bundle)))
        elif cited:
            st.caption("All cited identifiers resolve to the retrieved evidence bundle.")
        st.caption(f"Bundle holds {len(bundle_ids)} citable identifier(s); "
                   f"Generative mode cited {len(cited)}.")

    with st.expander(f"📚 Evidence · drugs · trials  "
                     f"({len(bundle.evidences)} evidence, {len(bundle.drugs)} drugs, {len(bundle.trials)} trials)"):
        render_grouped_evidence(bundle, v.get("cancer_type"))
        if bundle.drugs:
            st.markdown("**Drugs:** "
                        + ", ".join(drug_link(d) for d in sorted({d.drug for d in bundle.drugs})))
            st.caption("Drugs are gene-level DGIdb context for lookup — "
                       "not variant-specific actionability.")
        if bundle.trials:
            st.markdown("**Trials:** " + ", ".join(linkify(t.nct_id) for t in bundle.trials))


_ICON = str(_PROJECT_ROOT / "docs/branding/verivar_icon_256.png")
st.set_page_config(page_title="VeriVar — Somatic Variant Interpretation",
                   page_icon=_ICON, layout="wide")
st.logo(_ICON, size="large")
_logo_col, _title_col = st.columns([1, 11], vertical_alignment="center")
_logo_col.image(_ICON, width=60)
_title_col.title("VeriVar")
st.caption("Faithful, citation-grounded somatic variant interpretation · Generative mode (LLM) vs Deterministic mode (rule). Research/education only — not for clinical use.")

with st.expander("ℹ️ How to use this dashboard", expanded=False):
    st.markdown(
        """
**What this is.** Each somatic variant is classified two ways and compared:
- **Generative mode (LLM)** — a language model reads the retrieved evidence and assigns the classification.
- **Deterministic mode (rule)** — a deterministic rule engine assigns it; the LLM only explains.
- Each variant gets two axes: **oncogenicity** (VICC) and **clinical tier** (AMP/ASCO/CAP).
- **Discordant** (⚡) variants — where the two modes disagree — are the analytical signal.

**The four tabs**
1. **Overview** — leads with the **Faithfulness scorecard** (hallucinated-citation rate, citation grounding,
   directional faithfulness, abstention recall — guarantees enforced by construction; plus the *measured*
   no-retrieval 46.4% → 0 fabrication contrast), then cohort concordance and discordance by cancer type.
2. **Variant explorer** — a sortable, filterable table of every cohort variant. **Click a column header to sort.**
   Use the **search box** and **filters** (CIViC evidence / drugs / trials / discordant / abstained); download
   the filtered set as CSV. (Clearing a filter means "no filter", not "exclude everything".)
3. **Variant detail** — a per-variant card view: **Summary** (+ how often the gene is mutated in this cohort),
   the two **Calls** side-by-side, **Criteria fired** (which ClinGen/CGC/VICC criteria drove the call),
   **Protein context** (domain track + this variant's position), a prominent **grounded chat**, **Evidence**
   grouped by source/level with an **audit trail** (every citation traced; out-of-bundle = 0 by contract),
   **Drugs & trials**, external links (OncoKB/ClinVar/cBioPortal/COSMIC/DGIdb), and a **per-variant HTML report** download.
4. **Upload VCF (beta)** — interpret *your own* variants. Paste or upload a VCF; the **genome build is
   auto-detected** from the header (GRCh37/GRCh38, with override + a mismatch warning). Choose
   **"Annotate only (VEP)"** (gene · HGVSp · consequence · impact · rsID · gnomAD AF · SIFT/PolyPhen) or full
   interpretation; AlphaMissense is fetched live from Ensembl VEP for uploads. Download the **VEP annotation
   (CSV)**, a **combined (CSV)**, or as **VCF**. **Research/education only — do not upload private/patient data.**

**Grounded chat (Variant detail).** Ask a question about the *selected* variant. It answers **only** from the
retrieved evidence and **abstains** ("I cannot answer from the available evidence") when the evidence doesn't
cover the question — that's the intended faithfulness behavior, not a bug.

**Note — the citable VICC rule arm (not shown here).** Beyond the two modes above, the manuscript also
evaluates a separate **citable VICC rule arm**: a deterministic ClinGen/CGC/VICC point-based engine
(**not the LLM**) that carries the headline accuracy result (3-class accuracy **0.843** on the external
**Horak-70** benchmark). That arm is scored on that external benchmark, **not run per-variant in this cohort
view** — the cohort data shown here contains only the Generative and Deterministic modes, so there is no
per-variant VICC column.

**Tips**
- Filter to *Clinical trial(s)* to find variants with trials; *LLM abstained only* to see honest-abstention cases.
- Compare the same variant across cancers (e.g. **BRAF V600E** in Melanoma vs Colorectal) to see context-dependent tiering.
- In **Variant detail**, **BRAF V600E** is a good example of a fully-populated Criteria-fired + Protein-context + evidence view.
- In **Upload VCF**, **"Annotate only (VEP)"** is fast (no evidence/interpretation); the full run adds the dual-mode calls + AlphaMissense and lets you export a VCF.
        """
    )

data = load_results()
if data is None:
    st.warning("No results found. Run `python -m src.pipeline` first.")
    st.stop()

variants = data["variants"]
summary = data["discordance_summary"]

cancers = sorted({v["cancer_type"] for v in variants})
tiers = sorted({v["evidence_tier"] for v in variants})
prov = data.get("provenance", {})
st.sidebar.header("Run info")
st.sidebar.markdown(f"**Model:** {prov.get('model_name','n/a')}  \n"
                    f"**Run:** {prov.get('timestamp','')}  \n"
                    f"**Variants:** {len(variants)}")
st.sidebar.caption("🔎 Filters are in the **Variant explorer** tab. "
                   "The same filter applies to the Variant detail dropdown.")

tab_overview, tab_explore, tab_detail, tab_upload = st.tabs(
    ["Overview", "Variant explorer", "Variant detail", "Upload VCF (beta)"])

with tab_overview:
    # ── Faithfulness scorecard (the headline) ─────────────────────────────
    # Every number here is read live from the committed result JSONs.
    ev = load_json("eval_report.json")
    norag = load_json("faithfulness_real_norag.json")
    stats = load_json("stats_report.json")
    if ev:
        st.subheader("Faithfulness (the headline)")
        hall = ev.get("hallucination", {})
        grnd = ev.get("citation_grounding", {})
        dire = ev.get("directional_faithfulness", {})
        abst = ev.get("abstention", {})
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("Hallucinated-citation rate",
                  _pct(hall.get("hallucination_rate")),
                  help="Cited identifiers absent from the evidence bundle. "
                       "0 is enforced by construction (out-of-bundle citations are dropped).")
        f2.metric("Citation grounding",
                  _pct(grnd.get("grounding_rate")),
                  help="Share of cited identifiers that resolve to a retrieved evidence item.")
        f3.metric("Directional faithfulness",
                  _pct(dire.get("faithfulness_rate")),
                  help="Calls whose direction agrees with the cited evidence direction. "
                       "1.0 is enforced by the directional gate.")
        f4.metric("Abstention recall",
                  _pct(abst.get("abstention_recall")),
                  help="Of variants with no variant-specific evidence, the share where Generative mode "
                       "correctly abstained (VUS). 1.0 is enforced.")

        # The falsifiable contrast: no-retrieval fabrication vs with-retrieval 0.
        fab_ci = (stats or {}).get("norag_citation_fabrication_ci") or {}
        norag_rate = None
        if norag:
            norag_rate = (norag.get("before_enforcement") or {}).get("ungrounded_citation_rate")
        if norag_rate is None:
            norag_rate = fab_ci.get("point")
        if norag_rate is not None:
            rag_rate = hall.get("hallucination_rate", 0.0) or 0.0
            cc1, cc2 = st.columns([1, 1.4])
            with cc1:
                ci_txt = ""
                if fab_ci.get("lo") is not None and fab_ci.get("hi") is not None:
                    ci_txt = f"95% CI {_pct(fab_ci['lo'])}–{_pct(fab_ci['hi'])}"
                st.metric(
                    "Citation fabrication — no retrieval",
                    _pct(norag_rate),
                    delta=f"{(rag_rate - norag_rate) * 100:+.1f} pts with retrieval",
                    delta_color="inverse",
                    help="Same real model with no evidence bundle: every emitted citation is "
                         "ungrounded. With retrieval + the gate this drops to 0.")
                if ci_txt:
                    st.caption(ci_txt)
            with cc2:
                contrast = pd.DataFrame(
                    {"citation fabrication rate": [norag_rate, rag_rate]},
                    index=["no retrieval", "with retrieval"])
                st.bar_chart(contrast)
        st.caption(
            "1.0 / 0.0 values are **guarantees enforced by construction** (deterministic "
            "faithfulness gate), not emergent model behaviour. The "
            f"{_pct(norag_rate) if norag_rate is not None else 'no-retrieval'} → "
            f"{_pct(hall.get('hallucination_rate'))} citation-fabrication contrast is the "
            "**measured, falsifiable finding**. Research/education only — not for clinical use.")
        ep = ev.get("provenance", {})
        if ep:
            st.caption(
                f"Source: eval_report.json · {ep.get('mode_used','?')} run · "
                f"model {ep.get('model_name','?')} · {ep.get('timestamp','')} · "
                f"n={ev.get('n_variants','?')}.")
        st.divider()

    o = summary["overall"]
    st.subheader("Cohort concordance")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Variants", len(variants))
    c2.metric("Tier concordance", f"{o['tier_concordance_rate']*100:.1f}%")
    c3.metric("Oncogenicity concordance", f"{o['oncogenicity_concordance_rate']*100:.1f}%")
    c4.metric("Discordant", o["any_discordant"])
    st.subheader("Discordance by cancer type")
    by_cancer = pd.DataFrame([
        {"cancer": k, "n": r["n"], "tier_discordant": r["tier_discordant"],
         "oncogenicity_discordant": r["oncogenicity_discordant"]}
        for k, r in summary["by_cancer"].items()
    ]).set_index("cancer")
    st.bar_chart(by_cancer[["tier_discordant", "oncogenicity_discordant"]])

    # Typed discordance breakdown (from scripts.analyze_discordance), if present.
    disc_path = _PROJECT_ROOT / "data/outputs/discordance_analysis.json"
    if disc_path.exists():
        da = json.loads(disc_path.read_text())
        st.subheader("Discordance types")
        st.caption(f"{da['n_discordant']} discordant — {da['adjacent']} adjacent (1 step), "
                   f"{da['gross']} gross. LLM more conservative in {da['llm_more_conservative']}.")
        labels = {
            "rule_overcall_corrected_by_llm": "Rule over-calls → LLM not a driver (beyond-rules)",
            "llm_overcall_vs_rule": "LLM driver; rule not",
            "verifier_tier_downgrade": "Verifier tier downgrade",
            "oncogenic_confidence": "Oncogenic vs Likely Oncogenic",
            "benign_label": "VUS vs Likely Benign",
            "tier_boundary": "Same oncogenicity, adjacent tier",
            "other": "Other",
        }
        st.dataframe(pd.DataFrame(
            [{"type": labels.get(k, k), "count": n} for k, n in da["category_counts"].items()]),
            use_container_width=True, hide_index=True)

with tab_explore:
    st.markdown("#### Filters")
    fc1, fc2, fc3 = st.columns([2, 2, 2])
    search = fc1.text_input("🔍 Search gene / variant / cancer", placeholder="e.g. BRAF, V600E, melanoma")
    sel_cancers = fc2.multiselect("Cancer type", cancers, default=cancers)
    sel_tiers = fc3.multiselect("Evidence tier", tiers, default=tiers,
                                help="civic = clinical · alphamissense = computational · none = no evidence")
    b1, b2, b3, b4, b5 = st.columns(5)
    need_civic = b1.checkbox("CIViC evidence")
    need_drugs = b2.checkbox("Has drug(s)")
    need_trials = b3.checkbox("Has trial(s)")
    disc_only = b4.checkbox("Discordant ⚡")
    abstain_only = b5.checkbox("LLM abstained")
    lowconf_only = st.checkbox("Low confidence only (Generative mode agreement < 0.7)")

    # An emptied multiselect means "no filter on this field", not "exclude everything".
    sel_cancers = sel_cancers or cancers
    sel_tiers = sel_tiers or tiers

    def _keep(v: dict) -> bool:
        if v["cancer_type"] not in sel_cancers or v["evidence_tier"] not in sel_tiers:
            return False
        if search and search.lower() not in f"{v['gene']} {v['hgvsp']} {v['cancer_type']}".lower():
            return False
        if disc_only and not v["discordant"]:
            return False
        if abstain_only and not v["mode_a"]["abstained"]:
            return False
        if lowconf_only and (v["mode_a"].get("confidence") or 1.0) >= 0.7:
            return False
        if need_civic and v["evidence_tier"] != "civic":
            return False
        if need_drugs and v.get("n_drugs", 0) == 0:
            return False
        if need_trials and v.get("n_trials", 0) == 0:
            return False
        return True

    flt = [v for v in variants if _keep(v)]

    st.divider()
    st.subheader(f"{len(flt)} variants · {sum(v['discordant'] for v in flt)} discordant")
    if not flt:
        st.info(f"No variants match the current filters. Clear the filters above to see all {len(variants)}.")
    else:
        st.caption("Click a column header to sort. Filters above also drive the Variant detail tab.")
        rows = [{
            "variant": f"{v['gene']} {v['hgvsp']}", "cancer": v["cancer_type"],
            "evidence": v["evidence_tier"],
            "CIViC": "✓" if v["evidence_tier"] == "civic" else "",
            "drugs": v.get("n_drugs", 0),
            "trials": v.get("n_trials", 0),
            "Generative (LLM)": f"{v['mode_a']['oncogenicity']} / {v['mode_a']['tier']}"
                            + (" ⚠" if v["mode_a"]["abstained"] else ""),
            "conf": v["mode_a"].get("confidence"),
            "Deterministic (rule)": f"{v['mode_b']['oncogenicity']} / {v['mode_b']['tier']}",
            "⚡": "⚡" if v["discordant"] else "",
        } for v in flt]
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption("⚡ = discordant — the Generative and Deterministic modes disagree on this variant.")
        # CSV: replace the on-screen ⚡ marker with a plain boolean `discordant` column.
        csv_df = df.drop(columns=["⚡"]).copy()
        csv_df["discordant"] = [bool(v["discordant"]) for v in flt]
        st.download_button("⬇ Download filtered CSV", csv_df.to_csv(index=False),
                           "variants_filtered.csv", "text/csv")

with tab_detail:
    labels = [f"{v['gene']} {v['hgvsp']} — {v['cancer_type']}" for v in flt]
    if not labels:
        st.info("No variants match the current filters.")
    else:
        idx = st.selectbox("Select a variant", range(len(labels)), format_func=lambda i: labels[i])
        v = flt[idx]
        a, b = v["mode_a"], v["mode_b"]

        from src.models import EvidenceBundle, Variant
        # Build the selected variant's bundle once (grounding source for the chat).
        if v.get("bundle"):
            bundle = EvidenceBundle.model_validate(v["bundle"])
        else:
            agg, kg = get_aggregator_kg()
            bundle = agg.for_variant_obj(
                Variant(chrom="", pos=0, ref="", alt="", gene=v["gene"], hgvsp=v["hgvsp"],
                        cancer_type=v["cancer_type"], variant_type=v["variant_type"]))
        srcs = sorted({e.source for e in bundle.evidences})

        # ── ① Summary (gene/hgvsp/cancer + cohort context) ────────────────
        with st.container(border=True):
            st.subheader(f"① {v['gene']} {v['hgvsp']} — {v['cancer_type']}")
            st.caption(f"Evidence tier: {v['evidence_tier']} · {v['n_evidence']} evidence · "
                       f"{v['n_drugs']} drug(s) · {v['n_trials']} trial(s) · "
                       f"samples: {', '.join(v.get('sample_ids', [])) or '—'}")
            # Feature 3 — cohort frequency context (from our own cohort).
            ctx = cohort_gene_context(v["gene"])
            if ctx:
                st.markdown(
                    f"📊 **Cohort context:** {ctx['n_variants']} variant(s) in **{v['gene']}** "
                    f"across **{ctx['n_samples']}** distinct sample(s) in this demo cohort.")
            else:
                st.markdown(f"📊 **Cohort context:** *{v['gene']} not present in the demo cohort.*")

        # ── ② Calls (Generative vs Deterministic, side by side) ───────────
        with st.container(border=True):
            st.subheader("② Calls — Generative vs Deterministic")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### Generative mode — LLM")
                st.markdown(f"**{a['oncogenicity']} / {a['tier']}**"
                            + (f" ({a['tier_level']})" if a.get("tier_level") else "")
                            + (" · ⚠️ abstained" if a["abstained"] else ""))
                st.caption(f"confidence {a.get('confidence')}")
                st.markdown(linkify(a["rationale"]))
                if a.get("citations"):
                    st.markdown("**cites:** " + linkify(", ".join(a["citations"])))
            with col2:
                st.markdown("### Deterministic mode — rule")
                st.markdown(f"**{b['oncogenicity']} / {b['tier']}**"
                            + (f" ({b['tier_level']})" if b.get("tier_level") else ""))
                st.write(b["rationale"])

        # ── ③ Criteria fired (the auditability headline) ──────────────────
        with st.container(border=True):
            st.subheader("③ Criteria fired")
            render_criteria_fired(v)

        # ── Protein context (domain map + variant lollipop) ───────────────
        with st.container(border=True):
            st.subheader("🧬 Protein context")
            render_protein_context(v["gene"], v["hgvsp"])

        # ── ④ Grounded chat (kept prominent) ──────────────────────────────
        # Grounds strictly on the selected variant's persisted `bundle`; abstains
        # when that evidence doesn't cover the question.
        with st.container(border=True):
            st.subheader("④ 💬 Ask about this variant")
            st.caption(
                f"Answers **only** from the **selected** variant's "
                f"({v['gene']} {v['hgvsp']} — {v['cancer_type']}) retrieved evidence "
                f"and abstains (\"I cannot answer from the available evidence\") when "
                f"that evidence doesn't cover your question.  ·  "
                f"To ask about a different variant, change the dropdown above.  ·  "
                f"Evidence available: **{len(bundle.evidences)}** item(s)"
                + (f" from {', '.join(srcs)}" if srcs else " — none (will abstain)"))
            q = st.text_input(f"Your question about {v['gene']} {v['hgvsp']}",
                              placeholder="e.g. Is this variant actionable in this cancer?")
            if q:
                try:
                    llm = get_llm()
                    var = Variant(chrom="", pos=0, ref="", alt="", gene=v["gene"], hgvsp=v["hgvsp"],
                                  cancer_type=v["cancer_type"], variant_type=v["variant_type"])
                    with st.spinner(f"Answering about {v['gene']} {v['hgvsp']} from {len(bundle.evidences)} evidence item(s)…"):
                        answer = llm.answer_question(var, bundle, q)
                    st.markdown(linkify(answer))
                    if not bundle.evidences:
                        st.caption("No variant-specific evidence for this variant — the assistant abstains.")
                except Exception as e:  # noqa: BLE001
                    st.error(f"Chat unavailable: {e}")

        # ── ⑤ Evidence (grouped by source + level, with audit trail) ──────
        with st.container(border=True):
            st.subheader("⑤ Evidence")

            # Per-claim audit trail (Generative mode / mode_a). The set of identifiers
            # Generative mode was allowed to cite: evidence ids, drug citations, trial NCTs.
            bundle_ids = {e.id for e in bundle.evidences if e.id}
            for d in bundle.drugs:
                bundle_ids.update(getattr(d, "citations", None) or [])
            bundle_ids.update(t.nct_id for t in bundle.trials if getattr(t, "nct_id", None))

            cited = list(a.get("citations") or [])
            for m in _EID_RE.finditer(a.get("rationale", "")):
                cid = f"CIViC:EID{m.group(1)}"
                if cid not in cited:
                    cited.append(cid)
            for m in _NCT_RE.finditer(a.get("rationale", "")):
                if m.group(1) not in cited:
                    cited.append(m.group(1))

            grounded = [c for c in cited if c in bundle_ids]
            out_of_bundle = [c for c in cited if c not in bundle_ids]
            n_onco = a.get("oncogenicity", "")
            claim_no_source = (not a.get("abstained")) and (not cited) and \
                n_onco not in ("", "VUS", "Uncertain", "Uncertain significance")

            badge = "❌" if out_of_bundle else ("⚠️" if claim_no_source else "✓")
            with st.expander(f"🔍 Audit trail — Generative mode  ({badge} "
                             f"{len(grounded)} grounded / {len(out_of_bundle)} out-of-bundle)"):
                st.caption(
                    "Every assertion is traceable to a retrieved identifier. "
                    "**Out-of-bundle citations = 0 by contract** — any non-zero value here is a "
                    "hallucinated/ungrounded citation and the reason this view exists.")
                if a.get("abstained"):
                    st.success("✅ Generative mode **abstained** (VUS) — correct faithfulness behaviour when "
                               "variant-specific evidence is absent or insufficient. Not a defect.")
                elif claim_no_source:
                    st.warning(f"⚠️ Generative mode made a non-abstained **{n_onco}** call with **zero cited "
                               "sources** — a claim without a cited source.")
                if grounded:
                    st.markdown("**Grounded (in bundle ✓):** "
                                + linkify(" · ".join(f"{c}" for c in grounded)))
                if out_of_bundle:
                    st.error("**Out-of-bundle (✗ ungrounded):** "
                             + linkify(" · ".join(out_of_bundle)))
                elif cited:
                    st.caption("All cited identifiers resolve to the retrieved evidence bundle.")
                st.caption(f"Bundle holds {len(bundle_ids)} citable identifier(s); "
                           f"Generative mode cited {len(cited)}.")

            with st.expander(f"📚 Evidence by source ({len(bundle.evidences)} item(s))",
                             expanded=True):
                render_grouped_evidence(bundle, v.get("cancer_type"))

        # ── ⑥ Drugs & trials ──────────────────────────────────────────────
        with st.container(border=True):
            st.subheader("⑥ Drugs & trials")
            if bundle.drugs:
                st.markdown("**Drugs:** "
                            + ", ".join(drug_link(d) for d in sorted({d.drug for d in bundle.drugs})))
                st.caption("Drugs are gene-level DGIdb context for lookup — "
                           "not variant-specific actionability.")
            if bundle.trials:
                st.markdown("**Trials:**")
                for t in bundle.trials:
                    phase = f" · {t.phase}" if t.phase else ""
                    status = f" · {t.status}" if t.status else ""
                    conds = f" · {', '.join(t.conditions)}" if t.conditions else ""
                    st.markdown(f"- {linkify(t.nct_id)}{phase}{status}{conds}: "
                                f"{(t.title or '')[:120]}")
            if not bundle.drugs and not bundle.trials:
                st.caption("No drugs or trials linked to this variant's evidence.")
            rel = v.get("related_cancers") or []
            if rel:
                st.markdown("**Related cancers (inferred from evidence):** " + ", ".join(rel))

        # ── ⑦ External links + export ─────────────────────────────────────
        with st.container(border=True):
            st.subheader("⑦ External links & export")
            st.markdown("🔗 **External:** " + ext_links(v["gene"], v["hgvsp"], v.get("cancer_type")))
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", f"{v['gene']}_{v['hgvsp']}")
            st.download_button(
                "⬇ Download this variant's HTML report",
                build_variant_html_report(v, bundle),
                file_name=f"verivar_{safe}.html",
                mime="text/html",
                help="Self-contained, offline HTML report for this variant. "
                     "Research/education only — not for clinical use.")

def _load_example_vcf():
    """Fill the paste box with a committed public sample VCF (callback: runs
    before the rerun, so writing the widget's session_state key is allowed)."""
    p = _PROJECT_ROOT / "data/examples/sample_actionable_grch38.vcf"
    try:
        st.session_state["up_text"] = p.read_text()
    except Exception:  # noqa: BLE001
        st.session_state["up_text"] = ""


with tab_upload:
    st.subheader("Upload VCF — interpret your own variants (beta)")
    st.error(
        "⚠️ **Research / education / demo only — NOT for clinical use.** "
        "Do not use these outputs to make any clinical or treatment decision.")
    st.warning(
        "🔒 **Privacy.** Your VCF stays in this browser session's memory only — it is **not "
        "saved to disk and its contents are not logged**. Annotation calls Ensembl VEP "
        "(a public web service) with genomic coordinates only. If you enable Generative "
        "(LLM) mode, the retrieved evidence text is additionally sent to the OpenAI API. "
        "**Do not upload private or patient-identifiable data.**")

    st.markdown("#### ✅ Step 0 · Acknowledge to begin")
    _ackbox = st.container(border=True)
    ack = _ackbox.checkbox(
        "**I understand this is not for clinical use** — tick to enable the Run button.",
        key="up_ack")

    st.markdown("#### 1 · Provide variants")
    up = st.file_uploader("Upload a VCF (.vcf / .txt)", type=["vcf", "txt"], key="up_file")
    pasted = st.text_area(
        "…or paste VCF text",
        height=160,
        placeholder="#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n7\t140453136\t.\tA\tT\t.\tPASS\t.",
        key="up_text",
        help="Either an uploaded file or pasted text works. If you provide both, the uploaded file is used.")
    st.button(
        "📄 Load example (public driver hotspots, GRCh38)",
        on_click=_load_example_vcf,
        key="up_load_example")
    st.caption(
        "Example = 6 public driver hotspots (BRAF V600E, EGFR L858R, KRAS G12C/D/V, "
        "PIK3CA R88Q) lifted to GRCh38 — for trying the tool. Research/education only, "
        "**not your data**. If you also upload a file, the uploaded file takes "
        "precedence over pasted text.")

    # Read the raw VCF text (upload preferred over paste) EARLY so the genome
    # build can be auto-detected before the assembly selectbox renders.
    # Never persisted.
    vcf_text = ""
    if up is not None:
        try:
            vcf_text = up.getvalue().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read the uploaded file: {e}")
    elif pasted.strip():
        vcf_text = pasted

    # Auto-detect genome build from the VCF header (only when there's input).
    detected = None
    if vcf_text.strip():
        try:
            from src.cohort.vcf_loader import detect_assembly
            detected = detect_assembly(vcf_text)
        except Exception:  # noqa: BLE001
            detected = None

    st.markdown("#### 2 · Context")
    uc1, uc2 = st.columns(2)
    _asm_opts = ["GRCh37", "GRCh38"]
    _asm_idx = _asm_opts.index(detected) if detected in _asm_opts else 0
    # Make the detected build the actual default by seeding session_state BEFORE the
    # widget is created — but only when detection is NEW, so a deliberate manual
    # override (detected unchanged across reruns) is not clobbered every rerun.
    if detected and detected != st.session_state.get("_up_last_detected"):
        st.session_state["up_assembly"] = detected
        st.session_state["_up_last_detected"] = detected
    assembly = uc1.selectbox("Genome assembly", _asm_opts, index=_asm_idx, key="up_assembly")
    assembly = st.session_state["up_assembly"]
    if detected and assembly != detected:
        uc1.warning(
            f"⚠️ You selected **{assembly}** but the VCF header indicates **{detected}**. "
            "Annotating on the wrong genome build maps to the wrong loci and gives "
            "incorrect results — match the build unless you are sure.")
    elif detected:
        uc1.caption(f"🧬 Detected **{detected}** from the VCF header — override if needed.")
    elif vcf_text.strip():
        uc1.caption("No genome build found in the VCF header; defaulting to GRCh37 — "
                    "set it manually if needed.")
    AUTO_CANCER = "Auto — infer related cancers from evidence"
    cancer_choices = [AUTO_CANCER] + cancers + ["Other (type below)"]
    cancer_sel = uc2.selectbox("Cancer type (optional — tiering is context-dependent)",
                               cancer_choices, index=0, key="up_cancer_sel")
    if cancer_sel == AUTO_CANCER:
        cancer_type = None
        st.caption("Auto: no cancer context is assumed. Tiering runs context-free and each "
                   "variant's **related cancers** are inferred from its retrieved evidence.")
    elif cancer_sel == "Other (type below)":
        cancer_type = st.text_input("Enter cancer type", key="up_cancer_other",
                                    placeholder="e.g. Pancreatic Adenocarcinoma").strip() or None
    else:
        cancer_type = cancer_sel

    st.markdown("#### 3 · Mode")
    annotate_only = st.toggle(
        "Annotate only (VEP) — skip interpretation", value=False, key="up_annotate_only")
    if annotate_only:
        st.info(
            "**Annotate-only**: runs `parse_vcf` → Ensembl **VEP** mapping (coordinates → gene + "
            "protein change) and stops. No evidence retrieval, AlphaMissense, or classification — "
            "much faster. The Generative-mode toggle below is ignored. (VEP still uses the network.)")
    use_llm = st.toggle("Run Generative (LLM) mode", value=False, key="up_use_llm",
                        disabled=annotate_only)
    if annotate_only:
        pass
    elif use_llm:
        st.warning(
            "Calls the OpenAI API — needs `OPENAI_API_KEY` on the server (paid). **Optional**: "
            "without a key it's skipped and you still get the rule-based result. Don't upload "
            "private/patient data.")
    else:
        st.info(
            "Offline — rule-based arm only; no OpenAI call. (VEP annotation still uses the network.)")

    # Soft cap warning: annotation is one VEP call per variant.
    parsed_preview = []
    if vcf_text.strip():
        try:
            from src.cohort.vcf_loader import parse_vcf
            parsed_preview = parse_vcf(vcf_text)
        except Exception:  # noqa: BLE001
            parsed_preview = []
    if len(parsed_preview) > 50:
        st.warning(
            f"~{len(parsed_preview)} records detected. Annotation is **one Ensembl VEP call per "
            "variant**, so this may be slow. Consider trimming to your variants of interest.")

    have_input = bool(vcf_text.strip())
    run = st.button(
        "▶ Annotate only (VEP)" if annotate_only else "▶ Annotate & interpret",
        type="primary",
        disabled=not (ack and have_input),
        key="up_run")
    if not ack:
        st.caption("Tick the acknowledgement above to enable the Run button.")
    elif not have_input:
        st.caption("Provide a VCF (upload or paste) to enable the Run button.")

    # --- Compute on Run; persist plain-data results so widget reruns don't drop them. ---
    if run:
        from src.cohort.vcf_loader import parse_vcf, annotate_variants
        from src.interpret import interpret_variants

        records = parse_vcf(vcf_text)
        if not records:
            st.session_state.pop("up_res", None)
            st.error("No usable variant records found. Provide tab-delimited VCF rows with "
                     "CHROM / POS / REF / ALT columns (a `#CHROM` header line is fine).")
        else:
            try:
                if annotate_only:
                    spinner_msg = "Annotating via Ensembl VEP (coordinates → gene + protein)…"
                else:
                    spinner_msg = ("Annotating via Ensembl VEP… building evidence (first run "
                                   "loads the index)… interpreting…")
                retriever = None if annotate_only else get_upload_retriever()
                with st.spinner(spinner_msg):
                    ar = annotate_variants(records, assembly=assembly, cancer_type=cancer_type)
                    if annotate_only:
                        results = None
                    else:
                        results = interpret_variants(ar.variants, use_llm=use_llm,
                                                     retriever=retriever, am_online=True)
                # VEP annotation rows (available in BOTH modes). Carry the
                # enriched v.vep fields so the annotate-only table/CSV is richer.
                def _pred(d):
                    """Render a SIFT/PolyPhen dict as 'prediction(score)' / ''."""
                    if not isinstance(d, dict):
                        return d or ""
                    pred = d.get("prediction")
                    score = d.get("score")
                    if pred is None:
                        return ""
                    return f"{pred}({score})" if score is not None else f"{pred}"

                annotation = []
                for v in ar.variants:
                    vep = v.vep or {}
                    annotation.append({
                        "chrom": v.chrom,
                        "pos": v.pos,
                        "ref": v.ref,
                        "alt": v.alt,
                        "gene": v.gene,
                        "hgvsp": v.hgvsp,
                        "variant_type": getattr(v.variant_type, "value", v.variant_type),
                        "assembly": getattr(v.assembly, "value", v.assembly),
                        "consequence": vep.get("consequence") or "",
                        "impact": vep.get("impact") or "",
                        "transcript_id": vep.get("transcript_id") or "",
                        "hgvsc": vep.get("hgvsc") or "",
                        "protein_position": vep.get("protein_position") or "",
                        "amino_acids": vep.get("amino_acids") or "",
                        "rsid": vep.get("rsid") or "",
                        "gnomad_af": vep.get("gnomad_af") if vep.get("gnomad_af") is not None else "",
                        "sift": _pred(vep.get("sift")),
                        "polyphen": _pred(vep.get("polyphen")),
                    })
                skipped = []
                for s in ar.skipped:
                    rec = s.record or {}
                    skipped.append({
                        "loc": f"{rec.get('chrom','?')}:{rec.get('pos','?')} "
                               f"{rec.get('ref','?')}>{rec.get('alt','?')}",
                        "reason": s.reason,
                    })
                # Derive a sanitized base name from the uploaded file (if any)
                # for use in every download file_name. Falls back to a default
                # for pasted-only input or an empty stem.
                basename = "uploaded_variants"
                if up is not None and getattr(up, "name", None):
                    import os as _os
                    import re as _re
                    stem = _os.path.basename(up.name)
                    if stem.lower().endswith(".gz"):
                        stem = stem[:-3]
                    if stem.lower().endswith(".vcf"):
                        stem = stem[:-4]
                    elif stem.lower().endswith(".txt"):
                        stem = stem[:-4]
                    stem = _re.sub(r"[^A-Za-z0-9._-]", "_", stem)
                    if stem:
                        basename = stem
                st.session_state["up_res"] = {
                    "results": results,
                    "annotation": annotation,
                    "assembly": assembly,
                    "basename": basename,
                    "annotate_only": annotate_only,
                    "n_records": len(records),
                    "n_annotated": len(ar.variants),
                    "skipped": skipped,
                    "retriever_used": retriever is not None,
                    "cancer_type": cancer_type,
                    "use_llm": use_llm,
                }
            except Exception as e:  # noqa: BLE001
                st.session_state.pop("up_res", None)
                st.error(f"Annotation/interpretation failed: {e}")

    # --- Render from persisted state (survives the download-button / widget reruns). ---
    up_res = st.session_state.get("up_res")
    if up_res:
        from src.models import EvidenceBundle
        from src.cohort.vcf_loader import to_annotated_vcf

        results = up_res["results"]
        skipped = up_res["skipped"]
        annotation = up_res.get("annotation") or []
        annotate_only_r = up_res.get("annotate_only", False)
        # Genome build for the VCF header: prefer the run's stored assembly,
        # else derive from the first annotation row.
        assembly_r = up_res.get("assembly") or (
            (annotation[0].get("assembly") if annotation else None) or "GRCh37")
        retriever_used = up_res["retriever_used"]
        cancer_type_r = up_res["cancer_type"]
        use_llm_r = up_res["use_llm"]
        base = up_res.get("basename", "uploaded_variants")

        st.success(
            f"**{up_res['n_records']} parsed · {up_res['n_annotated']} annotated · "
            f"{len(skipped)} skipped.**"
            + ("  *(annotate-only — interpretation skipped.)*" if annotate_only_r else ""))

        # --- VEP annotation table + download (annotate-only mode only). ---
        # In FULL mode the VEP fields surface via the combined CSV / VCF exports,
        # so the standalone VEP table/CSV is skipped to avoid duplication.
        if annotation and annotate_only_r:
            st.markdown("#### VEP annotation (coordinates → gene + protein change)")
            st.caption(
                "🔎 **VEP** (Ensembl Variant Effect Predictor) maps each variant's "
                "coordinates to the affected gene, transcript, protein change, and "
                "predicted consequence. "
                "[Ensembl VEP ↗](https://www.ensembl.org/info/docs/tools/vep/index.html)")
            adf = pd.DataFrame(annotation, columns=[
                "chrom", "pos", "ref", "alt", "gene", "hgvsp", "variant_type", "assembly",
                "consequence", "impact", "transcript_id", "hgvsc", "protein_position",
                "amino_acids", "rsid", "gnomad_af", "sift", "polyphen"])
            st.dataframe(adf, use_container_width=True, hide_index=True)
            acol1, acol2 = st.columns(2)
            with acol1:
                st.download_button(
                    "⬇ Download VEP annotation (CSV)", adf.to_csv(index=False),
                    f"{base}.vep_annotation.csv", "text/csv", key="up_vep_csv")
            with acol2:
                st.download_button(
                    "⬇ Download as VCF (annotation only)",
                    to_annotated_vcf(annotation, None, assembly_r),
                    file_name=f"{base}.vep_annotation.vcf", mime="text/plain",
                    key="up_vcf_anno")

        if annotate_only_r:
            st.caption(
                "Annotate-only mode: Ensembl VEP mapping only — no evidence retrieval, "
                "AlphaMissense, or classification was run. Re-run with the toggle off for the "
                "full dual-mode interpretation.")
            if skipped:
                with st.expander(f"⏭️ Skipped / not annotated ({len(skipped)})", expanded=True):
                    st.caption("These records produced no protein-level annotation (e.g. "
                               "non-coding, no protein change, or a VEP error).")
                    skip_rows = [{"variant": s["loc"], "reason": s["reason"]} for s in skipped]
                    st.dataframe(pd.DataFrame(skip_rows), use_container_width=True,
                                 hide_index=True)
        else:
            st.caption(
                "Evidence path: **hybrid retriever** (structured + dense + graph) — "
                "richer evidence for non-hotspot variants."
                if retriever_used else
                "Evidence path: **offline structured aggregator** (exact-match) — the hybrid "
                "retriever could not be built (dense index unavailable); results may be sparser.")
            st.caption(
                "AlphaMissense scores are fetched **live from Ensembl VEP** for uploaded variants "
                "(esp. GRCh38 and uncached GRCh37) — expect a network call and slight latency.")
            if cancer_type_r is None:
                st.caption("No cancer type was provided (Auto) — tiering ran context-free; each "
                           "variant's **related cancers** below are inferred from its evidence.")
            if not use_llm_r:
                st.caption("Generative (LLM) mode was off — the 'Generative call' column shows "
                           "'not run'. VUS / abstention for no-evidence variants is honest "
                           "abstention, not an error.")

            if results:
                def _short_list(items, n=3):
                    """First ``n`` deduped items (order-preserving) + '(+N more)'."""
                    seen, out = set(), []
                    for it in items:
                        if it and it not in seen:
                            seen.add(it)
                            out.append(it)
                    head = ", ".join(out[:n])
                    if len(out) > n:
                        head += f" (+{len(out) - n} more)"
                    return head

                def _drug_names(r):
                    return [d.get("drug") for d in (r.get("bundle", {}) or {}).get("drugs", [])
                            if isinstance(d, dict) and d.get("drug")]

                rows = [{
                    "variant": f"{r['gene']} {r['hgvsp']}",
                    "cancer": r["cancer_type"] or "—",
                    "related cancers": _short_list(r.get("related_cancers") or []) or "—",
                    "evidence": r["evidence_tier"],
                    "drugs": (f"{r.get('n_drugs', 0)} · {_short_list(_drug_names(r))}"
                              if r.get("n_drugs") else "0"),
                    "trials": r.get("n_trials", 0),
                    "Deterministic (rule)": f"{r['mode_b']['oncogenicity']} / {r['mode_b']['tier']}",
                    "Generative (LLM)": ("not run"
                                         if r["mode_a"].get("rationale", "").startswith("Generative mode not run")
                                         else f"{r['mode_a']['oncogenicity']} / {r['mode_a']['tier']}"
                                              + (" ⚠" if r["mode_a"].get("abstained") else "")),
                    "⚡": "⚡" if r.get("discordant") else "",
                } for r in results]
                udf = pd.DataFrame(rows)
                st.dataframe(udf, use_container_width=True, hide_index=True)
                st.caption("⚡ = discordant — the Generative and Deterministic modes disagree on this variant.")

                # Combined single table: annotation fields joined with the
                # interpretation calls by index (annotation ↔ results).
                combined_rows = []
                for i, r in enumerate(results):
                    ann = annotation[i] if i < len(annotation) else {}
                    combined_rows.append({
                        "chrom": ann.get("chrom"),
                        "pos": ann.get("pos"),
                        "ref": ann.get("ref"),
                        "alt": ann.get("alt"),
                        "gene": ann.get("gene") or r.get("gene"),
                        "hgvsp": ann.get("hgvsp") or r.get("hgvsp"),
                        "variant_type": ann.get("variant_type"),
                        "assembly": ann.get("assembly") or assembly_r,
                        "related_cancers": "; ".join(r.get("related_cancers") or []),
                        "evidence_tier": r.get("evidence_tier"),
                        "n_evidence": r.get("n_evidence"),
                        "n_drugs": r.get("n_drugs"),
                        "n_trials": r.get("n_trials"),
                        "Generative_onc": r["mode_a"].get("oncogenicity"),
                        "Generative_tier": r["mode_a"].get("tier"),
                        "Deterministic_onc": r["mode_b"].get("oncogenicity"),
                        "Deterministic_tier": r["mode_b"].get("tier"),
                        "discordant": bool(r.get("discordant")),
                    })
                combined_df = pd.DataFrame(combined_rows)

                # Results CSV: swap the on-screen ⚡ marker for a plain boolean column.
                up_csv_df = udf.drop(columns=["⚡"]).copy()
                up_csv_df["discordant"] = [bool(r.get("discordant")) for r in results]

                dcol1, dcol2, dcol3 = st.columns(3)
                with dcol1:
                    st.download_button("⬇ Download results CSV", up_csv_df.to_csv(index=False),
                                       f"{base}.verivar_results.csv", "text/csv",
                                       key="up_csv")
                with dcol2:
                    st.download_button(
                        "⬇ Download combined (CSV)", combined_df.to_csv(index=False),
                        f"{base}.verivar_combined.csv", "text/csv", key="up_combined_csv")
                with dcol3:
                    st.download_button(
                        "⬇ Download as VCF (annotation + VeriVar)",
                        to_annotated_vcf(annotation, results, assembly_r),
                        file_name=f"{base}.verivar.vcf", mime="text/plain",
                        key="up_vcf_full")

                st.markdown("#### Per-variant detail")
                for r in results:
                    title = (f"{r['gene']} {r['hgvsp']} — {r['mode_b']['oncogenicity']} / "
                             f"{r['mode_b']['tier']}"
                             + ("  ⚡" if r.get("discordant") else ""))
                    with st.expander(title):
                        try:
                            bundle = EvidenceBundle.model_validate(r["bundle"])
                        except Exception:  # noqa: BLE001
                            bundle = EvidenceBundle(evidences=[], drugs=[], trials=[])
                        render_evidence_and_audit(r, bundle)
            else:
                st.info("Nothing was interpretable — see skipped variants below.")

            if skipped:
                with st.expander(f"⏭️ Skipped / not interpreted ({len(skipped)})", expanded=True):
                    st.caption("These records were not interpreted (e.g. non-coding, no protein "
                               "change, or a VEP annotation error). They are not failures of the "
                               "classifier — there was nothing to classify.")
                    skip_rows = [{"variant": s["loc"], "reason": s["reason"]} for s in skipped]
                    st.dataframe(pd.DataFrame(skip_rows), use_container_width=True,
                                 hide_index=True)

    st.divider()
    st.caption("Reminder: research/education only — not for clinical use. Variants with no "
               "variant-specific evidence are reported as VUS (honest abstention).")
