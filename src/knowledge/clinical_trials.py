"""ClinicalTrials.gov API v2 adapter — enrich CIViC trial links with details.

CIViC evidence rows carry NCT ids but no trial metadata. This adapter turns an
NCT id into a populated :class:`ClinicalTrial` (title/status/phase), using a
local cache for offline reproducibility. By default it is offline (cache-only);
``scripts/fetch_knowledge.py`` populates the cache from the cohort's CIViC NCT
ids so the committed snapshot is self-contained.
"""
import json
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from src.models import ClinicalTrial

API = "https://clinicaltrials.gov/api/v2/studies"
DEFAULT_CACHE = Path("data/knowledge/trials/trials_cache.json")


def _parse_study(study: dict) -> dict:
    ps = study.get("protocolSection", {})
    ident = ps.get("identificationModule", {})
    status = ps.get("statusModule", {})
    design = ps.get("designModule", {})
    arms = ps.get("armsInterventionsModule", {})
    cond = ps.get("conditionsModule", {})
    interventions = [i.get("name", "") for i in arms.get("interventions", []) if i.get("name")]
    return {
        "nct_id": ident.get("nctId", ""),
        "title": ident.get("briefTitle", ""),
        "status": status.get("overallStatus"),
        "phase": ", ".join(design.get("phases", []) or []) or None,
        "conditions": cond.get("conditions", []) or [],
        "interventions": interventions,
        "url": f"https://clinicaltrials.gov/study/{ident.get('nctId','')}",
    }


class ClinicalTrialsSource:
    name = "ClinicalTrials.gov"

    def __init__(self, cache_path: Path = DEFAULT_CACHE, offline: bool = True):
        self.cache_path = Path(cache_path)
        self.offline = offline
        self._cache: Dict[str, dict] = {}
        if self.cache_path.exists():
            self._cache = json.loads(self.cache_path.read_text())

    def fetch_one(self, nct_id: str) -> Optional[dict]:
        """Live fetch a single study's details (network); returns parsed dict."""
        req = urllib.request.Request(f"{API}/{nct_id}", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return _parse_study(json.load(r))
        except Exception:
            return None

    def enrich(self, nct_ids: List[str]) -> List[ClinicalTrial]:
        """NCT ids -> ClinicalTrial objects (cache first, then live unless offline)."""
        out, updated = [], False
        for nct in dict.fromkeys(n for n in nct_ids if n):  # de-dup, keep order
            rec = self._cache.get(nct)
            if rec is None and not self.offline:
                rec = self.fetch_one(nct)
                if rec:
                    self._cache[nct] = rec
                    updated = True
            if rec:
                out.append(ClinicalTrial(**rec))
            else:
                out.append(ClinicalTrial(nct_id=nct, url=f"https://clinicaltrials.gov/study/{nct}"))
        if updated:
            self._save()
        return out

    def _save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, indent=2))
