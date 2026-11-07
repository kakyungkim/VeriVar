"""One citation taxonomy applied identically to every arm (pure, offline).

Why this exists
---------------
The earlier headline contrasted "0 of 106 retrieval-arm citations outside the
bundle" with "fabricated citations on 26/56 no-retrieval variants". The two
numbers used different rules: the retrieval arm exempted bare source names and
digit tokens as "imprecision", while the no-retrieval arm counted every emitted
token as fabricated because it has no bundle (peer review 2026-09-24, P0-1 and
P0-2). This module classifies every emitted citation token with a single rule
set that does not look at which arm produced it. The only arm-dependent input
is the evidence bundle, which is empty for the no-retrieval arm.

Pre-specified rules
-------------------
The rules below were written into this docstring before this module first
produced counts (2026-09-24). They are not a blind pre-registration: the
reviewer's manual breakdown of the 26 no-retrieval variants (P0-1) was already
known when they were written. One clarification was added on 2026-09-27
(PMID-backed bundle membership, step 2) after the first run; it changes no
count in any arm (all PMIDs emitted by any arm resolve outside every bundle),
which ``scripts/run_citation_taxonomy.py`` checks and reports.

Step 1, token shape. Each token is stripped and parsed as ``NAMESPACE: VALUE``
when it has an alphabetic prefix followed by a colon; otherwise it is a bare
value. A token is *identifier-bearing* when it matches one of these schemes:

* ``pmid``        ``PMID: 123`` / ``PMID123`` (PubMed; resolvable via NCBI).
* ``clinvar``     ``VCV000123`` / ``RCV000123`` with or without ``ClinVar:``
  (resolvable via NCBI ``db=clinvar``; the numeric part is the VariationID).
* ``civic_eid``   ``EID123`` with or without ``CIViC:``.
* ``nct``         ``NCT`` + 8 digits (ClinicalTrials.gov).
* ``coordinate``  ``chrom:posREF>ALT`` with or without ``AlphaMissense:``.
* ``unschemed_numeric`` a digit string under a namespace that issues no bare
  numeric identifiers (``ClinGen``, ``CGC``, ``VICC``, ``OncoKB``,
  ``COSMIC``). The token is identifier-shaped but cannot name any record.

Everything else is a *non-identifier*: a bare source name (``AlphaMissense``,
``ClinGen``), a source name plus a gene (``ClinGen: BRAF``), a bare digit
token with no namespace (``1``, ``123``) or a criterion code (``OP1``).

Step 2, bundle membership (identifier-bearing tokens only). A token is in the
bundle when it equals a bundle id exactly, or when exactly one bundle id has
it as the part after the first colon (``EID6003`` -> ``CIViC:EID6003``,
``7:140481402C>T`` -> ``AlphaMissense:7:140481402C>T``). This is the same
resolver as ``scripts/run_nli_attribution.resolve_citation``. A ``pmid``
token is also in the bundle when its number equals a PMID attached to a bundle
item (``evidences[].pmids``, e.g. the paper behind a CIViC evidence item);
the resolved id is then ``<bundle id>#PMID<number>`` (2026-09-27 clarification).

Bundle for the no-retrieval arm
-------------------------------
The no-retrieval arm received no bundle, so "in the bundle" needs a stated
reference set. Two definitions are reported, and the rules above are applied
unchanged under each:

* **E (empty bundle).** Bundle = empty set. Every identifier is out of bundle
  and goes to step 3.
* **R (reference bundle).** Bundle = the retrieval bundle stored for the same
  variant in ``cohort_interpretation.json`` (the set the retrieval arms could
  cite). An identifier the no-retrieval arm emits that happens to name an item
  of that set (or a PMID behind one) is category ``a``.

The fabricated / misattributed categories do not depend on the bundle at all
(they come from token shape and the NCBI lookup), so E and R can differ only
by moving tokens from ``b2``/``c`` into ``a``.

Step 3, out-of-bundle identifiers, in this order:

1. ``unschemed_numeric`` -> fabricated (reason ``no_such_identifier_scheme``).
2. The numeric part (leading zeros stripped) is a placeholder pattern -> fabricated
   (reason ``placeholder_pattern``), even when a record with that number
   happens to exist (``PMID 12345678`` is a 1994 population declaration).
   A placeholder pattern is a string of >= 4 digits that is a single repeated
   digit or a run in which every digit is the previous digit +1 (mod 10)
   throughout, or -1 (mod 10) throughout: ``123456``, ``12345678``,
   ``87654321``, ``789012``, ``345678``. An existence-only sensitivity count,
   which lets such records fall through to steps 3-4, is reported alongside.
3. Looked up in the cache and no record exists -> fabricated (``no_record``).
4. Record exists: *related* if its text (PubMed title + abstract; ClinVar
   title + gene list) mentions the variant's gene symbol or a listed alias as a
   whole word (case-insensitive) -> ``b2_real_related_out_of_bundle``;
   otherwise -> ``c_real_unrelated_out_of_bundle`` (a real record attached to
   a variant it does not discuss: identifier-level misattribution, Type II).
   A stricter flag also records whether the protein change itself is named.
5. Not in the cache -> ``b0_out_of_bundle_unchecked`` (should be zero; a
   non-zero count means the lookup was not run for that token).

Categories
----------
``a_in_bundle``, ``b1_fabricated_identifier``, ``b2_real_related_out_of_bundle``,
``c_real_unrelated_out_of_bundle``, ``b0_out_of_bundle_unchecked``,
``d_non_identifier``.

In-bundle items are retrieved for the variant, so their content relevance is
the subject of the NLI (Type II) audit, not of this module. For the retrieval
arms a non-identifier that names the single bundle item of that source (bare
``AlphaMissense`` with one AlphaMissense item) is flagged
``uniquely_resolvable_in_bundle`` but is still category ``d``.

Variant-level flags
-------------------
``any_citation``; ``any_fabricated`` (>= 1 ``b1``); ``any_fabricated_or_misattributed``
(>= 1 ``b1`` or ``c``); ``any_out_of_bundle_identifier`` (>= 1 of b0/b1/b2/c);
``any_non_identifier`` (>= 1 ``d``).
"""
from __future__ import annotations

