#!/usr/bin/env python3
"""ClinVar somatic-oncogenicity holdout (rebuilt) for the VICC point-based rule arm.

Replaces the label source of ``scripts/run_clinvar_vicc.py`` (whose Benign/VUS gold came
from an E-utilities field qualifier that silently matched germline classifications; see
``scripts/fetch_clinvar_oncogenicity.py``). The old outputs ``clinvar_vicc*.json`` are left
untouched for the audit trail.

Construction (all offline, from the committed snapshot
``data/benchmark/clinvar_onc/clinvar_oncogenicity_missense_grch38.tsv``):
  1. drop aggregate "Conflicting classifications of oncogenicity" rows;
  2. exclude the Horak-70 variants (by gene + protein change);
  3. de-duplicate on (gene, protein change) — codon synonyms of one amino-acid change
     collapse; keys whose rows disagree on the collapsed class are DROPPED and counted;
  4. binary task ONC (Oncogenic + Likely oncogenic) vs VUS; the handful of Benign /
     Likely benign keys are reported but excluded (benign is essentially absent from
     ClinVar oncogenicity, so three-class accuracy and benign recall cannot be measured).

Rule arm: ``VICCPointClassifier`` with the same independent evidence as the Horak
evaluation (cancerhotspots, UniProt domains, MaveDB DMS, exact-variant CIViC,
AlphaMissense, gnomAD). **OS1 (known_oncogenic, sourced from ClinVar) is OFF** — here it
would be the label itself. No other ClinVar-derived field (germline classification,
ClinVar allele frequencies) is read. Operating point: points >= 6 (Likely oncogenic or
Oncogenic) = ONC call; AUROC uses the raw points.

Scopes: ``panel9`` = the nine Horak genes where the engine has its full evidence stack
(UniProt domains + CIViC + hotspots; DMS for TP53/PTEN); ``all`` = every gene (domains
absent outside the nine; CIViC for the 30 snapshot genes; hotspots for 233 genes;
AlphaMissense/gnomAD everywhere).

Usage:  python -m scripts.run_clinvar_onc_holdout
Output: data/benchmark/clinvar_onc_holdout.json (+ clinvar_onc_holdout_rows.json)
"""
import csv
import datetime as _dt
import hashlib
import json
import os
import subprocess
from collections import Counter, defaultdict
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np

from src.classify.vicc_rules import (CONFIGS, PRIMARY_CONFIG, CivicSignal, VICCPointClassifier,
                                     civic_signal_from_rows, domain_feature_at,
                                     parse_protein_change)
from src.classify.vicc_inputs import (V2InputProvider, load_civic_rows, load_dms_lof,
                                      v2_resource_paths)
from src.eval.stats import boundary_ci, bootstrap_ci

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCH = os.path.join(ROOT, "data", "benchmark")
SNAP_DIR = os.path.join(BENCH, "clinvar_onc")
SNAP_TSV = os.path.join(SNAP_DIR, "clinvar_oncogenicity_missense_grch38.tsv")
OUT = os.path.join(BENCH, "clinvar_onc_holdout.json")
OUT_ROWS = os.path.join(BENCH, "clinvar_onc_holdout_rows.json")
HORAK_TSV = os.path.join(BENCH, "horak_benchmark.tsv")
OLD_ROWS = os.path.join(BENCH, "clinvar_vicc_rows.json")
CIVIC_TSVS = [os.path.join(BENCH, "horak_civic.tsv"),
              os.path.join(ROOT, "data", "knowledge", "civic", "civic_evidence_panel.tsv")]
DOMAINS = os.path.join(ROOT, "data", "knowledge", "domains", "uniprot_domains.json")
HOTSPOTS = os.path.join(ROOT, "data", "knowledge", "hotspots", "cancerhotspots.json")
DMS_LOF = os.path.join(ROOT, "data", "knowledge", "functional", "dms_lof.json")
DMS_NEU = os.path.join(ROOT, "data", "knowledge", "functional", "dms_neutral.json")
PANEL9 = ["BRAF", "EZH2", "FLT3", "IDH1", "KRAS", "PIK3CA", "PTEN", "RB1", "TP53"]
THRESHOLD = 6
RIGS = "Center for Genomic Medicine, Rigshospitalet, Copenhagen University Hospital"


