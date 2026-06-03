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


def ext_links(gene: str, hgvsp: str) -> str:
    """External knowledgebase links for a variant (markdown)."""
    alt = hgvsp[2:] if hgvsp.startswith("p.") else hgvsp
    return " · ".join([
        f"[OncoKB](https://www.oncokb.org/gene/{gene}/{alt})",
        f"[ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/?term={gene}%20{alt})",
        f"[cBioPortal](https://www.cbioportal.org/results?gene_list={gene})",
        f"[COSMIC](https://cancer.sanger.ac.uk/cosmic/search?q={gene}%20{alt})",
        f"[DGIdb](https://dgidb.org/results?searchType=gene&searchTerms={gene})",
    ])


@st.cache_data
def load_results():
    if not RESULT_PATH.exists():
        return None
    return json.loads(RESULT_PATH.read_text())


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


st.set_page_config(page_title="Dual-Mode Variant Interpretation", layout="wide")
st.title("🧬 Dual-Mode Somatic Variant Interpretation")
st.caption("Mode A (LLM) vs Mode B (rule). Research/education only — not for clinical use.")

with st.expander("ℹ️ How to use this dashboard", expanded=False):
    st.markdown(
        """
**What this is.** Each somatic variant is classified two ways and compared:
- **Mode A (LLM)** — a language model reads the retrieved evidence and assigns the classification.
- **Mode B (rule)** — a deterministic rule engine assigns it; the LLM only explains.
- Each variant gets two axes: **oncogenicity** (VICC) and **clinical tier** (AMP/ASCO/CAP).
- **Discordant** (⚡) variants — where the two modes disagree — are the analytical signal.

**The three tabs**
1. **Overview** — headline concordance metrics + discordance per cancer type.
2. **Variant explorer** — a sortable, filterable table of every variant. **Click a column header to sort.**
   Use the **search box** and the **filter controls** at the top of the tab, or the **sidebar** for more filters
   (CIViC evidence / drugs / trials / discordant / abstained). Download the filtered set as CSV.
3. **Variant detail** — pick a variant to see both modes side-by-side, the evidence (with clickable
   CIViC/NCT/OncoKB/ClinVar links), and a **grounded chat**.

**Grounded chat (Variant detail).** Ask a question about the *selected* variant. It answers **only** from the
retrieved evidence and **abstains** ("I cannot answer from the available evidence") when the evidence doesn't
cover the question — that's the intended faithfulness behavior, not a bug.

**Tips**
- Filter to *Clinical trial(s)* to find variants with trials; *LLM abstained only* to see honest-abstention cases.
- Compare the same variant across cancers (e.g. **BRAF V600E** in Melanoma vs Colorectal) to see context-dependent tiering.
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

tab_overview, tab_explore, tab_detail = st.tabs(["Overview", "Variant explorer", "Variant detail"])

with tab_overview:
    o = summary["overall"]
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
    lowconf_only = st.checkbox("Low confidence only (Mode A agreement < 0.7)")

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
    st.caption("Click a column header to sort. Filters above also drive the Variant detail tab.")
    rows = [{
        "variant": f"{v['gene']} {v['hgvsp']}", "cancer": v["cancer_type"],
        "evidence": v["evidence_tier"],
        "CIViC": "✓" if v["evidence_tier"] == "civic" else "",
        "drugs": v.get("n_drugs", 0),
        "trials": v.get("n_trials", 0),
        "Mode A (LLM)": f"{v['mode_a']['oncogenicity']} / {v['mode_a']['tier']}"
                        + (" ⚠" if v["mode_a"]["abstained"] else ""),
        "conf": v["mode_a"].get("confidence"),
        "Mode B (rule)": f"{v['mode_b']['oncogenicity']} / {v['mode_b']['tier']}",
        "⚡": "⚡" if v["discordant"] else "",
    } for v in flt]
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("⬇ Download filtered CSV", df.to_csv(index=False),
                       "variants_filtered.csv", "text/csv")

with tab_detail:
    labels = [f"{v['gene']} {v['hgvsp']} — {v['cancer_type']}" for v in flt]
    if not labels:
        st.info("No variants match the current filters.")
    else:
        idx = st.selectbox("Select a variant", range(len(labels)), format_func=lambda i: labels[i])
        v = flt[idx]
        a, b = v["mode_a"], v["mode_b"]
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"### Mode A — LLM")
            st.markdown(f"**{a['oncogenicity']} / {a['tier']}**"
                        + (f" ({a['tier_level']})" if a.get("tier_level") else "")
                        + (" · ⚠️ abstained" if a["abstained"] else ""))
            st.caption(f"confidence {a.get('confidence')}")
            st.markdown(linkify(a["rationale"]))
            if a.get("citations"):
                st.markdown("**cites:** " + linkify(", ".join(a["citations"])))
        with col2:
            st.markdown(f"### Mode B — rule")
            st.markdown(f"**{b['oncogenicity']} / {b['tier']}**"
                        + (f" ({b['tier_level']})" if b.get("tier_level") else ""))
            st.write(b["rationale"])
        st.divider()
        st.caption(f"Evidence tier: {v['evidence_tier']} · {v['n_evidence']} evidence · "
                   f"{v['n_drugs']} drug(s) · {v['n_trials']} trial(s) · "
                   f"samples: {', '.join(v.get('sample_ids', []))}")
        st.markdown("🔗 **External:** " + ext_links(v["gene"], v["hgvsp"]))

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

        with st.expander(f"📚 Evidence · drugs · trials  "
                         f"({len(bundle.evidences)} evidence, {len(bundle.drugs)} drugs, {len(bundle.trials)} trials)"):
            if bundle.evidences:
                st.markdown("**Evidence**")
                for e in bundle.evidences[:25]:
                    lvl = f" · level {e.evidence_level}" if e.evidence_level else ""
                    dis = f" · {e.disease}" if e.disease else ""
                    st.markdown(f"- {linkify(e.id)}{lvl}{dis}: {e.statement[:160]}")
                if len(bundle.evidences) > 25:
                    st.caption(f"… and {len(bundle.evidences) - 25} more")
            if bundle.drugs:
                st.markdown("**Drugs:** " + ", ".join(sorted({d.drug for d in bundle.drugs})))
            if bundle.trials:
                st.markdown("**Trials:** " + ", ".join(linkify(t.nct_id) for t in bundle.trials))

        st.subheader(f"💬 Ask about **{v['gene']} {v['hgvsp']}** — {v['cancer_type']}")
        st.caption(
            f"⚠️ The chat is grounded on the **selected** variant above (not on what you type). "
            f"To ask about a different variant, change the dropdown.  ·  "
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