import re
from collections import Counter
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, Field


class CitationCategory(str, Enum):
    """Mutually exclusive category of one emitted citation token."""

    IN_BUNDLE = "a_in_bundle"
    UNCHECKED = "b0_out_of_bundle_unchecked"
    FABRICATED = "b1_fabricated_identifier"
    REAL_RELATED = "b2_real_related_out_of_bundle"
    REAL_UNRELATED = "c_real_unrelated_out_of_bundle"
    NON_IDENTIFIER = "d_non_identifier"


CATEGORY_ORDER: List[CitationCategory] = list(CitationCategory)
OUT_OF_BUNDLE_IDENTIFIER = {CitationCategory.UNCHECKED, CitationCategory.FABRICATED,
                            CitationCategory.REAL_RELATED, CitationCategory.REAL_UNRELATED}

UNSCHEMED_NAMESPACES = {"clingen", "cgc", "vicc", "oncokb", "cosmic"}

# Common aliases used in titles/abstracts; fixed a priori.
GENE_ALIASES: Dict[str, List[str]] = {
    "TP53": ["p53"],
    "KRAS": ["K-ras", "Ki-ras", "K-ras2"],
    "NRAS": ["N-ras"],
    "BRAF": ["B-raf"],
    "PIK3CA": ["PI3K", "p110alpha", "p110α", "PI3Kalpha", "PI3Kα"],
    "EGFR": ["ErbB1", "HER1"],
    "ERBB2": ["HER2", "neu"],
    "CDKN2A": ["p16", "p16INK4a", "INK4a"],
    "PTEN": [],
    "APC": [],
    "BRCA2": [],
}