# --------------------------------------------------------------------------- stats
def auroc(y: List[int], s: List[float]) -> Optional[float]:
    """Mann-Whitney AUROC with mid-ranks for ties; None if a class is empty."""
    npos = sum(y)
    nneg = len(y) - npos
    if npos == 0 or nneg == 0:
        return None
    order = np.argsort(np.asarray(s, dtype=float), kind="mergesort")
    ss = np.asarray(s, dtype=float)[order]
    ranks = np.empty(len(s))
    i = 0
    while i < len(ss):
        j = i
        while j < len(ss) and ss[j] == ss[i]:
            j += 1
        ranks[order[i:j]] = (i + j - 1) / 2.0 + 1
        i = j
    sum_pos = float(ranks[np.asarray(y) == 1].sum())
    return (sum_pos - npos * (npos + 1) / 2.0) / (npos * nneg)


def auroc_ci(y: List[int], s: List[float], n_boot: int = 2000, seed: int = 0) -> dict:
    """Class-stratified percentile bootstrap CI for AUROC (fixed seed)."""
    point = auroc(y, s)
    if point is None:
        return {"point": None, "lo": None, "hi": None, "n_pos": sum(y),
                "n_neg": len(y) - sum(y)}
    rng = np.random.default_rng(seed)
    y_a, s_a = np.asarray(y), np.asarray(s, dtype=float)
    pos, neg = s_a[y_a == 1], s_a[y_a == 0]
    vals = []
    for _ in range(n_boot):
        p = rng.choice(pos, size=pos.size, replace=True)
        n = rng.choice(neg, size=neg.size, replace=True)
        vals.append(auroc([1] * p.size + [0] * n.size, list(p) + list(n)))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return {"point": round(point, 3), "lo": round(float(lo), 3), "hi": round(float(hi), 3),
            "n_pos": int(pos.size), "n_neg": int(neg.size)}


def detection_metrics(records: List[dict]) -> dict:
    """ONC-vs-VUS detection at points >= THRESHOLD, with bootstrap CIs."""
    recs = [r for r in records if r["gold"] in ("ONC", "VUS")]
    y = [1 if r["gold"] == "ONC" else 0 for r in recs]
    s = [r["points"] for r in recs]
    call = [r["points"] >= THRESHOLD for r in recs]
    tp = sum(1 for yi, c in zip(y, call) if yi and c)
    fn = sum(1 for yi, c in zip(y, call) if yi and not c)
    tn = sum(1 for yi, c in zip(y, call) if not yi and not c)
    fp = sum(1 for yi, c in zip(y, call) if not yi and c)
    sens = bootstrap_ci([float(c) for yi, c in zip(y, call) if yi])
    spec = bootstrap_ci([float(not c) for yi, c in zip(y, call) if not yi])
    ppv = round(tp / (tp + fp), 3) if tp + fp else None
    return {"n": len(recs), "n_onc": sum(y), "n_vus": len(y) - sum(y),
            "tp": tp, "fn": fn, "tn": tn, "fp": fp,
            "sensitivity": sens, "specificity_on_gold_vus": spec, "ppv": ppv,
            "ppv_exact_ci": boundary_ci(tp, tp + fp),
            # Wilson + Clopper-Pearson; the bootstrap collapses at 0 or 1 (peer review P1-3)
            "sensitivity_exact_ci": boundary_ci(tp, tp + fn),
            "specificity_on_gold_vus_exact_ci": boundary_ci(tn, tn + fp),
            "auroc_points": auroc_ci(y, s),
            "pred_dist_5class": dict(Counter(r["pred"] for r in recs))}


# --------------------------------------------------------------------------- data
def read_tsv(path: str) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def norm_key(gene: str, aa: str) -> str:
    aa = str(aa).strip()
    return f"{str(gene).strip().upper()} {aa if aa.startswith('p.') else 'p.' + aa}"


