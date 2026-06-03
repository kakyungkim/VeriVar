#!/usr/bin/env python3
"""INDEPENDENT, CLASS-BALANCED generalisation test of the VICC point engine on ClinVar.

Horak-70 is OncoVI's *home* set; this fetches ClinVar variants that carry a somatic
**oncogenicity classification** (a separate, recently-curated expert source) and runs
`VICCPointClassifier` at FULL strength — the same evidence the Horak evaluation uses
(cancerhotspots, UniProt domains, gnomAD, MaveDB DMS, exact-variant CIViC, AlphaMissense).

Two fairness fixes over the earlier floor version:
  1. **Class balance** — samples Oncogenic / Likely-oncogenic, Benign / Likely-benign AND
     Uncertain-significance per gene (the old script queried only "oncogenic", giving a
     105:2 oncogenic-skewed set on which every conservative VUS abstention scored as wrong).
  2. **Full evidence** — wires CIViC (exact-variant) and AlphaMissense (VEP), so the engine
     is not artificially crippled to a floor.

Reports raw 3-class accuracy AND balanced (macro-recall) accuracy + per-class recall.

Usage:  python -m scripts.run_clinvar_vicc [--per-class 25] [--offline-am]
"""
import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

import pandas as pd

from src.classify.vicc_rules import VICCPointClassifier, parse_protein_change
from src.knowledge.alphamissense import AlphaMissenseAnnotator
from src.models import Variant

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
EUT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
GENES = ["FLT3", "BRAF", "IDH1", "KRAS", "PIK3CA", "PTEN", "RB1", "EZH2", "TP53"]
# Oncogenicity-classification values to sample, grouped into the 3 collapsed classes.
CLASS_TERMS = {
    "ONC": ["Oncogenic", "Likely oncogenic"],
    "BEN": ["Benign", "Likely benign"],
    "VUS": ["Uncertain significance"],
}
_AA3 = {"Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q",
        "Glu": "E", "Gly": "G", "His": "H", "Ile": "I", "Leu": "L", "Lys": "K",
        "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W",
        "Tyr": "Y", "Val": "V", "Ter": "*"}
_BEN_SIG = {"unaltered function", "benign", "likely benign", "negative"}
_RANK = {"A": 3, "B": 2, "C": 1, "D": 0}
_REGION = ("dna", "bind", "pocket", "kinase", "catalyt", "phosphatase", "set", "tensin")


def _get(url):
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as f:
                return json.load(f)
        except Exception:
            time.sleep(1)
    return {}


def collapse(c):
    c = (c or "").lower()
    if "oncogenic" in c and "non-" not in c:
        return "ONC"
    if "benign" in c:
        return "BEN"
    return "VUS"   # uncertain significance


def parse_title_aa(title):
    """'NM_..(BRAF):c.1397G>C (p.Gly466Ala)' -> 'p.G466A' (1-letter) or None."""
    import re
    m = re.search(r"\(p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2}|=)\)", title or "")
    if not m:
        return None
    r, a = _AA3.get(m.group(1)), _AA3.get(m.group(3))
    if not r or not a:
        return None
    return f"p.{r}{m.group(2)}{a}"


def _grch37_loc(vs):
    """Return (chr, pos, ref, alt) on GRCh37 from a ClinVar variation_set, or None."""
    for loc in (vs.get("variation_loc") or []):
        if loc.get("assembly_name") == "GRCh37" and loc.get("ref") and loc.get("alt"):
            try:
                return (str(loc["chr"]), int(loc["start"]), loc["ref"], loc["alt"])
            except (TypeError, ValueError, KeyError):
                pass
    return None