_NS = re.compile(r"^([A-Za-z][A-Za-z0-9_\-]*)\s*:\s*(.+)$")
_PMID = re.compile(r"^PMID\s*:?\s*(\d+)$", re.I)
_CLINVAR = re.compile(r"^(?:ClinVar\s*:\s*)?((?:VCV|RCV)0*(\d+))(?:\.\d+)?$", re.I)
_EID = re.compile(r"^(?:CIViC\s*:\s*)?EID(\d+)$", re.I)
_NCT = re.compile(r"^(?:ClinicalTrials(?:\.gov)?\s*:\s*)?(NCT\d{8})$", re.I)
_COORD = re.compile(r"^(?:AlphaMissense\s*:\s*)?(?:chr)?([0-9]{1,2}|X|Y|MT)"
                    r":(\d+)([ACGT]+)>([ACGT]+)$", re.I)
_DIGITS = re.compile(r"^\d+$")

_AA3 = {"A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys", "E": "Glu",
        "Q": "Gln", "G": "Gly", "H": "His", "I": "Ile", "L": "Leu", "K": "Lys",
        "M": "Met", "F": "Phe", "P": "Pro", "S": "Ser", "T": "Thr", "W": "Trp",
        "Y": "Tyr", "V": "Val", "*": "Ter"}


class ParsedToken(BaseModel):
    """Shape of one token (step 1)."""

    raw: str
    kind: str  # pmid|clinvar|civic_eid|nct|coordinate|unschemed_numeric|non_identifier
    number: Optional[str] = None  # numeric part used for lookup / placeholder test
    non_identifier_type: Optional[str] = None  # source_name|source_plus_gene|bare_digits|code|other

    @property
    def is_identifier(self) -> bool:
        return self.kind != "non_identifier"


class CitationRecord(BaseModel):
    """Classification of one emitted token for one variant."""

    variant_index: int
    variant_id: str
    gene: str
    hgvsp: str
    token: str
    kind: str
    category: CitationCategory
    reasons: List[str] = Field(default_factory=list)
    resolved_bundle_id: Optional[str] = None
    uniquely_resolvable_in_bundle: bool = False
    record_exists: Optional[bool] = None
    record_title: Optional[str] = None
    mentions_gene: Optional[bool] = None
    mentions_protein_change: Optional[bool] = None
    placeholder: bool = False


def is_placeholder_number(num: str) -> bool:
    """True for >= 4-digit repeated-digit or strict +1/-1 (mod 10) runs."""
    s = num.lstrip("0")
    if len(s) < 4 or not s.isdigit():
        return False
    if len(set(s)) == 1:
        return True
    d = [int(c) for c in s]
    steps = {(b - a) % 10 for a, b in zip(d, d[1:])}
    return steps == {1} or steps == {9}


def parse_token(tok: str) -> ParsedToken:
    """Step 1: classify the shape of an emitted token."""
    t = (tok or "").strip()
    m = _PMID.match(t)
    if m:
        return ParsedToken(raw=tok, kind="pmid", number=m.group(1))
    m = _CLINVAR.match(t)
    if m:
        return ParsedToken(raw=tok, kind="clinvar", number=m.group(2))
    m = _EID.match(t)
    if m:
        return ParsedToken(raw=tok, kind="civic_eid", number=m.group(1))
    m = _NCT.match(t)
    if m:
        return ParsedToken(raw=tok, kind="nct", number=m.group(1)[3:])
    if _COORD.match(t):
        return ParsedToken(raw=tok, kind="coordinate")
    m = _NS.match(t)
    if m:
        ns, val = m.group(1), m.group(2).strip()
        if _DIGITS.match(val) and ns.lower() in UNSCHEMED_NAMESPACES:
            return ParsedToken(raw=tok, kind="unschemed_numeric", number=val)
        if re.match(r"^[A-Z0-9\-]+$", val) and not _DIGITS.match(val):
            return ParsedToken(raw=tok, kind="non_identifier",
                               non_identifier_type="source_plus_gene")
        return ParsedToken(raw=tok, kind="non_identifier", non_identifier_type="other")
    if _DIGITS.match(t):
        return ParsedToken(raw=tok, kind="non_identifier", number=t,
                           non_identifier_type="bare_digits")
    if re.match(r"^[A-Z]{1,4}\d{1,2}$", t):
        return ParsedToken(raw=tok, kind="non_identifier", non_identifier_type="code")
    if re.match(r"^[A-Za-z][A-Za-z\.\- ]*$", t):
        return ParsedToken(raw=tok, kind="non_identifier", non_identifier_type="source_name")
    return ParsedToken(raw=tok, kind="non_identifier", non_identifier_type="other")


