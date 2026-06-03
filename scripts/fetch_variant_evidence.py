"""Populate per-variant evidence caches for the cohort (AlphaMissense + trials).

Iterates the loaded cohort variants and warms two caches so the pipeline can run
fully offline afterwards:
  * AlphaMissense scores via Ensembl VEP REST (GRCh37) for missense SNVs
  * ClinicalTrials.gov details for the NCT ids CIViC links to each variant

Run:  python -m scripts.fetch_variant_evidence
Outputs:
  data/knowledge/alphamissense/vep_cache.json
  data/knowledge/trials/trials_cache.json
"""
import sys
import time

from src.cohort.loader import load_cohort
from src.knowledge.civic import CivicSource
from src.knowledge.alphamissense import AlphaMissenseAnnotator
from src.knowledge.clinical_trials import ClinicalTrialsSource


def main():
    variants = load_cohort()
    print(f"[*] {len(variants)} candidate variants in cohort.")

    # AlphaMissense (VEP REST, live) — caches scores + misses.
    amis = AlphaMissenseAnnotator(offline=False)
    n_am = 0
    for v in variants:
        ev = amis.evidence_for_variant(v)
        if ev:
            n_am += 1
        time.sleep(0.2)  # be polite to the public REST API
    print(f"[+] AlphaMissense: scored {n_am} missense SNVs -> {amis.cache_path}")

    # Clinical trials: collect CIViC NCT ids per variant, fetch details live.
    civic = CivicSource()
    trials = ClinicalTrialsSource(offline=False)
    nct_ids = set()
    for v in variants:
        for t in civic.trials(v.gene, v.hgvsp):
            nct_ids.add(t.nct_id)
    if nct_ids:
        trials.enrich(sorted(nct_ids))
    print(f"[+] Trials: cached {len(nct_ids)} NCT ids -> {trials.cache_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
