#!/usr/bin/env python
"""Count the words of an abstract under the two counting rules conference forms use.

Conference abstract limits (for example the 200-word GIW/ISCB-Asia limit) do not say
how words are counted. This script reports both readings so a draft can be kept under
the limit either way:

* ``whitespace``: tokens separated by whitespace, the same as ``wc -w``.
* ``split``: whitespace tokens further split on ``/`` and ``-`` (and the en dash), so
  that "ClinGen/CGC/VICC" counts as three words and "leave-own-evidence-out" as four.
  Tokens left empty by the split (for example a bare "-") are not counted.

Input is either a whole text file or one section of a Markdown file. With
``--section "Body"`` the script takes the lines under the first heading whose text is
exactly ``Body`` (any heading level) up to the next heading of the same or a higher
level. With ``--fenced`` it takes the first fenced code block instead.

Examples::

    python -m scripts.count_abstract_words notes/publication/abstract_GIW2026_LBA.md --section Body
    python -m scripts.count_abstract_words abstract.txt

Standard library only; reads the file and prints, writes nothing.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
SPLIT_CHARS = re.compile(r"[/\-–]")


def extract_section(text: str, title: str) -> str:
    """Return the lines under the first Markdown heading named ``title``."""
    lines = text.splitlines()
    start, level = None, None
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if m and m.group(2).strip() == title:
            start, level = i + 1, len(m.group(1))
            break
    if start is None:
        raise SystemExit(f"heading {title!r} not found")
    body = []
    for line in lines[start:]:
        m = HEADING.match(line)
        if m and len(m.group(1)) <= level:
            break
        body.append(line)
    return "\n".join(body).strip()


def extract_fenced(text: str) -> str:
    """Return the contents of the first fenced code block."""
    m = re.search(r"```[^\n]*\n(.*?)```", text, flags=re.S)
    if not m:
        raise SystemExit("no fenced code block found")
    return m.group(1).strip()


def count_whitespace(text: str) -> int:
    """Whitespace-delimited tokens (the ``wc -w`` rule)."""
    return len(text.split())


def count_split(text: str) -> int:
    """Whitespace tokens further split on slash, hyphen and en dash."""
    n = 0
    for tok in text.split():
        n += sum(1 for part in SPLIT_CHARS.split(tok) if re.search(r"\w", part))
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=pathlib.Path, help="text or Markdown file")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--section", help="count only the Markdown section under this heading")
    grp.add_argument("--fenced", action="store_true", help="count only the first fenced code block")
    ap.add_argument("--limit", type=int, default=200, help="word limit to check against (default 200)")
    args = ap.parse_args(argv)

    text = args.path.read_text(encoding="utf-8")
    if args.section:
        text = extract_section(text, args.section)
    elif args.fenced:
        text = extract_fenced(text)

    ws, sp = count_whitespace(text), count_split(text)
    print(f"whitespace words: {ws}")
    print(f"split words (/ and - split): {sp}")
    print(f"characters: {len(text)}")
    ok = ws <= args.limit and sp <= args.limit
    print(f"limit {args.limit}: {'OK under both counts' if ok else 'OVER under at least one count'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