def build_holdout(rows: List[dict], exclude_keys: Iterable[str]) -> Tuple[List[dict], dict]:
    """Apply steps 1-3 of the construction; return (one record per key, funnel)."""
    excl = set(exclude_keys)
    funnel: Dict[str, int] = {"snapshot_rows": len(rows)}
    rows = [r for r in rows if r["onc_class"] != "CONFLICT"]
    funnel["dropped_aggregate_conflicting"] = funnel["snapshot_rows"] - len(rows)
    kept = [r for r in rows if norm_key(r["gene"], r["aa"]) not in excl]
    funnel["dropped_horak70_overlap_rows"] = len(rows) - len(kept)
    funnel["horak70_overlap_keys"] = len({norm_key(r["gene"], r["aa"]) for r in rows} & excl)
    groups: Dict[str, List[dict]] = defaultdict(list)
    for r in kept:
        groups[norm_key(r["gene"], r["aa"])].append(r)
    funnel["unique_gene_aa_keys"] = len(groups)
    funnel["keys_with_multiple_nucleotide_variants"] = sum(len(g) > 1 for g in groups.values())
    out, conflicts = [], []
    for key, grp in sorted(groups.items()):
        classes = {g["onc_class"] for g in grp}
        if len(classes) > 1:
            conflicts.append({"key": key, "labels": sorted(g["oncogenicity"] for g in grp)})
            continue
        # representative: the record with most oncogenicity SCVs, then lowest VariationID
        rep = sorted(grp, key=lambda g: (-int(g.get("n_onc_scvs") or 0),
                                         int(g["variation_id"])))[0]
        rec = dict(rep)
        rec["key"] = key
        rec["gold"] = rep["onc_class"]
        rec["n_nucleotide_variants"] = len(grp)
        rec["variation_ids"] = "|".join(g["variation_id"] for g in grp)
        out.append(rec)
    funnel["dropped_keys_conflicting_labels"] = len(conflicts)
    funnel["final_keys"] = len(out)
    funnel["conflicting_examples"] = conflicts[:20]
    return out, funnel


class RuleArm:
    """VICC point engine wired to the same independent evidence as the Horak eval."""

    def __init__(self, config: str = PRIMARY_CONFIG):
        self.clf = VICCPointClassifier(config=config)
        self.domains = json.load(open(DOMAINS)) if os.path.exists(DOMAINS) else {}
        cfg = self.clf.config
        # v2-family configurations read the pre-registered inputs; v1 is the published path.
        self.dms = load_dms_lof(cfg.dms_inputs)
        self.dms_neu = json.load(open(DMS_NEU)) if os.path.exists(DMS_NEU) else {}
        self.civ = defaultdict(list)
        for r in load_civic_rows(cfg.civic_inputs, base_paths=CIVIC_TSVS):
            self.civ[str(r["molecular_profile"]).split()[0]].append(r)
        self.civic_genes = sorted(self.civ)
        self.v2in = V2InputProvider(cfg)

    def domain_at(self, gene: str, pos: int) -> Optional[str]:
        return domain_feature_at(self.domains, gene, pos, self.clf.config.om1_scope)
        return None

    def civic_signal(self, gene: str, ref: str, pos: int, alt: str) -> CivicSignal:
        """Exact-variant CIViC + SOP functional-only mapping (shared with the Horak eval)."""
        return civic_signal_from_rows(self.civ.get(gene, []), gene, ref, pos, alt)

    def score(self, rec: dict, use_dms: bool = True):
        gene, aa = rec["gene"], rec["aa"]
        pp = parse_protein_change(aa)
        civ_sig = self.civic_signal(gene, pp[0], pp[1], pp[2]) if pp else None
        vkey = f"{pp[0]}{pp[1]}{pp[2]}" if pp else ""
        am = rec.get("am_pathogenicity")
        gaf = rec.get("gnomad_af")
        return self.clf.score(
            gene, aa,
            am_pathogenicity=float(am) if am not in (None, "") else None,
            civic=civ_sig,
            in_domain=self.domain_at(gene, pp[1]) if pp else None,
            gnomad_af=float(gaf) if gaf not in (None, "") else None,
            functional_lof=use_dms and bool(self.dms.get(gene, {}).get(vkey)),
            functional_neutral=use_dms and bool(self.dms_neu.get(gene, {}).get(vkey)),
            known_oncogenic=False,   # OS1 OFF: ClinVar-sourced OS1 == label leakage
            **self.v2in.kwargs(gene, aa, rec.get("chrom"), rec.get("pos"), rec.get("ref"),
                              rec.get("alt")))


def score_records(records: List[dict], scorer: Callable[[dict], object]) -> List[dict]:
    out = []
    for rec in records:
        res = scorer(rec)
        out.append({"key": rec["key"], "gene": rec["gene"], "aa": rec["aa"],
                    "gold": rec["gold"], "gold_label": rec["oncogenicity"],
                    "pred": res.oncogenicity.value, "points": res.points,
                    "codes": [c.code for c in res.criteria],
                    "submitters": rec.get("onc_submitters", ""),
                    "onc_last_evaluated": rec.get("onc_last_evaluated", ""),
                    "variation_ids": rec.get("variation_ids", rec.get("variation_id", ""))})
    return out