def resolve_in_bundle(tok: str, bundle_ids: Sequence[str],
                      bundle_pmids: Optional[Dict[str, List[str]]] = None) -> Optional[str]:
    """Step 2: exact or unique suffix match against bundle ids, or a PMID that
    backs a bundle item (``bundle_pmids`` maps bundle id -> attached PMIDs)."""
    t = tok.strip()
    if t in bundle_ids:
        return t
    norm = [i for i in bundle_ids if i.split(":", 1)[-1] == t]
    if len(norm) == 1:
        return norm[0]
    parsed = parse_token(t)
    if parsed.kind == "pmid" and parsed.number and bundle_pmids:
        num = parsed.number.lstrip("0") or "0"
        for bid in bundle_ids:
            if num in {(x or "").strip().lstrip("0") for x in bundle_pmids.get(bid, [])}:
                return f"{bid}#PMID{num}"
    return None


def protein_change_forms(hgvsp: str) -> List[str]:
    """Short and three-letter forms of a protein change, e.g. V600E / Val600Glu."""
    m = re.match(r"^p\.([A-Z\*])(\d+)([A-Z\*])$", hgvsp or "")
    if not m:
        return []
    a, pos, b = m.groups()
    forms = [f"{a}{pos}{b}"]
    if a in _AA3 and b in _AA3:
        forms.append(f"{_AA3[a]}{pos}{_AA3[b]}")
    return forms


def _mentions(text: str, terms: Iterable[str]) -> bool:
    for term in terms:
        if term and re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])",
                              text, re.I):
            return True
    return False


def gene_terms(gene: str) -> List[str]:
    return [gene] + GENE_ALIASES.get(gene, [])


def lookup_record(parsed: ParsedToken, cache: dict) -> Optional[dict]:
    """Return the cached record for a resolvable identifier, or None if not cached."""
    table = {"pmid": "pmid", "clinvar": "clinvar"}.get(parsed.kind)
    if table is None or parsed.number is None:
        return None
    return (cache.get(table) or {}).get(parsed.number.lstrip("0") or "0")


def record_text(kind: str, rec: dict) -> str:
    if kind == "clinvar":
        return " ".join([rec.get("title") or "", " ".join(rec.get("genes") or [])])
    return " ".join([rec.get("title") or "", rec.get("abstract") or ""])


def classify_token(tok: str, *, variant_index: int, variant_id: str, gene: str,
                   hgvsp: str, bundle_ids: Sequence[str],
                   bundle_sources: Optional[Dict[str, str]] = None,
                   cache: Optional[dict] = None,
                   bundle_pmids: Optional[Dict[str, List[str]]] = None) -> CitationRecord:
    """Apply steps 1-3 to one token."""
    cache = cache or {}
    parsed = parse_token(tok)
    base = dict(variant_index=variant_index, variant_id=variant_id, gene=gene,
                hgvsp=hgvsp, token=tok, kind=parsed.kind)
    if not parsed.is_identifier:
        uniq = False
        if bundle_sources:
            same = [i for i, s in bundle_sources.items() if s == tok.strip()]
            uniq = len(same) == 1
        return CitationRecord(**base, category=CitationCategory.NON_IDENTIFIER,
                              reasons=[f"non_identifier:{parsed.non_identifier_type}"],
                              uniquely_resolvable_in_bundle=uniq)
    rid = resolve_in_bundle(tok, bundle_ids, bundle_pmids)
    if rid is not None:
        return CitationRecord(**base, category=CitationCategory.IN_BUNDLE,
                              resolved_bundle_id=rid)
    reasons: List[str] = []
    placeholder = bool(parsed.number) and is_placeholder_number(parsed.number)
    if parsed.kind == "unschemed_numeric":
        reasons.append("no_such_identifier_scheme")
    if placeholder:
        reasons.append("placeholder_pattern")
    rec = lookup_record(parsed, cache)
    exists = title = mg = mp = None
    if rec is not None:
        exists = bool(rec.get("exists"))
        title = rec.get("title")
        if exists:
            text = record_text(parsed.kind, rec)
            mg = _mentions(text, gene_terms(gene))
            mp = _mentions(text, protein_change_forms(hgvsp))
    extra = dict(record_exists=exists, record_title=title, mentions_gene=mg,
                 mentions_protein_change=mp, placeholder=placeholder)
    if reasons:
        return CitationRecord(**base, category=CitationCategory.FABRICATED,
                              reasons=reasons, **extra)
    if rec is None:
        return CitationRecord(**base, category=CitationCategory.UNCHECKED,
                              reasons=["not_in_lookup_cache"], **extra)
    if not exists:
        return CitationRecord(**base, category=CitationCategory.FABRICATED,
                              reasons=["no_record"], **extra)
    cat = CitationCategory.REAL_RELATED if mg else CitationCategory.REAL_UNRELATED
    return CitationRecord(**base, category=cat,
                          reasons=["record_mentions_gene" if mg else "record_unrelated_to_gene"],
                          **extra)


