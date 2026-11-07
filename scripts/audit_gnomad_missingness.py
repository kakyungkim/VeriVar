"""Audit how missing gnomAD records are handled on the OP4 path (Horak-70 and ClinVar).

Purpose
-------
Peer review 2026-09-24 (P1-4 / "OP4") found that the Methods sentence "OP4 is
awarded only when gnomAD data are observed ... no population evidence is
imputed" does not describe the code. This script counts, for both benchmark
paths, how often the gnomAD allele frequency passed to the VICC engine is an
observed value versus a missing record coded as 0.0, and how often OP4 then
fires, so the Methods can be worded exactly. It reads committed snapshots
only; it does not re-run the engine and does not change any input.

How the code encodes gnomAD (read from the source, 2026-09-27)
--------------------------------------------------------------
* ClinVar path, ``scripts/fetch_clinvar_oncogenicity.py::parse_vep_record``:
  ``af`` starts at 0.0 and is raised to the max of the ``gnomade`` / ``gnomadg``
  overall frequency for the ALT allele over VEP ``colocated_variants``. So a
  VEP record with no colocated variant, or with colocated variants that carry
  no gnomAD frequency for this allele, is stored as ``gnomad_af = 0.0``. Only a
  variant for which VEP returned no record at all is stored as ``None``
  (``vep_annotate`` miss placeholder).
* Horak path, ``data/benchmark/horak_gnomad.json`` (key -> AF, GRCh37). The
  file carries the same convention per the comment in
  ``fetch_clinvar_oncogenicity.py``, but no script in the repository writes it
  (it entered in commit ec22422 with its consumers only), so the convention
  cannot be verified from code; this audit checks it against an independent
  VEP query instead (below).
* Engine, ``src/classify/vicc_rules.py`` (``op4="data_only"``, sop_strict):
  OP4 fires when ``gnomad_af is not None and gnomad_af < 1e-4``; ``None`` gives
  no OP4. So a stored 0.0 is treated as "absent from gnomAD" and earns OP4.
  Coverage at the site is never checked.

Independent cross-check
-----------------------
``data/knowledge/vep_v2/vep_v2_annotations.json`` (``scripts/fetch_vicc_v2_inputs.py``,
GRCh38 VEP with ``af_gnomade=1&af_gnomadg=1``) stores every gnomAD exome/genome
frequency key found for the ALT allele (``gnomad_freqs``). For each variant
coded 0.0 on the v1 path, the audit reports whether that second query found no
gnomAD key at all, gnomAD keys that are all 0.0 (an explicit zero), or a
non-zero frequency (a real discrepancy). Both snapshots store parsed values
only, so "no colocated record" and "colocated record without a gnomAD
frequency" cannot be separated.

Prerequisites
-------------
``data/benchmark/{horak_benchmark.tsv,horak_gnomad.json,horak_vicc.json,
clinvar_onc_holdout_rows.json}``, ``data/benchmark/clinvar_onc/
clinvar_oncogenicity_missense_grch38.tsv`` and
``data/knowledge/vep_v2/vep_v2_annotations.json``. Offline.

Run
---
::

    python -m scripts.audit_gnomad_missingness [--out PATH]

Output
------
``data/outputs/gnomad_missingness_audit.json``: per path, counts of AF
states (``missing_none`` / ``coded_zero`` / ``observed_below_op4`` /
``observed_at_or_above_op4``), OP4 firing by AF state (sop_strict output rows),
the v2 cross-check for coded-zero variants, and for Horak the cross-tab with
the curators' published OP4 (``sop_codes``).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from typing import Dict, Iterable, List, Mapping, Optional

from src.classify.vicc_inputs import v2_key
from src.classify.vicc_rules import OP4_MAX_AF

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, "data", "benchmark")
HORAK_TSV = os.path.join(BENCH, "horak_benchmark.tsv")
HORAK_GNOMAD = os.path.join(BENCH, "horak_gnomad.json")
HORAK_VICC = os.path.join(BENCH, "horak_vicc.json")
CLINVAR_TSV = os.path.join(BENCH, "clinvar_onc", "clinvar_oncogenicity_missense_grch38.tsv")
CLINVAR_ROWS = os.path.join(BENCH, "clinvar_onc_holdout_rows.json")
VEP_V2 = os.path.join(ROOT, "data", "knowledge", "vep_v2", "vep_v2_annotations.json")
OUT = os.path.join(ROOT, "data", "outputs", "gnomad_missingness_audit.json")

AF_STATES = ("missing_none", "coded_zero", "observed_below_op4", "observed_at_or_above_op4")


def af_state(af: Optional[float], threshold: float = OP4_MAX_AF) -> str:
    """Bin the AF handed to the engine: None, exactly 0.0, (0, threshold), >= threshold."""
    if af is None:
        return "missing_none"
    if af == 0.0:
        return "coded_zero"
    return "observed_below_op4" if af < threshold else "observed_at_or_above_op4"


def v2_status(rec: Optional[Mapping]) -> str:
    """Result of the independent GRCh38 VEP query for one variant.

    ``v2_no_gnomad_key``: VEP returned the variant but no gnomAD frequency key for
    the ALT allele; ``v2_gnomad_all_zero``: gnomAD keys present, every value 0.0
    (an explicit zero, which the v1 parser also stores as 0.0);
    ``v2_gnomad_nonzero``: at least one gnomAD frequency > 0 (a real discrepancy
    with a v1 value of 0.0)."""
    if not rec or not rec.get("vep_returned"):
        return "v2_not_returned"
    freqs = rec.get("gnomad_freqs") or {}
    if not freqs:
        return "v2_no_gnomad_key"
    return "v2_gnomad_nonzero" if any(float(v) > 0 for v in freqs.values()) else \
        "v2_gnomad_all_zero"


def summarise(records: Iterable[Mapping]) -> dict:
    """Count AF states, OP4 firing per state and the v2 cross-check.

    Each record needs ``af`` (float or None), ``op4`` (bool, engine output) and
    ``v2`` (the v2 annotation dict or None); ``curator_op4`` (bool) is optional.
    """
    recs = list(records)
    states = Counter(af_state(r["af"]) for r in recs)
    op4_by_state = Counter(af_state(r["af"]) for r in recs if r["op4"])
    zero = [r for r in recs if af_state(r["af"]) == "coded_zero"]
    out = {
        "n": len(recs),
        "af_state_counts": {s: states.get(s, 0) for s in AF_STATES},
        "op4_fired": sum(1 for r in recs if r["op4"]),
        "op4_fired_by_af_state": {s: op4_by_state.get(s, 0) for s in AF_STATES},
        "coded_zero_v2_crosscheck": dict(Counter(v2_status(r["v2"]) for r in zero)),
        "coded_zero_v2_nonzero_discrepancies": [
            {"variant": r.get("variant"), "v2_gnomad_freqs": r["v2"]["gnomad_freqs"]}
            for r in zero if v2_status(r["v2"]) == "v2_gnomad_nonzero"],
        "coded_zero_v2_all_zero_variants": [
            r.get("variant") for r in zero if v2_status(r["v2"]) == "v2_gnomad_all_zero"],
    }
    if recs and all("curator_op4" in r for r in recs):
        tab = Counter((bool(r["op4"]), bool(r["curator_op4"])) for r in recs)
        out["op4_vs_curator"] = {
            "both": tab.get((True, True), 0), "engine_only": tab.get((True, False), 0),
            "curator_only": tab.get((False, True), 0), "neither": tab.get((False, False), 0),
            "curator_op4_total": sum(1 for r in recs if r["curator_op4"]),
            "engine_only_by_af_state": dict(Counter(
                af_state(r["af"]) for r in recs if r["op4"] and not r["curator_op4"]))}
    return out


def _read_tsv(path: str) -> List[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _float_or_none(x) -> Optional[float]:
    return None if x in (None, "") else float(x)


def horak_records(bench: List[dict], gnomad: Mapping[str, float], vicc_rows: List[dict],
                  vep_v2: Mapping[str, dict]) -> List[dict]:
    """Join the Horak TSV, the v1 AF file and the engine rows (same order as the TSV)."""
    if len(bench) != len(vicc_rows):
        raise ValueError("horak_vicc rows and horak_benchmark.tsv differ in length")
    out = []
    for b, v in zip(bench, vicc_rows):
        name = f"{b['gene']} {b['aa']}"
        if v["variant"] != name:
            raise ValueError(f"row order mismatch: {v['variant']} vs {name}")
        gkey = f"{b['b37_chr']} {b['b37_pos']} . {b['b37_ref']} {b['b37_alt']} . . ."
        curator = {c.strip() for c in (b.get("sop_codes") or "").split(",")}
        out.append({"variant": name, "af": gnomad.get(gkey), "op4": "OP4" in v["codes"],
                    "curator_op4": "OP4" in curator,
                    "v2": vep_v2.get(v2_key(b["b38_chr"], b["b38_pos"], b["b38_ref"],
                                            b["b38_alt"]))})
    return out


def clinvar_representative(snapshot_rows: List[dict], variation_ids: str) -> dict:
    """Pick the record the holdout scored for a key (same rule as
    ``run_clinvar_onc_holdout``: most oncogenicity SCVs, then lowest VariationID)."""
    ids = set(variation_ids.split("|"))
    grp = [r for r in snapshot_rows if r["variation_id"] in ids]
    if not grp:
        raise ValueError(f"no snapshot row for {variation_ids}")
    return sorted(grp, key=lambda g: (-int(g.get("n_onc_scvs") or 0),
                                      int(g["variation_id"])))[0]


def clinvar_records(snapshot: List[dict], holdout_rows: List[dict],
                    vep_v2: Mapping[str, dict]) -> List[dict]:
    """One record per scored holdout key, with the AF the engine received."""
    out = []
    for h in holdout_rows:
        rep = clinvar_representative(snapshot, h["variation_ids"])
        out.append({"variant": h["key"], "af": _float_or_none(rep.get("gnomad_af")),
                    "op4": "OP4" in h["codes"],
                    "v2": vep_v2.get(v2_key(rep["chrom"], rep["pos"], rep["ref"], rep["alt"]))})
    return out


def _sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    vep_v2 = json.load(open(VEP_V2))
    horak_vicc = json.load(open(HORAK_VICC))
    hr = horak_records(_read_tsv(HORAK_TSV), json.load(open(HORAK_GNOMAD)),
                       horak_vicc["rows"], vep_v2)
    snapshot = _read_tsv(CLINVAR_TSV)
    cr = clinvar_records(snapshot, json.load(open(CLINVAR_ROWS)), vep_v2)
    snap_states = Counter(af_state(_float_or_none(r.get("gnomad_af"))) for r in snapshot)

    report = {
        "purpose": ("Exact handling of missing gnomAD records on the OP4 path, for the "
                    "Methods (peer review 2026-09-24 P1-4)."),
        "op4_rule": (f"sop_strict (op4='data_only'): OP4 iff gnomad_af is not None and "
                     f"gnomad_af < {OP4_MAX_AF}; None -> no OP4; 0.0 -> OP4 ('Absent from "
                     f"gnomAD'). Site coverage is not checked."),
        "encoding": {
            "clinvar": ("fetch_clinvar_oncogenicity.parse_vep_record: AF = max gnomADe/gnomADg "
                        "overall AF for the ALT allele over VEP colocated_variants, default "
                        "0.0 when none is found; None only when VEP returned no record."),
            "horak": ("horak_gnomad.json (GRCh37 key -> AF); stated to follow the same "
                      "convention, but no generating script is in the repository."),
        },
        "horak70": {"engine_config": horak_vicc.get("config"), **summarise(hr)},
        "clinvar_snapshot_all_rows": {"n": len(snapshot),
                                      "af_state_counts": {s: snap_states.get(s, 0)
                                                          for s in AF_STATES}},
        "clinvar_holdout_scored": summarise(cr),
        "provenance": {os.path.relpath(p, ROOT): _sha(p) for p in
                       (HORAK_TSV, HORAK_GNOMAD, HORAK_VICC, CLINVAR_TSV, CLINVAR_ROWS, VEP_V2)},
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out + ".tmp", "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    os.replace(args.out + ".tmp", args.out)
    print(f"[+] wrote {args.out}")
    for k in ("horak70", "clinvar_holdout_scored"):
        s = report[k]
        print(f"== {k}: n={s['n']} states={s['af_state_counts']} OP4={s['op4_fired']} "
              f"by_state={s['op4_fired_by_af_state']} v2={s['coded_zero_v2_crosscheck']}")
        if "op4_vs_curator" in s:
            print("   vs curator:", s["op4_vs_curator"])
        print("   nonzero discrepancies:", s["coded_zero_v2_nonzero_discrepancies"])
    print("== clinvar snapshot:", report["clinvar_snapshot_all_rows"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