def per_gene(scored: List[dict], min_n: int = 5) -> dict:
    by = defaultdict(list)
    for r in scored:
        if r["gold"] in ("ONC", "VUS"):
            by[r["gene"]].append(r)
    out = {}
    for g, lst in sorted(by.items(), key=lambda kv: -len(kv[1])):
        if len(lst) < min_n:
            continue
        n_onc = sum(r["gold"] == "ONC" for r in lst)
        n_vus = len(lst) - n_onc
        tp = sum(r["gold"] == "ONC" and r["points"] >= THRESHOLD for r in lst)
        tn = sum(r["gold"] == "VUS" and r["points"] < THRESHOLD for r in lst)
        au = auroc([int(r["gold"] == "ONC") for r in lst], [r["points"] for r in lst])
        out[g] = {"n": len(lst), "n_onc": n_onc, "n_vus": n_vus,
                  "sensitivity": round(tp / n_onc, 3) if n_onc else None,
                  "specificity": round(tn / n_vus, 3) if n_vus else None,
                  # small per-gene n: proportions often sit at 0 or 1 (peer review P1-3)
                  "sensitivity_exact_ci": boundary_ci(tp, n_onc) if n_onc else None,
                  "specificity_exact_ci": boundary_ci(tn, n_vus) if n_vus else None,
                  "auroc": round(au, 3) if au is not None else None}
    return out