def existence_only_category(r: CitationRecord) -> CitationCategory:
    """Sensitivity: placeholders that resolve to a real record re-bin by relevance."""
    if (r.category == CitationCategory.FABRICATED and r.reasons == ["placeholder_pattern"]
            and r.record_exists):
        return CitationCategory.REAL_RELATED if r.mentions_gene else CitationCategory.REAL_UNRELATED
    return r.category


class VariantInput(BaseModel):
    """One variant of one arm: emitted tokens plus the bundle it could cite."""

    variant_index: int
    variant_id: str
    gene: str
    hgvsp: str
    citations: List[str]
    bundle_ids: List[str] = Field(default_factory=list)
    bundle_sources: Dict[str, str] = Field(default_factory=dict)
    bundle_pmids: Dict[str, List[str]] = Field(default_factory=dict)


def classify_variants(variants: Sequence[VariantInput], cache: dict) -> List[CitationRecord]:
    """Classify every token of every variant."""
    out: List[CitationRecord] = []
    for v in variants:
        for tok in v.citations:
            out.append(classify_token(tok, variant_index=v.variant_index,
                                      variant_id=v.variant_id, gene=v.gene, hgvsp=v.hgvsp,
                                      bundle_ids=v.bundle_ids,
                                      bundle_sources=v.bundle_sources, cache=cache,
                                      bundle_pmids=v.bundle_pmids))
    return out


def variant_flags(variants: Sequence[VariantInput], records: Sequence[CitationRecord],
                  existence_only: bool = False) -> List[dict]:
    """Per-variant category counts and the pre-specified flags."""
    by_v: Dict[int, List[CitationRecord]] = {}
    for r in records:
        by_v.setdefault(r.variant_index, []).append(r)
    rows = []
    for v in variants:
        recs = by_v.get(v.variant_index, [])
        cats = [existence_only_category(r) if existence_only else r.category for r in recs]
        c = Counter(cats)
        rows.append({
            "variant_index": v.variant_index, "variant_id": v.variant_id,
            "n_citations": len(recs),
            "counts": {k.value: c.get(k, 0) for k in CATEGORY_ORDER},
            "any_citation": bool(recs),
            "any_fabricated": c.get(CitationCategory.FABRICATED, 0) > 0,
            "any_fabricated_or_misattributed": (c.get(CitationCategory.FABRICATED, 0)
                                                + c.get(CitationCategory.REAL_UNRELATED, 0)) > 0,
            "any_out_of_bundle_identifier": sum(c.get(k, 0) for k in OUT_OF_BUNDLE_IDENTIFIER) > 0,
            "any_non_identifier": c.get(CitationCategory.NON_IDENTIFIER, 0) > 0,
            "tokens": [{"token": r.token, "category": cat.value, "reasons": r.reasons}
                       for r, cat in zip(recs, cats)],
        })
    return rows


VARIANT_FLAGS = ["any_citation", "any_fabricated", "any_fabricated_or_misattributed",
                 "any_out_of_bundle_identifier", "any_non_identifier"]
