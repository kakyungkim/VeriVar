"""Deterministic faithfulness-enforcement gate — auditability by construction.

The four leakage-free faithfulness metrics in :mod:`src.eval.metrics` only *measure*
whether a Generative-mode (LLM) call cites real evidence, abstains when it should, and
agrees with the direction of its own citations. This module *enforces* them: a pure,
model-agnostic post-hoc pass that takes any Mode-A call plus its retrieved evidence
bundle and returns a corrected call that is faithful **by construction**, together with
an explicit audit trail of every gate that fired.

The point of the paper's faithfulness + **auditability** thesis is that faithfulness is
not something we hope a prompt elicits — it is a property we can *guarantee* and *show
our work* for. A fallible LLM may fabricate a citation, assert "oncogenic" while citing
only benign evidence, or fail to abstain when the bundle is empty; each of these is a
faithfulness violation that this gate detects and repairs deterministically, so the
shipped call can never be less faithful than the evidence supports.

Four gates, applied in order:

1. **Citation validation (anti-hallucination)** — drop any cited id that is not in the
   retrieved bundle. Fabricated ids can never survive, so the hallucination rate is 0
   by construction.
2. **Abstention** — if the bundle carries no variant-specific evidence, force abstention
   (VUS / Tier III); a confident call with nothing to stand on is unfaithful.
3. **Directional consistency** — if a non-abstained call's *surviving* citations do not
   point the same way as the call (oncogenic call with only benign evidence, or vice
   versa), abstain to VUS rather than contradict the cited evidence.
4. **Grounding** — a non-abstained call that has evidence available but cites none is
   not grounded; require it to abstain.

``enforce_faithfulness`` is pure (no I/O, no LLM) and unit-tested against adversarial
inputs, so it is itself fully auditable.
"""
from typing import Dict, List, Optional

_BENIGN_SIG = {"unaltered function", "benign", "likely benign", "neutral", "negative"}
_ONCOGENIC_CLASSES = {"Oncogenic", "Likely Oncogenic"}
_BENIGN_CLASSES = {"Benign", "Likely Benign"}
_AM_PATHOGENIC_T = 0.564
_AM_BENIGN_T = 0.34


def _bundle_index(variant: dict) -> Dict[str, dict]:
    """{evidence_id: evidence} for the variant's retrieved bundle."""
    return {e["id"]: e for e in (variant.get("bundle") or {}).get("evidences", [])}


def _supports_oncogenic(e: dict) -> bool:
    if e.get("source") == "AlphaMissense":
        return (e.get("score") or 0) >= _AM_PATHOGENIC_T
    return (e.get("direction") == "Supports"
            and (e.get("significance") or "").lower() not in _BENIGN_SIG)


def _supports_benign(e: dict) -> bool:
    if e.get("source") == "AlphaMissense":
        s = e.get("score")
        return s is not None and 0 < s <= _AM_BENIGN_T
    return (e.get("significance") or "").lower() in _BENIGN_SIG


def _abstain(mode_a: dict, reason: str, audit: List[str]) -> dict:
    """Return a VUS / Tier III abstention, preserving the rationale + an audit note."""
    audit.append(reason)
    out = dict(mode_a)
    out.update({
        "oncogenicity": "VUS",
        "tier": "Tier III",
        "tier_level": None,
        "abstained": True,
        "confidence": min(mode_a.get("confidence") if mode_a.get("confidence") is not None else 1.0, 0.5),
        "rationale": f"{mode_a.get('rationale', '')} [Faithfulness gate: {reason}]".strip(),
    })
    return out


def enforce_faithfulness(variant: dict) -> dict:
    """Return a copy of `variant` whose Mode-A call is faithful by construction.

    Adds a ``faithfulness_audit`` block: the gates that fired and the citations dropped.
    Mode B (the deterministic rule arm) is never touched.
    """
    mode_a = dict(variant.get("mode_a") or {})
    idx = _bundle_index(variant)
    audit: List[str] = []

    # Gate 1 — citation validation (anti-hallucination): keep only ids present in the bundle.
    cites = list(mode_a.get("citations") or [])
    valid = [c for c in cites if c in idx]
    dropped = [c for c in cites if c not in idx]
    if dropped:
        audit.append(f"dropped {len(dropped)} fabricated citation(s): {dropped}")
        mode_a["citations"] = valid

    already_abstained = bool(mode_a.get("abstained"))

    # Gate 2 — abstention: no variant-specific evidence at all -> must abstain.
    if not idx and not already_abstained:
        out = _abstain(mode_a, "no variant-specific evidence in bundle", audit)
        return _result(variant, out, dropped, audit)

    onc = mode_a.get("oncogenicity")

    # Gate 3 — directional consistency: surviving citations must point the call's way.
    if not mode_a.get("abstained") and valid:
        cited = [idx[c] for c in valid]
        if onc in _ONCOGENIC_CLASSES and not any(_supports_oncogenic(e) for e in cited):
            out = _abstain(mode_a, "oncogenic call not supported by its cited evidence", audit)
            return _result(variant, out, dropped, audit)
        if onc in _BENIGN_CLASSES and not any(_supports_benign(e) for e in cited):
            out = _abstain(mode_a, "benign call not supported by its cited evidence", audit)
            return _result(variant, out, dropped, audit)

    # Gate 4 — grounding: a non-abstained directional call with evidence must cite some.
    if (not mode_a.get("abstained") and idx and not valid
            and onc in (_ONCOGENIC_CLASSES | _BENIGN_CLASSES)):
        out = _abstain(mode_a, "directional call with available evidence cited nothing", audit)
        return _result(variant, out, dropped, audit)

    return _result(variant, mode_a, dropped, audit)


def _result(variant: dict, mode_a: dict, dropped: List[str], audit: List[str]) -> dict:
    out = dict(variant)
    out["mode_a"] = mode_a
    out["faithfulness_audit"] = {
        "gates_fired": audit,
        "citations_dropped": dropped,
        "corrected": bool(audit),
    }
    return out


def enforce_cohort(variants: List[dict]) -> List[dict]:
    """Apply :func:`enforce_faithfulness` across a cohort's variant list."""
    return [enforce_faithfulness(v) for v in variants]