def fetch_gene(gene, per_class):
    """Class-balanced fetch: up to `per_class` usable variants per collapsed class."""
    kept = {"ONC": [], "BEN": [], "VUS": []}
    for cls, terms in CLASS_TERMS.items():
        for term_val in terms:
            if len(kept[cls]) >= per_class:
                break
            q = urllib.parse.quote(f'{gene}[gene] AND "{term_val}"[Oncogenicity Classification]')
            ids = _get(f"{EUT}/esearch.fcgi?db=clinvar&term={q}&retmax={per_class * 4}&retmode=json") \
                .get("esearchresult", {}).get("idlist", [])
            for i in range(0, len(ids), 50):
                if len(kept[cls]) >= per_class:
                    break
                chunk = ",".join(ids[i:i + 50])
                res = _get(f"{EUT}/esummary.fcgi?db=clinvar&id={chunk}&retmode=json").get("result", {})
                for uid, r in res.items():
                    if uid == "uids" or len(kept[cls]) >= per_class:
                        continue
                    # The gold label is the query's Oncogenicity-Classification term — the
                    # field we searched on. esummary's `oncogenicity_classification.description`
                    # is only populated for oncogenic records, so we trust the search index.
                    onc = term_val
                    aa = parse_title_aa(r.get("title", ""))
                    if not aa:
                        continue
                    vs = (r.get("variation_set") or [{}])[0]
                    af = None
                    for fr in (vs.get("allele_freq_set") or []):
                        try:
                            af = max(af or 0.0, float(fr.get("value")))
                        except (TypeError, ValueError):
                            pass
                    kept[cls].append({"gene": gene, "aa": aa, "gold": onc, "gnomad_af": af,
                                      "loc37": _grch37_loc(vs)})
                time.sleep(0.34)
    return kept["ONC"] + kept["BEN"] + kept["VUS"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=25)
    ap.add_argument("--offline-am", action="store_true",
                    help="do not call Ensembl VEP for AlphaMissense (use cache only)")
    args = ap.parse_args()

    fdir = os.path.join(ROOT, "data/knowledge/functional")
    dms = json.load(open(os.path.join(fdir, "dms_lof.json"))) if os.path.exists(os.path.join(fdir, "dms_lof.json")) else {}
    dms_neu = json.load(open(os.path.join(fdir, "dms_neutral.json"))) if os.path.exists(os.path.join(fdir, "dms_neutral.json")) else {}
    doms = json.load(open(os.path.join(ROOT, "data/knowledge/domains/uniprot_domains.json")))
    civ = pd.read_csv(os.path.join(BENCH, "horak_civic.tsv"), sep="\t")
    civ_by_gene = defaultdict(list)
    for _, r in civ.iterrows():
        civ_by_gene[str(r["molecular_profile"]).split()[0]].append(r)
    am_ann = AlphaMissenseAnnotator(offline=args.offline_am)

    def domain_at(gene, pos):
        for s, e, t, desc in doms.get(gene, []):
            if s <= pos <= e and (t in ("Domain", "Active site", "Binding site")
                                  or (t == "Region" and any(k in (desc or "").lower() for k in _REGION))):
                return desc or t
        return None

    def civic_signal(gene, ref, pos, alt):
        """Exact-variant CIViC matching (same faithful rule as the Horak eval)."""
        onco = ben = 0
        best = None
        exact = f"{gene} {ref}{pos}{alt}"
        for r in civ_by_gene.get(gene, []):
            mp = str(r["molecular_profile"])
            if not (mp.startswith(exact) and (len(mp) == len(exact) or not mp[len(exact)].isalnum())):
                continue
            s = str(r["significance"]).lower()
            d = str(r["evidence_direction"]).lower()
            if s in _BEN_SIG:
                ben += 1
            elif d == "supports":
                onco += 1
                lv = str(r["evidence_level"])
                if best is None or _RANK.get(lv, -1) > _RANK.get(best, -1):
                    best = lv
        return onco, ben, best

    def am_for(loc37):
        if not loc37:
            return None
        chrom, pos, ref, alt = loc37
        if len(ref) != 1 or len(alt) != 1:   # missense SNV only
            return None
        v = Variant(chrom=chrom, pos=pos, ref=ref, alt=alt)
        rec = am_ann._lookup(v)
        return rec.get("am_pathogenicity") if rec else None

    rows = []
    for g in GENES:
        rows += fetch_gene(g, args.per_class)

    clf = VICCPointClassifier()
    gold, pred, detail = [], [], []
    for r in rows:
        pp = parse_protein_change(r["aa"])
        vkey = f"{pp[0]}{pp[1]}{pp[2]}" if pp else ""
        onco = ben = 0
        best = None
        if pp:
            onco, ben, best = civic_signal(r["gene"], pp[0], pp[1], pp[2])
        res = clf.score(r["gene"], r["aa"],
                        am_pathogenicity=am_for(r.get("loc37")),
                        civic_onco=onco, civic_benign=ben, civic_best_level=best,
                        in_domain=domain_at(r["gene"], pp[1]) if pp else None,
                        gnomad_af=r.get("gnomad_af"),
                        functional_lof=bool(dms.get(r["gene"], {}).get(vkey)),
                        functional_neutral=bool(dms_neu.get(r["gene"], {}).get(vkey)))
        gold.append(r["gold"])
        pred.append(res.oncogenicity.value)
        detail.append({"gene": r["gene"], "aa": r["aa"], "gold": collapse(r["gold"]),
                       "pred": collapse(res.oncogenicity.value), "points": res.points,
                       "codes": [c.code for c in res.criteria]})

    n = len(gold)
    gc = [collapse(g) for g in gold]
    pc = [collapse(p) for p in pred]
    acc3 = round(sum(p == g for p, g in zip(pc, gc)) / n, 3) if n else 0
    # Balanced accuracy = mean per-class recall (robust to residual class imbalance).
    recalls = {}
    for cls in ("ONC", "BEN", "VUS"):
        tot = sum(1 for g in gc if g == cls)
        hit = sum(1 for g, p in zip(gc, pc) if g == cls and p == cls)
        recalls[cls] = round(hit / tot, 3) if tot else None
    rec_vals = [v for v in recalls.values() if v is not None]
    bal_acc = round(sum(rec_vals) / len(rec_vals), 3) if rec_vals else 0
    # Binary oncogenic-detection — the clinically meaningful task. ClinVar "Benign" is
    # structurally hard for ANY VICC engine (Benign requires populational frequency or a
    # functional-neutral line; a rare benign missense correctly stays VUS), so a 3-class
    # benign recall understates real performance. We therefore also report ONC-vs-rest.
    tp = sum(1 for g, p in zip(gc, pc) if g == "ONC" and p == "ONC")
    fn = sum(1 for g, p in zip(gc, pc) if g == "ONC" and p != "ONC")
    fp = sum(1 for g, p in zip(gc, pc) if g != "ONC" and p == "ONC")
    tn = sum(1 for g, p in zip(gc, pc) if g != "ONC" and p != "ONC")
    sens = round(tp / (tp + fn), 3) if tp + fn else None
    spec = round(tn / (tn + fp), 3) if tn + fp else None
    report = {"n": n, "per_class": args.per_class, "accuracy_3class": acc3,
              "balanced_accuracy_3class": bal_acc, "per_class_recall": recalls,
              "onc_detection": {"sensitivity": sens, "specificity": spec, "tp": tp,
                                "fp": fp, "tn": tn, "fn": fn},
              "genes": GENES, "alphamissense": "cache-only" if args.offline_am else "VEP-live",
              "note": "independent, class-balanced ClinVar oncogenicity set; engine at full "
                      "strength (exact-CIViC + AlphaMissense + hotspots + domains + gnomAD + DMS). "
                      "3-class benign recall is structurally limited (VICC Benign needs frequency); "
                      "the ONC-vs-rest detection metric is the clinically meaningful one.",
              "gold_dist": dict(Counter(gc)), "pred_dist": dict(Counter(pc))}
    # FN diagnostics: among oncogenic-gold variants we MISSED, what evidence fired?
    fn = [d for d in detail if d["gold"] == "ONC" and d["pred"] != "ONC"]
    tp_rows = [d for d in detail if d["gold"] == "ONC" and d["pred"] == "ONC"]
    onco_codes = {"OVS1", "OS1", "OS2", "OS3", "OM1", "OM3", "OM4", "OP1", "OP3", "OP4"}
    report["fn_diagnostics"] = {
        "n_fn": len(fn),
        "fn_by_gene": dict(Counter(d["gene"] for d in fn)),
        "fn_points_hist": dict(Counter(d["points"] for d in fn)),
        "fn_with_no_onco_code": sum(1 for d in fn if not (set(d["codes"]) & onco_codes)),
        "fn_with_only_weak": sum(1 for d in fn if set(d["codes"]) & onco_codes
                                 and not (set(d["codes"]) & {"OVS1", "OS2", "OS3"})),
        "tp_strong_evidence_share": round(
            sum(1 for d in tp_rows if set(d["codes"]) & {"OVS1", "OS2", "OS3"}) / len(tp_rows), 3)
        if tp_rows else None,
        "fn_examples": fn[:12]}
    json.dump(detail, open(os.path.join(BENCH, "clinvar_vicc_rows.json"), "w"), indent=2)
    json.dump(report, open(os.path.join(BENCH, "clinvar_vicc.json"), "w"), indent=2)
    print(f"[+] ClinVar independent, class-balanced (n={n}): acc3={acc3}  balanced_acc={bal_acc}")
    print(f"    ONC-detection: sensitivity={sens}  specificity={spec}  (tp={tp} fp={fp} tn={tn} fn={fn})")
    print(f"    per-class recall: {recalls}")
    print(f"    gold {report['gold_dist']}  pred {report['pred_dist']}")


if __name__ == "__main__":
    main()