def _sha256(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head() -> Optional[str]:
    try:
        return subprocess.check_output(["git", "-C", ROOT, "rev-parse", "HEAD"],
                                       text=True).strip()
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="ClinVar oncogenicity holdout, VICC rule arm")
    ap.add_argument("--config", default=PRIMARY_CONFIG, choices=sorted(CONFIGS))
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--out-rows", default=OUT_ROWS)
    args = ap.parse_args()
    rows = read_tsv(SNAP_TSV)
    horak = read_tsv(HORAK_TSV)
    horak_keys = {norm_key(r["gene"], r["aa"]) for r in horak}
    records, funnel = build_holdout(rows, horak_keys)
    ben = [r for r in records if r["gold"] == "BEN"]
    arm = RuleArm(config=args.config)
    scored = score_records(records, arm.score)
    scored_nodms = {r["key"]: r for r in score_records(records,
                                                       lambda x: arm.score(x, use_dms=False))}

    old_keys = set()
    if os.path.exists(OLD_ROWS):
        old_keys = {norm_key(r["gene"], r["aa"]) for r in json.load(open(OLD_ROWS))}

    def subset(pred):
        return [r for r in scored if pred(r)]

    scopes = {
        "panel9": subset(lambda r: r["gene"] in PANEL9),
        "civic_or_panel_genes": subset(lambda r: r["gene"] in set(PANEL9) | set(arm.civic_genes)),
        "all": scored,
    }
    results = {name: {"class_dist": dict(Counter(r["gold"] for r in lst)),
                      "detection": detection_metrics(lst),
                      "per_gene": per_gene(lst)}
               for name, lst in scopes.items()}

    # TP53 / PTEN separately, with the DMS-derived OS2 line on vs off (OS2 held-out view).
    os2 = {}
    for g in ("TP53", "PTEN"):
        lst = subset(lambda r, g=g: r["gene"] == g)
        off = [scored_nodms[r["key"]] for r in lst]
        os2[g] = {"dms_on": detection_metrics(lst), "dms_off": detection_metrics(off),
                  "n_os2_dms_fired": sum("OS2" in r["codes"] and "OS2" not in
                                         scored_nodms[r["key"]]["codes"] for r in lst)}

    # Robustness: single-submitter concentration and overlap with the retired holdout.
    robustness = {
        "rigshospitalet_only": detection_metrics(subset(
            lambda r: r["submitters"] and set(r["submitters"].split("|")) == {RIGS})),
        "other_submitters": detection_metrics(subset(
            lambda r: not (r["submitters"] and set(r["submitters"].split("|")) == {RIGS}))),
        "all_excluding_old_holdout_keys": detection_metrics(subset(
            lambda r: r["key"] not in old_keys)),
        "panel9_excluding_old_holdout_keys": detection_metrics(subset(
            lambda r: r["gene"] in PANEL9 and r["key"] not in old_keys)),
    }
    submitter_share = Counter()
    for r in scored:
        for s in filter(None, r["submitters"].split("|")):
            submitter_share[s] += 1

    snap_prov = json.load(open(os.path.join(SNAP_DIR, "provenance.json")))
    report = {
        "title": "ClinVar somatic-oncogenicity holdout (rebuilt 2026-09-24), VICC rule arm",
        "task": "ONC (Oncogenic+Likely oncogenic) vs VUS detection; operating point "
                f"points >= {THRESHOLD}; AUROC over raw VICC points",
        "why_rebuilt": "clinvar_vicc.json (n=458) took gold = E-utilities search term; the "
                       "[Oncogenicity Classification] qualifier does not restrict Benign / "
                       "Likely benign / Uncertain significance to oncogenicity records, so "
                       "those gold labels were mostly germline classifications.",
        "rule_arm_config": {"engine": f"src.classify.vicc_rules.VICCPointClassifier(config={args.config!r})",
                            "config": args.config,
                            "config_description": CONFIGS[args.config].description,
                            "OS1_known_oncogenic": False,
                            "clinvar_derived_inputs": "none (label source only)",
                            "evidence": ["cancerhotspots (OS3/OM3/OP3)",
                                         "UniProt domains (OM1; 9 genes only)",
                                         "MaveDB DMS (OS2/SBS2; TP53, PTEN)",
                                         "CIViC exact-variant, functional evidence only "
                                         "(OS2/OS2_Moderate vs SBS2/SBS2_Moderate; snapshot genes)",
                                         "AlphaMissense via VEP GRCh38 (OP1/SBP1)",
                                         "gnomAD AF via VEP GRCh38 (SBVS1/SBS1/OP4)"],
                            "civic_genes": arm.civic_genes, "panel9": PANEL9},
        "funnel": funnel,
        "benign_keys_excluded_from_binary_task": [
            {"key": r["key"], "label": r["oncogenicity"]} for r in ben],
        "scopes": results,
        "tp53_pten_os2": os2,
        "robustness": robustness,
        "submitter_share_all_keys": dict(submitter_share.most_common()),
        "n_keys_single_submitter_rigshospitalet": sum(
            1 for r in scored if r["submitters"] and set(r["submitters"].split("|")) == {RIGS}),
        "onc_last_evaluated_year": dict(Counter((r["onc_last_evaluated"] or "-")[:4]
                                                for r in scored)),
        "overlap_with_retired_holdout_keys": {
            "all": sum(r["key"] in old_keys for r in scored),
            "panel9": sum(r["key"] in old_keys for r in scored if r["gene"] in PANEL9)},
        "retired_holdout_for_comparison": {
            "file": "data/benchmark/clinvar_vicc.json", "n_rows": 458, "unique_keys": 352,
            "sensitivity": 0.537, "specificity": 0.967, "auroc": 0.902,
            "status": "retired: BEN/VUS gold labels not oncogenicity classifications"},
        "provenance": {
            "generated_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "script": "scripts/run_clinvar_onc_holdout.py", "git_head": _git_head(),
            "snapshot_tsv": os.path.relpath(SNAP_TSV, ROOT),
            "snapshot_tsv_sha256": _sha256(SNAP_TSV),
            "clinvar_source_files": snap_prov.get("source_files"),
            "snapshot_fetched_utc": snap_prov.get("fetched_utc"),
            "vep": snap_prov.get("vep"),
            "resource_sha256": {os.path.relpath(p, ROOT): _sha256(p) for p in
                                [HOTSPOTS, DOMAINS, DMS_LOF, DMS_NEU, HORAK_TSV] + CIVIC_TSVS
                                + v2_resource_paths(CONFIGS[args.config])},
            "bootstrap": "percentile; proportions via src.eval.stats.bootstrap_ci "
                         "(5000, seed 0); AUROC class-stratified (2000, seed 0)",
        },
    }
    json.dump(report, open(args.out, "w"), indent=2)
    json.dump(scored, open(args.out_rows, "w"), indent=1)
    for name in ("panel9", "all"):
        d = results[name]["detection"]
        print(f"[+] {name}: n={d['n']} (ONC {d['n_onc']} / VUS {d['n_vus']})  "
              f"sens {d['sensitivity']['point']} [{d['sensitivity']['lo']}, "
              f"{d['sensitivity']['hi']}]  spec {d['specificity_on_gold_vus']['point']} "
              f"[{d['specificity_on_gold_vus']['lo']}, {d['specificity_on_gold_vus']['hi']}]  "
              f"AUROC {d['auroc_points']['point']} [{d['auroc_points']['lo']}, "
              f"{d['auroc_points']['hi']}]")
    print(f"    funnel: { {k: v for k, v in funnel.items() if k != 'conflicting_examples'} }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
