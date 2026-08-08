"""Run configuration recording — what fixed the model's behaviour on this run.

Every output this pipeline writes carries a :class:`~src.models.interpretation.Provenance`
record. Recording the model name and a timestamp is not enough to reproduce or
to audit a run, because the behaviour of an LLM-backed classifier is fixed just
as much by the system prompts, the sampling parameters, and the version of the
faithfulness contract in force. Those change silently under ordinary
refactoring, and a run whose prompts differ is a different run.

This module collects that configuration into one place:

* :func:`prompt_registry` — the canonical system prompts, by name.
* :func:`prompt_hashes` / :func:`prompt_hash` — per-prompt and combined digests.
* :func:`build_provenance` — assemble the full record the pipeline writes.

The digests are what make the record useful: a golden-set regression check can
compare the recorded ``prompt_hash`` against the snapshot's and report a prompt
change as the cause of a behavioural difference, rather than leaving it to be
guessed at.

Rationale and the external criteria this is modelled on are in
``docs/regulatory/international_standards.md``.
"""
from __future__ import annotations

import hashlib
import subprocess
from typing import Dict, List, Optional

from src.models.interpretation import Provenance

#: Version of the faithfulness/abstention contract in force. Bump this whenever
#: the *enforced behaviour* changes (what may be cited, when the system must
#: abstain, what the verifier is allowed to alter) — not for prose edits, which
#: the prompt hash already tracks.
GUARDRAIL_VERSION = "1.0"

#: Default sampling temperatures per call type, mirroring the classifier
#: defaults in :mod:`src.classify.llm`. Recorded so a later run that changes a
#: default is visible in the output rather than only in the diff.
DEFAULT_TEMPERATURES: Dict[str, float] = {
    "classify": 0.0,
    "parametric": 0.0,
    "self_consistency": 0.4,
    "explain_rule": 0.0,
    "qa": 0.0,
    "verify": 0.0,
}


def prompt_registry() -> Dict[str, str]:
    """Return the canonical system prompts keyed by call type.

    Imported lazily so that reading provenance never pulls in the classifier
    stack (and, through it, optional LLM dependencies).
    """
    from src.classify.llm import (
        SYSTEM_CLASSIFY, SYSTEM_EXPLAIN_RULE, SYSTEM_PARAMETRIC, SYSTEM_QA,
    )
    from src.classify.verify import SYSTEM_VERIFY

    return {
        "classify": SYSTEM_CLASSIFY,
        "parametric": SYSTEM_PARAMETRIC,
        "explain_rule": SYSTEM_EXPLAIN_RULE,
        "qa": SYSTEM_QA,
        "verify": SYSTEM_VERIFY,
    }


def _digest(text: str) -> str:
    """Short, stable content digest (sha256, first 16 hex chars)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def prompt_hashes() -> Dict[str, str]:
    """Per-prompt digests, so a diff points at *which* prompt moved."""
    return {name: _digest(text) for name, text in sorted(prompt_registry().items())}


def prompt_hash() -> str:
    """One digest over the whole prompt set (order-independent by sorting)."""
    joined = "\n\x1e".join(f"{name}\x1f{text}" for name, text in sorted(prompt_registry().items()))
    return _digest(joined)


def code_revision() -> Optional[str]:
    """Short git commit of the working tree, or ``None`` outside a checkout.

    Suffixed ``-dirty`` when the tree has uncommitted changes, because a clean
    hash on a modified tree would misrepresent what actually ran.
    """
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        return f"{rev}-dirty" if dirty else rev
    except Exception:  # noqa: BLE001 - not a git checkout, or git unavailable
        return None


def build_provenance(
    *,
    live: bool,
    model_name: Optional[str],
    data_sources: Optional[dict] = None,
    timestamp: str = "",
    n_variants: Optional[int] = None,
    techniques: Optional[List[str]] = None,
    retrieval_index: Optional[dict] = None,
    temperatures: Optional[Dict[str, float]] = None,
    n_votes: Optional[int] = None,
    seed: Optional[int] = None,
) -> Provenance:
    """Assemble the provenance record for one run.

    ``live`` distinguishes a real API run from the offline deterministic
    fallback; the two are not interchangeable results and the record says which
    one produced the output.
    """
    index = retrieval_index or {}
    return Provenance(
        mode_used="live" if live else "offline",
        model_name=model_name,
        # Derived from the index rather than passed separately, so the recorded
        # embedder can never disagree with the index it actually queried.
        embedding_model=index.get("embedder"),
        retrieval_index=index,
        data_sources=data_sources or {},
        timestamp=timestamp,
        seed=seed,
        n_variants=n_variants,
        techniques=techniques or ["single-pass"],
        temperatures=temperatures if temperatures is not None else dict(DEFAULT_TEMPERATURES),
        n_votes=n_votes,
        prompt_hash=prompt_hash(),
        prompt_hashes=prompt_hashes(),
        guardrail_version=GUARDRAIL_VERSION,
        code_revision=code_revision(),
    )
