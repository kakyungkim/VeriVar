"""Declarative, audited repository reorganisation (dry run by default).

Purpose
-------
Moves, renames and deletes files according to the declarative tables in
:func:`default_spec`, then rewrites every textual reference to the old paths so
that links, script defaults and docs keep pointing at the right file. The
tables encode the 2026-09-24 clean-up (root clutter to ``archive/`` and
``notes/``, ``docs/`` split into ``harness/ reference/ talks/``, manuscript
reviews into ``docs/manuscript/reviews/``, local memos out of the tracked tree,
legacy figures archived, ``F6_dashboard.png`` renamed ``figS3_dashboard.png``).

What it does, in order (``--apply`` only)
-----------------------------------------
1. Build the plan: expand globs and directories into per-file operations, check
   every source exists, refuse any destination that already exists (or that two
   sources would share), evaluate conditional items (``LICENSE.txt`` is deleted
   only when its sha256 equals ``LICENSE``; ``.tmp_cc/`` only when empty).
2. Back up every affected file (move sources, delete targets, every text file
   that will be rewritten, ``.gitignore``) into
   ``<backup-root>/<timestamp>/files/`` and write ``manifest_before.json``
   (path, size, sha256 for every file outside ``venv/`` and ``.git/``). The
   backup copies are re-hashed before anything is changed.
3. Delete junk (``.DS_Store``, ``__pycache__/``) and the listed deletes.
   Tracked files are removed from the index with ``git rm --cached``.
4. Move / rename. Tracked files use ``git mv`` (history is kept). Tracked files
   whose destination is local-only (``archive/``, ``notes/``) are moved and then
   untracked with ``git rm --cached`` -- otherwise they would stay tracked
   inside an ignored folder. Untracked/ignored files are moved with
   ``os.replace``. The sha256 of every moved file is verified immediately.
5. Rewrite path references in text files (md, py, sh, html, json, yml, yaml,
   toml, j2) outside ``venv/ .git/ experiments/ archive/``. Two mechanisms, in
   a single non-overlapping pass per file:
   * path-string rules (auto-generated from every move, plus the manual
     ``PATH_REWRITES``), matched on path-token boundaries;
   * relative-link repair for Markdown ``](target)`` and HTML ``href=/src=``:
     each relative target is resolved against the file's *old* directory and
     re-expressed relative to its *new* directory, so links inside moved files
     and links to moved files both keep working.
   A file is only written if its sha256 still equals the value seen at plan
   time (protects against concurrent edits).
6. Edit ``.gitignore`` (declarative ops) and create the new README files.
7. Verify: file count after == before - deleted + created, every moved file
   is present at its destination with an unchanged sha256 (checked before the
   rewrite step and again at the end for files that were not rewritten), and
   nothing from the before-manifest is unaccounted for. Prints
   ``N moved, M rewritten, K deleted, 0 lost`` and writes
   ``manifest_after.json``.

Safety
------
* Default is a dry run: nothing in the repository changes except the plan
  report (``--plan-out``, default ``notes/audits/2026-09-24/reorg_plan.json``,
  a local-only folder). ``--apply`` is required to change anything.
* Apply refuses to start if any destination exists, two sources collide, or a
  source is missing (unless ``--allow-missing``; optional items such as
  ``docs/manuscript/working/`` never count as missing).
* No overwrite, ever. No commit. No ``git add`` of new files.
* The tool, its test, and its own plan report are excluded from rewriting.
* A git-status simulation (sandbox repo with the before / after ``.gitignore``
  and the real index, queried with ``git status --porcelain --ignored``)
  reports every path that would become newly trackable or newly ignored, and
  checks that ``archive/`` and ``notes/`` stay ignored while
  ``docs/{harness,reference,talks}`` and ``docs/manuscript/reviews`` stay
  trackable.

Run
---
    python -m scripts.reorganize_repo                  # dry run, full plan printed
    python -m scripts.reorganize_repo --diff           # ... plus a diff of every rewrite
    python -m scripts.reorganize_repo --apply          # perform it
    python -m scripts.reorganize_repo --apply --allow-missing
    python -m scripts.reorganize_repo --rewrite-exclude 'data/**'   # keep data/ untouched

Output
------
* stdout: the full plan (moves, renames, deletes, per-file rewrite counts, link
  repairs, .gitignore diff, created files, git-status transitions, warnings),
  and on apply the verification summary.
* ``--plan-out`` JSON: the same plan plus, on apply, the results and the backup
  location.
* ``<backup-root>/<timestamp>/``: ``files/`` copies, ``manifest_before.json``,
  ``manifest_after.json`` (apply only).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import fnmatch
import glob as _glob
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Literal, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
#: Backups go to the system temp directory unless --backup-root says otherwise.
DEFAULT_BACKUP_ROOT = Path(tempfile.gettempdir()) / "verivar_bak_reorg"
DEFAULT_PLAN_OUT = "notes/audits/2026-09-24/reorg_plan.json"

TEXT_EXTS = frozenset({".md", ".py", ".sh", ".html", ".json", ".yml", ".yaml",
                       ".toml", ".j2"})
#: Top-level directories never scanned for rewrites.
REWRITE_EXCLUDE_TOP = ("venv", ".git", "experiments", "archive")
#: Top-level directories never walked at all (manifests, status simulation).
WALK_EXCLUDE_TOP = ("venv", ".git")
#: Destinations under these prefixes are local-only (git-ignored).
LOCAL_ONLY_PREFIXES = ("archive/", "notes/")
#: Files this tool must never rewrite (it and its test contain the old paths).
SELF_FILES = ("scripts/reorganize_repo.py", "tests/test_reorganize_repo.py")
#: Text files larger than this are skipped (reported) rather than rewritten.
MAX_REWRITE_BYTES = 50 * 1024 * 1024

JUNK_FILE_NAMES = frozenset({".DS_Store"})
JUNK_DIR_NAMES = frozenset({"__pycache__"})

Anchor = Literal["path", "root", "none"]


# --------------------------------------------------------------------------- #
# Declarative spec types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Move:
    """Move one source to a destination.

    ``src`` is a repo-relative file, a directory (trailing ``/``) or a glob.
    * glob -> every match goes *into* ``dst`` (a directory, basename kept);
    * directory -> the directory itself becomes ``dst`` (``dst`` = new dir path);
    * file -> if ``dst`` ends with ``/`` it goes into that dir, else ``dst`` is
      the exact new path.
    ``optional``: an absent source is reported as skipped, not missing.
    ``cleanup_src_dir``: remove the source (glob parent) directory if emptied.
    ``report_refs``: add a reference count (full path + basename) to the plan.
    """

    src: str
    dst: str
    note: str = ""
    optional: bool = False
    cleanup_src_dir: bool = False
    report_refs: bool = False


@dataclass(frozen=True)
class Rename:
    """Rename a file in place (same directory, new basename)."""

    src: str
    new_name: str
    note: str = ""


@dataclass(frozen=True)
class Delete:
    """Delete a file or directory.

    ``condition``: ``""`` (always), ``"identical_to:<path>"`` (sha256 must match,
    otherwise the item is skipped with a warning), ``"empty_dir"`` (directory
    must be empty, otherwise skipped).
    """

    path: str
    condition: str = ""
    note: str = ""


@dataclass(frozen=True)
class PathRewrite:
    """Replace a path string in text files.

    ``anchor`` controls token boundaries for literal rules:
    * ``"path"``: not preceded by ``[A-Za-z0-9_.-]`` (a ``/`` before is allowed,
      so absolute paths are caught);
    * ``"root"``: additionally not preceded by ``/`` (for root-level names that
      are suffixes of their new path);
    * ``"none"``: plain substring.
    All literal rules require the match not be followed by ``[A-Za-z0-9_-]`` or
    by ``.`` + alnum (so ``X.md`` never matches inside ``X.md.bak``).
    ``regex=True`` treats ``old`` as a regex and ``new`` as its expand template.
    ``include`` / ``exclude`` are fnmatch globs on the file's *original*
    repo-relative path.
    """

    old: str
    new: str
    anchor: Anchor = "path"
    regex: bool = False
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class GitignoreEdit:
    """Edit ``.gitignore``.

    * ``replace_line``: replace the exact line ``old`` by ``lines``;
    * ``append_block``: append ``lines`` unless every non-comment line of the
      block is already present.
    """

    op: Literal["replace_line", "append_block"]
    old: str = ""
    lines: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class CreateFile:
    """Create a new file (refused if it exists)."""

    path: str
    content: str
    note: str = ""


@dataclass
class ReorgSpec:
    """The full declarative plan."""

    moves: list[Move] = field(default_factory=list)
    renames: list[Rename] = field(default_factory=list)
    deletes: list[Delete] = field(default_factory=list)
    delete_junk: bool = True
    path_rewrites: list[PathRewrite] = field(default_factory=list)
    #: Extra exclude globs for the *auto-generated* rule whose ``old`` is the key.
    auto_rule_excludes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    gitignore_edits: list[GitignoreEdit] = field(default_factory=list)
    creates: list[CreateFile] = field(default_factory=list)
    must_be_ignored: tuple[str, ...] = ()
    must_be_trackable: tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# The 2026-09-24 plan
# --------------------------------------------------------------------------- #
ARCHIVE_README = """\
# archive/ (local only, git-ignored)

Material that is no longer part of the working project but is kept locally
because it documents how the project got here. Nothing in this folder is read
by code, tests, the manuscript gate, or the figure builder. It is excluded from
the public repository by the `archive/` line in `.gitignore`; files that were
previously tracked were moved here by `scripts/reorganize_repo.py` and removed
from the index with `git rm --cached` (their history remains in git log under
the old paths).

| Folder | Contents | Why it is kept |
| --- | --- | --- |
| `backups/` | `CLAUDE.md.bak_20260924`, `SUBMISSION_STEPS_LOCAL.md.bak_20260924` | Pre-edit snapshots taken on 2026-09-24 before the publication-block wording changed; kept for diffing. |
| `ppt_2026-05/` | April-May 2026 slide decks, PDF export and tech brief (`ppt/`) | Early presentations of the pipeline; superseded by the manuscript but useful as a record of the original framing. |
| `company_review_2026-06/` | `company-agent-templates/`, `company_review_packet_ko.md` | Local-only materials from June 2026. Local by design; never for the public repo. |
| `submission_bioRxiv_2026-09/` | bioRxiv draft PDFs of 2026-08-28 and 2026-09-03 (+ their README) | Superseded by the medRxiv submission after the SOP-strict re-implementation; kept as the record of what an earlier version claimed. |
| `manuscript_figures_2026-06/` | `F0`-`F5`, `F7` figure PNG/PDFs and `_f*.png` panel crops | The June 2026 figure set, replaced by `fig1`-`fig5` / `figS*` built by `make_figures.py`; no document references them any more. |

Created by `scripts/reorganize_repo.py` (plan: `notes/audits/2026-09-24/reorg_plan.json`).
"""

SUBMISSION_README = """\
# docs/manuscript/submission/

This folder holds only the actual medRxiv submission bundle. It is assembled on
2026-10-10, after the pre-submission gates pass
(`python -m scripts.verify_manuscript --online`, the number-traceability check,
and the scoop review). Until then it contains only this README.

Expected contents once assembled:

- the manuscript PDF with embedded figures;
- the supplementary PDF;
- a cover letter, if one is used.

The bundle itself is derived from `docs/manuscript/preprint.md` and the figure
builder and stays untracked (see `.gitignore`); only this README is tracked.
Earlier bioRxiv-era PDFs were moved to the local-only `archive/` folder.
"""


def default_spec() -> ReorgSpec:
    """Return the 2026-09-24 reorganisation plan."""
    m = "docs/manuscript"
    fig = f"{m}/figures"
    audits = "notes/audits/2026-09-24/"
    pub = "notes/publication/"
    moves = [
        # ROOT
        Move("CLAUDE.md.bak_20260924", "archive/backups/", "pre-edit snapshot"),
        Move("SUBMISSION_STEPS_LOCAL.md.bak_20260924", "archive/backups/",
             "pre-edit snapshot"),
        Move("NOTE_*.md", "notes/handoffs/", "root handoff notes"),
        Move("SUBMISSION_STEPS_LOCAL.md", pub, "local submission checklist"),
        Move("ppt/*", "archive/ppt_2026-05/", "old decks", cleanup_src_dir=True),
        # DOCS
        Move("docs/company-agent-templates/",
             "archive/company_review_2026-06/company-agent-templates/",
             "company review material"),
        Move("docs/company_review_packet_ko.md", "archive/company_review_2026-06/",
             "company review material"),
        Move("docs/HARNESS.md", "docs/harness/HARNESS.md", "harness map"),
        Move("docs/paper-harness-template/", "docs/harness/paper-harness-template/",
             "reusable harness template"),
        Move("docs/faithfulness.md", "docs/reference/", "reference doc"),
        Move("docs/vicc_rule_arm.md", "docs/reference/", "reference doc"),
        Move("docs/traceability_check.md", "docs/reference/", "reference doc"),
        Move("docs/RESOURCES.md", "docs/reference/", "resource manifest table"),
        Move("docs/talk_agent_skill_paperwriting_ko.md", "docs/talks/", "talk deck"),
        Move("docs/talk_agent_skill_paperwriting_ko.html", "docs/talks/", "talk deck"),
        Move("docs/study/", "docs/talks/study/", "study handouts"),
        # MANUSCRIPT
        Move(f"{m}/peer_review_2026-06-*.md", f"{m}/reviews/", "review records"),
        # Internal adversarial pre-submission review (local paths inside) stays local.
        Move(f"{m}/peer_review_2026-09-24.md", audits, "internal critic review"),
        *[Move(f"{m}/{n}", pub, "planning memo") for n in (
            "학회투고_계획_20260924.md", "발표처_원격_지원_국내_조사_20260924.md",
            "스쿱점검_보강제안_20260924.md", "논문화_실행계획_20260924.md",
            "공개저장소_준비_20260924.md", "abstract_GIW2026_LBA.md",
            "reference_search_prompt.md")],
        *[Move(f"{m}/{n}", audits, "audit memo") for n in (
            "재현성_산출물_점검_20260924.md", "SOP엄격구현_20260924.md",
            "OS2매핑_수정_20260924.md", "ClinVar홀드아웃_재구축_20260924.md",
            "related_work_verified_20260924.md", "related_work_verified_20260924.bib",
            "추가평가세트_조사_20260924.md", "원고보강_변경내역_20260924.md")],
        Move(f"{m}/working/*", audits, "working drafts", optional=True,
             cleanup_src_dir=True),
        Move(f"{m}/submission/superseded_20260924/*", "archive/submission_bioRxiv_2026-09/",
             "superseded bioRxiv PDFs", cleanup_src_dir=True),
        # FIGURES
        *[Move(f"{fig}/{g}", "archive/manuscript_figures_2026-06/", "legacy figure set")
          for g in ("F[0-5]_*.png", "F[0-5]_*.pdf", "F7_*.png", "F7_*.pdf", "_f*.png")],
        Move(f"{fig}/vicc_roc.png", f"{fig}/diagnostic/vicc_roc.png",
             "diagnostic ROC, not a manuscript figure"),
        # DATA
        Move("data/synthetic_sample.vcf", "data/examples/", "example input",
             report_refs=True),
        Move("data/run_ablation_supervised.sh", "scripts/", "run supervisor script",
             report_refs=True),
    ]
    renames = [
        Rename(f"{fig}/F6_dashboard.png", "figS3_dashboard.png",
               "Supplementary Figure S3 gets a figS* name like S1/S2/S4"),
    ]
    deletes = [
        Delete("LICENSE.txt", "identical_to:LICENSE", "duplicate of LICENSE"),
        Delete(".tmp_cc/", "empty_dir", "empty scratch dir"),
    ]
    path_rewrites = [
        PathRewrite("F6_dashboard.png", "figS3_dashboard.png", anchor="path",
                    note="rename; bare name is unique in the repo"),
        PathRewrite("figures/vicc_roc.png", "figures/diagnostic/vicc_roc.png",
                    note="relative mentions of the ROC figure"),
        PathRewrite(r'"figures",(\s*)"vicc_roc\.png"\)',
                    r'"figures",\1"diagnostic", "vicc_roc.png")', regex=True,
                    include=("scripts/run_horak_vicc.py",),
                    note="--roc-png default is built with os.path.join"),
    ]
    auto_rule_excludes = {
        # The template tells *another* team to create docs/HARNESS.md in its own repo.
        "docs/HARNESS.md": ("docs/paper-harness-template/*",),
    }
    gitignore_edits = [
        GitignoreEdit(
            "replace_line", old="docs/manuscript/submission/",
            lines=("docs/manuscript/submission/*",
                   "!docs/manuscript/submission/README.md"),
            note="bundle stays untracked; README explaining the folder is tracked"),
        GitignoreEdit("append_block", lines=(
            "",
            "# Repository reorganisation (2026-09-24, scripts/reorganize_repo.py).",
            "# archive/ holds superseded local material and is never published. The",
            "# old-location patterns above (ppt/, company review packet, NOTE_*.md,",
            "# SUBMISSION_STEPS_LOCAL.md, dated manuscript memos) are kept on purpose",
            "# so those files stay ignored if they are ever recreated at the old paths.",
            "archive/",
        ), note="archive is local only"),
    ]
    creates = [
        CreateFile("archive/README.md", ARCHIVE_README, "describes archive subfolders"),
        CreateFile(f"{m}/submission/README.md", SUBMISSION_README,
                   "states what the submission folder is for"),
    ]
    return ReorgSpec(
        moves=moves, renames=renames, deletes=deletes, delete_junk=True,
        path_rewrites=path_rewrites, auto_rule_excludes=auto_rule_excludes,
        gitignore_edits=gitignore_edits, creates=creates,
        must_be_ignored=("archive/", "notes/"),
        must_be_trackable=("docs/manuscript/reviews/", "docs/harness/",
                           "docs/reference/", "docs/talks/",
                           "docs/manuscript/figures/diagnostic/",
                           "docs/manuscript/submission/README.md"),
    )


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def nfc(s: str) -> str:
    """NFC-normalise (macOS may hand back NFD file names)."""
    return unicodedata.normalize("NFC", s)


def sha256_file(path: Path) -> str:
    """Streaming sha256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(root: Path, *args: str, stdin: Optional[bytes] = None,
        check: bool = True) -> subprocess.CompletedProcess:
    """Run git in ``root`` and return the completed process (bytes I/O)."""
    return subprocess.run(["git", "-C", str(root), *args], input=stdin,
                          capture_output=True, check=check)


def is_git_repo(root: Path) -> bool:
    """True if ``root`` is inside a git work tree."""
    r = git(root, "rev-parse", "--is-inside-work-tree", check=False)
    return r.returncode == 0 and r.stdout.strip() == b"true"


def tracked_files(root: Path) -> set[str]:
    """Repo-relative paths in the git index (NFC)."""
    if not is_git_repo(root):
        return set()
    out = git(root, "ls-files", "-z").stdout.decode("utf-8", "surrogateescape")
    return {nfc(p) for p in out.split("\0") if p}


def is_junk(rel: str) -> bool:
    """True for OS/bytecode clutter."""
    parts = rel.split("/")
    return parts[-1] in JUNK_FILE_NAMES or any(p in JUNK_DIR_NAMES for p in parts[:-1])


def walk_files(root: Path, exclude_top: Iterable[str]) -> list[str]:
    """All files under ``root`` (repo-relative, POSIX, NFC), skipping top dirs."""
    excl = set(exclude_top)
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            dirnames[:] = [d for d in dirnames if d not in excl]
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            rel = fn if rel_dir == "." else f"{rel_dir}/{fn}"
            out.append(nfc(rel.replace(os.sep, "/")))
    return sorted(out)


def walk_dirs(root: Path, exclude_top: Iterable[str]) -> set[str]:
    """All directories under ``root`` (repo-relative, NFC)."""
    excl = set(exclude_top)
    out: set[str] = set()
    for dirpath, dirnames, _ in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            dirnames[:] = [d for d in dirnames if d not in excl]
        else:
            out.add(nfc(rel_dir.replace(os.sep, "/")))
        dirnames[:] = [d for d in dirnames if d != ".git"]
    return out


def under(rel: str, prefix: str) -> bool:
    """True if ``rel`` equals ``prefix`` (a file) or lies under it (a dir)."""
    p = prefix.rstrip("/")
    return rel == p or rel.startswith(p + "/")


def glob_match(rel: str, patterns: Iterable[str]) -> bool:
    """fnmatch any (``*`` crosses ``/``)."""
    return any(fnmatch.fnmatchcase(rel, p) for p in patterns)


def manifest(root: Path, files: Iterable[str]) -> list[dict]:
    """[{path, size, sha256}] for existing files."""
    rows = []
    for rel in files:
        p = root / rel
        if p.is_file() and not p.is_symlink():
            rows.append({"path": rel, "size": p.stat().st_size, "sha256": sha256_file(p)})
    return rows


# --------------------------------------------------------------------------- #
# Plan data
# --------------------------------------------------------------------------- #
@dataclass
class FileOp:
    """One file-level move or rename."""

    kind: str          # "move" | "rename"
    src: str
    dst: str
    tracked: bool
    action: str        # "git mv" | "move+untrack" | "move"
    size: int
    sha256: str
    rule: str


@dataclass
class DeleteOp:
    """One delete (file or directory)."""

    path: str
    kind: str          # "file" | "dir"
    files: list[str]
    tracked_files: list[str]
    reason: str


@dataclass
class FileRewrite:
    """Planned text edits for one file."""

    path: str
    final_path: str
    sha256_before: str
    counts: dict[str, int]
    link_fixes: list[list[str]]
    new_text: str = field(repr=False, default="")


@dataclass
class Plan:
    """Everything the tool will do, plus diagnostics."""

    root: str
    created_at: str
    head: str
    ops: list[FileOp] = field(default_factory=list)
    dir_moves: list[list[str]] = field(default_factory=list)
    cleanup_dirs: list[str] = field(default_factory=list)
    deletes: list[DeleteOp] = field(default_factory=list)
    rewrites: list[FileRewrite] = field(default_factory=list)
    rules: list[dict] = field(default_factory=list)
    gitignore_before: str = ""
    gitignore_after: str = ""
    gitignore_changes: list[str] = field(default_factory=list)
    creates: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    skipped_optional: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    references: dict[str, dict] = field(default_factory=dict)
    local_only_refs: list[dict] = field(default_factory=list)
    status: dict = field(default_factory=dict)

    def mapping(self) -> dict[str, str]:
        """old file path -> new file path."""
        return {o.src: o.dst for o in self.ops}

    def deleted_files(self) -> set[str]:
        """Every file removed by a delete."""
        return {f for d in self.deletes for f in d.files}

    def to_json(self) -> dict:
        """Serialisable view (no rewritten file bodies)."""
        d = asdict(self)
        for r in d["rewrites"]:
            r.pop("new_text", None)
        return d


# --------------------------------------------------------------------------- #
# Plan construction
# --------------------------------------------------------------------------- #
def _expand_moves(root: Path, spec: ReorgSpec, plan: Plan, tracked: set[str],
                  all_files: list[str]) -> None:
    """Turn Move/Rename entries into per-file operations."""
    def add(kind: str, src: str, dst: str, rule: str) -> None:
        p = root / src
        is_tr = src in tracked
        local = any(under(dst, pre) for pre in LOCAL_ONLY_PREFIXES)
        action = ("move+untrack" if local else "git mv") if is_tr else "move"
        plan.ops.append(FileOp(kind, src, dst, is_tr, action, p.stat().st_size,
                               sha256_file(p), rule))

    for mv in spec.moves:
        rule = f"{mv.src} -> {mv.dst}"
        if any(ch in mv.src for ch in "*?["):
            matches = sorted(nfc(os.path.relpath(x, root).replace(os.sep, "/"))
                             for x in _glob.glob(str(root / mv.src)))
            files = [x for x in matches if (root / x).is_file() and not is_junk(x)]
            if not files:
                (plan.skipped_optional if mv.optional else plan.missing).append(mv.src)
                continue
            for f in files:
                add("move", f, posixpath.join(mv.dst.rstrip("/"), posixpath.basename(f)),
                    rule)
            if mv.cleanup_src_dir:
                plan.cleanup_dirs.append(posixpath.dirname(mv.src))
        elif mv.src.endswith("/"):
            sdir, ddir = mv.src.rstrip("/"), mv.dst.rstrip("/")
            if not (root / sdir).is_dir():
                (plan.skipped_optional if mv.optional else plan.missing).append(mv.src)
                continue
            files = [f for f in all_files if f.startswith(sdir + "/") and not is_junk(f)]
            for f in files:
                add("move", f, ddir + f[len(sdir):], rule)
            plan.dir_moves.append([sdir, ddir])
            plan.cleanup_dirs.append(sdir)
        else:
            if not (root / mv.src).is_file():
                (plan.skipped_optional if mv.optional else plan.missing).append(mv.src)
                continue
            dst = (posixpath.join(mv.dst.rstrip("/"), posixpath.basename(mv.src))
                   if mv.dst.endswith("/") else mv.dst)
            add("move", mv.src, dst, rule)
    for rn in spec.renames:
        if not (root / rn.src).is_file():
            plan.missing.append(rn.src)
            continue
        add("rename", rn.src, posixpath.join(posixpath.dirname(rn.src), rn.new_name),
            f"{rn.src} -> {rn.new_name}")


def _check_conflicts(root: Path, plan: Plan) -> None:
    """Refuse existing or colliding destinations and double-handled sources."""
    seen_dst: dict[str, str] = {}
    seen_src: set[str] = set()
    deleted = plan.deleted_files()
    for op in plan.ops:
        if op.src in seen_src:
            plan.conflicts.append(f"source handled twice: {op.src}")
        seen_src.add(op.src)
        if op.src in deleted:
            plan.conflicts.append(f"source is also deleted: {op.src}")
        if (root / op.dst).exists():
            plan.conflicts.append(f"destination exists (refusing to overwrite): {op.dst}")
        if op.dst in seen_dst:
            plan.conflicts.append(
                f"two sources map to {op.dst}: {seen_dst[op.dst]} and {op.src}")
        seen_dst[op.dst] = op.src
    for c in plan.creates:
        if (root / c["path"]).exists() or c["path"] in seen_dst:
            plan.conflicts.append(f"file to create already exists: {c['path']}")


def _expand_deletes(root: Path, spec: ReorgSpec, plan: Plan, tracked: set[str],
                    all_files: list[str]) -> None:
    """Resolve Delete entries and junk into DeleteOps (conditions evaluated)."""
    for d in spec.deletes:
        rel = d.path.rstrip("/")
        p = root / rel
        if not p.exists():
            plan.missing.append(d.path)
            continue
        if d.condition.startswith("identical_to:"):
            ref = d.condition.split(":", 1)[1]
            if not (root / ref).is_file() or sha256_file(root / ref) != sha256_file(p):
                plan.warnings.append(f"delete skipped, {rel} is not identical to {ref}")
                continue
            reason = f"sha256 identical to {ref}"
        elif d.condition == "empty_dir":
            if not p.is_dir() or any(p.iterdir()):
                plan.warnings.append(f"delete skipped, {rel} is not an empty directory")
                continue
            reason = "empty directory"
        else:
            reason = "listed"
        files = ([f for f in all_files if f.startswith(rel + "/")] if p.is_dir()
                 else [rel])
        plan.deletes.append(DeleteOp(rel, "dir" if p.is_dir() else "file", files,
                                     [f for f in files if f in tracked],
                                     f"{reason}; {d.note}".strip("; ")))
    if spec.delete_junk:
        junk_dirs: set[str] = set()
        for f in all_files:
            parts = f.split("/")
            for i, part in enumerate(parts[:-1]):
                if part in JUNK_DIR_NAMES:
                    junk_dirs.add("/".join(parts[:i + 1]))
                    break
        # also empty __pycache__ dirs
        for dpath in walk_dirs(root, WALK_EXCLUDE_TOP):
            if posixpath.basename(dpath) in JUNK_DIR_NAMES:
                if not any(under(dpath, j) and dpath != j for j in junk_dirs):
                    junk_dirs.add(dpath)
        junk_dirs = {j for j in junk_dirs
                     if not any(j != k and under(j, k) for k in junk_dirs)}
        for j in sorted(junk_dirs):
            files = [f for f in all_files if f.startswith(j + "/")]
            plan.deletes.append(DeleteOp(j, "dir", files, [f for f in files if f in tracked],
                                         "junk (__pycache__)"))
        for f in all_files:
            if posixpath.basename(f) in JUNK_FILE_NAMES and not any(
                    under(f, j) for j in junk_dirs):
                plan.deletes.append(DeleteOp(f, "file", [f], [f] if f in tracked else [],
                                             "junk (.DS_Store)"))


@dataclass
class _Rule:
    label: str
    #: (regex, replacement, is_regex_rule, literal needle for a cheap prefilter)
    patterns: list[tuple[re.Pattern, str, bool, str]]
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    new: str


_PRE_PATH = r"(?<![A-Za-z0-9_.\-])"
_PRE_ROOT = r"(?<![A-Za-z0-9_.\-/])"
_POST = r"(?![A-Za-z0-9_\-]|\.[A-Za-z0-9])"


def _literal_pattern(old: str, anchor: Anchor) -> re.Pattern:
    body = re.escape(old)
    if anchor == "none":
        return re.compile(body)
    return re.compile((_PRE_ROOT if anchor == "root" else _PRE_PATH) + body + _POST)


def _build_rules(spec: ReorgSpec, plan: Plan) -> list[_Rule]:
    """Auto rules from every move (files + moved dirs) plus the manual ones."""
    raw: list[PathRewrite] = []
    auto_seen: set[str] = set()
    for sdir, ddir in plan.dir_moves:
        raw.append(PathRewrite(sdir, ddir, anchor="path" if "/" in sdir else "root",
                               exclude=spec.auto_rule_excludes.get(sdir, ()),
                               note="auto: moved directory"))
        auto_seen.add(sdir)
    for op in plan.ops:
        if op.src in auto_seen:
            continue
        raw.append(PathRewrite(op.src, op.dst, anchor="path" if "/" in op.src else "root",
                               exclude=spec.auto_rule_excludes.get(op.src, ()),
                               note=f"auto: {op.kind}"))
        auto_seen.add(op.src)
    raw.extend(spec.path_rewrites)
    rules: list[_Rule] = []
    for r in raw:
        pats: list[tuple[re.Pattern, str, bool, str]] = []
        if r.regex:
            pats.append((re.compile(r.old), r.new, True, ""))
        else:
            variants = {(r.old, r.new)}
            nfd_old = unicodedata.normalize("NFD", r.old)
            if nfd_old != r.old:
                variants.add((nfd_old, r.new))
            esc_old = json.dumps(r.old)[1:-1]
            if esc_old != r.old:
                variants.add((esc_old, json.dumps(r.new)[1:-1]))
            for o, n in sorted(variants):
                pats.append((_literal_pattern(o, r.anchor), n, False, o))
            if not r.regex and r.anchor != "none" and _literal_pattern(
                    r.old, r.anchor).search(r.new):
                plan.warnings.append(
                    f"rule is not idempotent (old matches inside new): {r.old} -> {r.new}")
        rules.append(_Rule(r.old, pats, r.include, r.exclude, r.new))
        plan.rules.append({"old": r.old, "new": r.new, "anchor": r.anchor,
                           "regex": r.regex, "include": list(r.include),
                           "exclude": list(r.exclude), "note": r.note})
    return rules


_MD_LINK = re.compile(r'\]\(\s*<?([^()\s<>]+)>?(?:\s+"[^"]*")?\s*\)')
_HTML_ATTR = re.compile(r'\b(?:href|src)\s*=\s*"([^"]+)"')
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


@dataclass
class _Ctx:
    old_files: set[str]
    old_dirs: set[str]
    file_map: dict[str, str]
    dir_map: list[tuple[str, str]]
    deleted: set[str]

    def map(self, rel: str) -> Optional[str]:
        if rel in self.file_map:
            return self.file_map[rel]
        for s, d in self.dir_map:
            if rel == s or rel.startswith(s + "/"):
                return d + rel[len(s):]
        return None


def _fix_link(target: str, orig_rel: str, final_rel: str, ctx: _Ctx,
              warnings: list[str]) -> Optional[str]:
    """New relative link target, or None if unchanged / not a local link."""
    if _SCHEME.match(target) or target.startswith(("#", "/", "{", "$", "~")) \
            or "%" in target:
        return None
    cut = min([i for i in (target.find("#"), target.find("?")) if i >= 0],
              default=len(target))
    path, rest = target[:cut], target[cut:]
    if not path:
        return None
    resolved = nfc(posixpath.normpath(posixpath.join(posixpath.dirname(orig_rel), path)))
    if resolved.startswith("..") or resolved == ".":
        return None
    if resolved not in ctx.old_files and resolved not in ctx.old_dirs:
        return None
    if resolved in ctx.deleted:
        warnings.append(f"{orig_rel}: link to deleted file {resolved}")
        return None
    new_abs = ctx.map(resolved) or resolved
    new_rel = posixpath.relpath(new_abs, posixpath.dirname(final_rel) or ".")
    if path.endswith("/") and not new_rel.endswith("/"):
        new_rel += "/"
    if path.startswith("./") and not new_rel.startswith("."):
        new_rel = "./" + new_rel
    if new_rel == path:
        return None
    return new_rel + rest


def compute_edits(text: str, orig_rel: str, final_rel: str, rules: list[_Rule],
                  ctx: _Ctx, warnings: list[str]) -> tuple[str, dict[str, int],
                                                          list[list[str]]]:
    """Apply link repair + path rules in one non-overlapping pass."""
    edits: list[tuple[int, int, str, str]] = []
    link_fixes: list[list[str]] = []
    if posixpath.splitext(orig_rel)[1] in (".md", ".html", ".j2"):
        for rx in (_MD_LINK, _HTML_ATTR):
            for mt in rx.finditer(text):
                new = _fix_link(mt.group(1), orig_rel, final_rel, ctx, warnings)
                if new is not None:
                    edits.append((mt.start(1), mt.end(1), new, "link"))
                    link_fixes.append([mt.group(1), new])
    cands: list[tuple[int, int, str, str]] = []
    for rule in rules:
        if rule.include and not glob_match(orig_rel, rule.include):
            continue
        if rule.exclude and glob_match(orig_rel, rule.exclude):
            continue
        for rx, repl, is_rx, needle in rule.patterns:
            if needle and needle not in text:
                continue
            for mt in rx.finditer(text):
                cands.append((mt.start(), mt.end(), mt.expand(repl) if is_rx else repl,
                              rule.label))
    cands.sort(key=lambda c: (c[0], -(c[1] - c[0])))
    taken = sorted((s, e) for s, e, _, _ in edits)

    def overlaps(s: int, e: int) -> bool:
        return any(s < te and ts < e for ts, te in taken)

    for s, e, repl, label in cands:
        if not overlaps(s, e):
            edits.append((s, e, repl, label))
            taken.append((s, e))
    counts: dict[str, int] = {}
    out = text
    for s, e, repl, label in sorted(edits, key=lambda x: x[0], reverse=True):
        out = out[:s] + repl + out[e:]
        counts[label] = counts.get(label, 0) + 1
    return out, counts, link_fixes


def _plan_rewrites(root: Path, spec: ReorgSpec, plan: Plan, all_files: list[str],
                   rewrite_excludes: tuple[str, ...], plan_out_rel: str) -> None:
    """Scan text files and record the edits each would receive."""
    rules = _build_rules(spec, plan)
    ctx = _Ctx(set(all_files), walk_dirs(root, WALK_EXCLUDE_TOP), plan.mapping(),
               sorted(((s, d) for s, d in plan.dir_moves), key=lambda x: -len(x[0])),
               plan.deleted_files())
    deleted = plan.deleted_files()
    self_skip = set(SELF_FILES) | {plan_out_rel}
    for rel in all_files:
        if rel.split("/")[0] in REWRITE_EXCLUDE_TOP or rel in self_skip or rel in deleted:
            continue
        if posixpath.splitext(rel)[1].lower() not in TEXT_EXTS:
            continue
        final = ctx.map(rel) or rel
        if final.split("/")[0] in REWRITE_EXCLUDE_TOP:
            continue
        if rewrite_excludes and (glob_match(rel, rewrite_excludes)
                                 or glob_match(final, rewrite_excludes)):
            continue
        p = root / rel
        if p.stat().st_size > MAX_REWRITE_BYTES:
            plan.warnings.append(f"not scanned (>{MAX_REWRITE_BYTES} bytes): {rel}")
            continue
        raw = p.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            plan.warnings.append(f"not scanned (not UTF-8): {rel}")
            continue
        new, counts, links = compute_edits(text, rel, final, rules, ctx, plan.warnings)
        if new != text:
            plan.rewrites.append(FileRewrite(rel, final, hashlib.sha256(raw).hexdigest(),
                                             counts, links, new))


def _plan_gitignore(root: Path, spec: ReorgSpec, plan: Plan) -> None:
    """Compute the edited .gitignore text."""
    gi = root / ".gitignore"
    before = gi.read_text(encoding="utf-8") if gi.exists() else ""
    lines = before.splitlines()
    for ed in spec.gitignore_edits:
        if ed.op == "replace_line":
            idx = [i for i, ln in enumerate(lines) if ln == ed.old]
            if not idx:
                plan.warnings.append(f".gitignore: line not found, not replaced: {ed.old!r}")
                continue
            i = idx[0]
            lines[i:i + 1] = list(ed.lines)
            plan.gitignore_changes.append(f"replace {ed.old!r} -> {list(ed.lines)!r}")
        elif ed.op == "append_block":
            payload = [ln for ln in ed.lines if ln and not ln.startswith("#")]
            if all(ln in lines for ln in payload):
                plan.gitignore_changes.append(f"already present: {payload!r}")
                continue
            lines.extend(ed.lines)
            plan.gitignore_changes.append(f"append {payload!r}")
    after = "\n".join(lines) + ("\n" if lines else "")
    plan.gitignore_before, plan.gitignore_after = before, after


def _plan_references(root: Path, spec: ReorgSpec, plan: Plan, all_files: list[str]) -> None:
    """Reference counts for moves flagged report_refs and for deletes."""
    targets: list[tuple[str, str]] = []
    flagged = {mv.src for mv in spec.moves if mv.report_refs}
    for op in plan.ops:
        if op.src in flagged:
            targets.append((op.src, "move"))
    for d in plan.deletes:
        if not d.reason.startswith("junk"):
            targets.append((d.path, "delete"))
    if not targets:
        return
    texts: dict[str, str] = {}
    for rel in all_files:
        if rel.split("/")[0] in ("venv", ".git") or rel in SELF_FILES:
            continue
        if posixpath.splitext(rel)[1].lower() not in TEXT_EXTS:
            continue
        try:
            if (root / rel).stat().st_size <= MAX_REWRITE_BYTES:
                texts[rel] = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    for path, kind in targets:
        base = posixpath.basename(path)
        full_rx, base_rx = _literal_pattern(path, "path"), _literal_pattern(base, "path")
        hits = {}
        for rel, t in texts.items():
            nf, nb = len(full_rx.findall(t)), len(base_rx.findall(t))
            if nf or nb:
                hits[rel] = {"full_path": nf, "basename": nb}
        plan.references[path] = {"kind": kind, "files": hits}


_LOCAL_REF = re.compile(r"(?<![A-Za-z0-9_.\-])(?:\.\./)*(?:archive|notes)/[^\s)\"'`<>\]]+")


def _flag_local_only_refs(plan: Plan, status_after: dict[str, str]) -> None:
    """Publishable files whose rewrite *introduces* a pointer into archive/ or notes/."""
    root = Path(plan.root)
    for rw in plan.rewrites:
        st = status_after.get(rw.final_path, "untracked")
        if st == "ignored" or any(under(rw.final_path, p) for p in LOCAL_ONLY_PREFIXES):
            continue
        old = set(_LOCAL_REF.findall((root / rw.path).read_text(encoding="utf-8")))
        hits = sorted(set(_LOCAL_REF.findall(rw.new_text)) - old)
        if hits:
            plan.local_only_refs.append({"file": rw.final_path, "status_after": st,
                                         "targets": hits})


# --------------------------------------------------------------------------- #
# git-status simulation
# --------------------------------------------------------------------------- #
def simulate_status(root: Path, gitignore_text: str, paths: Iterable[str],
                    tracked: set[str], nested_ignores: dict[str, bytes]) -> dict[str, str]:
    """State of each path under a given .gitignore, via a sandbox repo.

    Every path becomes an empty placeholder file; ``tracked`` paths are force-
    added to the sandbox index; nested ``.gitignore`` files get their real
    content; ``.git/info/exclude`` is copied. ``git status --porcelain
    --ignored=traditional --untracked-files=all`` then classifies each file as
    ``tracked`` / ``untracked`` / ``ignored`` with git's own negation semantics.
    """
    paths = sorted(set(paths))
    with tempfile.TemporaryDirectory(prefix="reorg_sim_") as tmp:
        sb = Path(tmp)
        subprocess.run(["git", "init", "-q", str(sb)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(sb), "config", "core.precomposeunicode", "true"],
                       check=True, capture_output=True)
        excl = root / ".git" / "info" / "exclude"
        if excl.is_file():
            (sb / ".git" / "info").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(excl, sb / ".git" / "info" / "exclude")
        (sb / ".gitignore").write_text(gitignore_text, encoding="utf-8")
        for rel in paths:
            if rel == ".gitignore":
                continue
            p = sb / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(nested_ignores.get(rel, b""))
        to_add = [p for p in paths if p in tracked]
        if to_add:
            # update-index works on git < 2.25 (no --pathspec-from-file) and,
            # like `add -f`, does not consult .gitignore.
            subprocess.run(["git", "-C", str(sb), "update-index", "--add", "-z", "--stdin"],
                           input=("\0".join(to_add) + "\0").encode("utf-8"), check=True,
                           capture_output=True)
        out = subprocess.run(["git", "-C", str(sb), "status", "--porcelain=v1", "-z",
                              "--ignored=traditional", "--untracked-files=all"],
                             check=True, capture_output=True).stdout.decode("utf-8")
    state: dict[str, str] = {}
    for ent in out.split("\0"):
        if len(ent) < 4:
            continue
        xy, rel = ent[:2], nfc(ent[3:])
        state[rel] = {"??": "untracked", "!!": "ignored"}.get(xy, "tracked")
    return {p: state.get(p, "tracked" if p in tracked else "unknown") for p in paths}


def real_status(root: Path) -> dict[str, str]:
    """Real repo state (outside venv/), same porcelain semantics."""
    out = git(root, "status", "--porcelain=v1", "-z", "--ignored=traditional",
              "--untracked-files=all", "--", ".", ":(exclude)venv").stdout.decode("utf-8")
    st: dict[str, str] = {}
    ents = out.split("\0")
    i = 0
    while i < len(ents):
        ent = ents[i]
        i += 1
        if len(ent) < 4:
            continue
        xy, rel = ent[:2], nfc(ent[3:])
        if xy[0] in "RC":
            i += 1
        st[rel] = {"??": "untracked", "!!": "ignored"}.get(xy, "tracked")
    return st


def _plan_status(root: Path, spec: ReorgSpec, plan: Plan, all_walk: list[str],
                 tracked: set[str]) -> dict[str, str]:
    """Before/after status simulation and the resulting transitions."""
    mapping = plan.mapping()
    deleted = plan.deleted_files()
    untracked_by_policy = {o.src for o in plan.ops if o.action == "move+untrack"}
    nested_before = {p: (root / p).read_bytes() for p in all_walk
                     if posixpath.basename(p) == ".gitignore" and p != ".gitignore"}
    before = simulate_status(root, plan.gitignore_before, all_walk, tracked, nested_before)
    after_paths: list[str] = []
    after_tracked: set[str] = set()
    src_of: dict[str, str] = {}
    for p in all_walk:
        if p in deleted:
            continue
        q = mapping.get(p, p)
        after_paths.append(q)
        src_of[q] = p
        if p in tracked and p not in untracked_by_policy:
            after_tracked.add(q)
    created = [c["path"] for c in plan.creates]
    after_paths.extend(created)
    nested_after = {mapping.get(p, p): b for p, b in nested_before.items()}
    after = simulate_status(root, plan.gitignore_after, after_paths, after_tracked,
                            nested_after)
    trans: dict[str, list[dict]] = {}
    for q, s1 in after.items():
        p = src_of.get(q)
        s0 = before.get(p, "absent") if p else "absent"
        if s0 != s1 or p != q:
            key = f"{s0} -> {s1}"
            trans.setdefault(key, []).append({"from": p, "to": q})
    for p in sorted(deleted):
        trans.setdefault(f"{before.get(p, '?')} -> deleted", []).append({"from": p, "to": None})
    newly_trackable = [t for k, v in trans.items() for t in v
                       if k.endswith("-> untracked") and not k.startswith("untracked")]
    newly_ignored = [t for k, v in trans.items() for t in v
                     if k.endswith("-> ignored") and not k.startswith("ignored")]
    violations = []
    for q, s1 in after.items():
        if any(under(q, pre) for pre in spec.must_be_ignored) and s1 != "ignored":
            violations.append(f"should be ignored but is {s1}: {q}")
        if any(under(q, pre) for pre in spec.must_be_trackable) and s1 == "ignored":
            violations.append(f"should be trackable but is ignored: {q}")
    # sanity: simulation vs the real repository for the before state
    mism = []
    if is_git_repo(root):
        real = real_status(root)
        for p, s in before.items():
            r = real.get(p, "tracked" if p in tracked else None)
            if r is not None and r != s:
                mism.append(f"{p}: simulated {s}, real {r}")
    plan.status = {
        "summary": {k: len(v) for k, v in sorted(trans.items())},
        "transitions": {k: v for k, v in sorted(trans.items())},
        "newly_trackable": newly_trackable,
        "newly_ignored": newly_ignored,
        "violations": violations,
        "simulation_vs_real_mismatches": mism,
    }
    return after


def build_plan(root: Path, spec: ReorgSpec, rewrite_excludes: tuple[str, ...] = (),
               plan_out_rel: str = DEFAULT_PLAN_OUT, status_sim: bool = True) -> Plan:
    """Compute the full plan without changing anything."""
    root = root.resolve()
    head = ""
    if is_git_repo(root):
        head = git(root, "rev-parse", "HEAD", check=False).stdout.decode().strip()
    plan = Plan(str(root), _dt.datetime.now().isoformat(timespec="seconds"), head)
    tracked = tracked_files(root)
    all_walk = walk_files(root, WALK_EXCLUDE_TOP)
    plan.creates = [{"path": c.path, "bytes": len(c.content.encode()), "note": c.note}
                    for c in spec.creates]
    _expand_deletes(root, spec, plan, tracked, all_walk)
    _expand_moves(root, spec, plan, tracked, all_walk)
    _check_conflicts(root, plan)
    _plan_rewrites(root, spec, plan, all_walk, rewrite_excludes, plan_out_rel)
    _plan_gitignore(root, spec, plan)
    _plan_references(root, spec, plan, all_walk)
    if status_sim and shutil.which("git"):
        after = _plan_status(root, spec, plan, all_walk, tracked)
        _flag_local_only_refs(plan, after)
    return plan


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def counts(plan: Plan) -> dict[str, int]:
    """Headline counts per category."""
    junk = [d for d in plan.deletes if d.reason.startswith("junk")]
    return {
        "moves": sum(o.kind == "move" for o in plan.ops),
        "renames": sum(o.kind == "rename" for o in plan.ops),
        "git_mv": sum(o.action == "git mv" for o in plan.ops),
        "move_untrack": sum(o.action == "move+untrack" for o in plan.ops),
        "plain_move": sum(o.action == "move" for o in plan.ops),
        "deletes_listed": len(plan.deletes) - len(junk),
        "deletes_junk_items": len(junk),
        "deleted_files": len(plan.deleted_files()),
        "rewritten_files": len(plan.rewrites),
        "rewrite_occurrences": sum(sum(r.counts.values()) for r in plan.rewrites),
        "link_fixes": sum(len(r.link_fixes) for r in plan.rewrites),
        "creates": len(plan.creates),
        "missing": len(plan.missing),
        "conflicts": len(plan.conflicts),
        "warnings": len(plan.warnings),
    }


def print_diffs(plan: Plan, out=sys.stdout) -> None:
    """Unified diff (changed lines only, no context) of every planned rewrite."""
    root = Path(plan.root)
    for r in plan.rewrites:
        old = (root / r.path).read_text(encoding="utf-8").splitlines(keepends=True)
        new = r.new_text.splitlines(keepends=True)
        for line in difflib.unified_diff(old, new, f"a/{r.path}", f"b/{r.final_path}", n=0):
            out.write(line if line.endswith("\n") else line + "\n")


def print_plan(plan: Plan, out=sys.stdout) -> None:
    """Human-readable full plan."""
    w = lambda s="": print(s, file=out)  # noqa: E731
    w(f"# Reorganisation plan for {plan.root} (HEAD {plan.head[:10]})")
    w(f"## Moves / renames ({len(plan.ops)})")
    for o in plan.ops:
        w(f"  [{o.action:12}] {o.kind:6} {o.src} -> {o.dst}")
    if plan.cleanup_dirs:
        w(f"## Source directories removed if empty ({len(plan.cleanup_dirs)})")
        for d in plan.cleanup_dirs:
            w(f"  {d}/")
    w(f"## Deletes ({len(plan.deletes)} items, {len(plan.deleted_files())} files)")
    for d in plan.deletes:
        tr = f", {len(d.tracked_files)} tracked" if d.tracked_files else ""
        w(f"  {d.kind:4} {d.path}  ({len(d.files)} files{tr}; {d.reason})")
    w(f"## Rewrites ({len(plan.rewrites)} files)")
    for r in plan.rewrites:
        loc = r.path if r.path == r.final_path else f"{r.path} (-> {r.final_path})"
        w(f"  {loc}: {sum(r.counts.values())} occurrence(s)")
        for k, v in sorted(r.counts.items()):
            w(f"      {v:3} x {k}")
        for old, new in r.link_fixes:
            w(f"      link: {old} -> {new}")
    w("## .gitignore")
    for c in plan.gitignore_changes:
        w(f"  {c}")
    w(f"## Creates ({len(plan.creates)})")
    for c in plan.creates:
        w(f"  {c['path']} ({c['bytes']} bytes)")
    if plan.references:
        w("## Reference check")
        for p, info in plan.references.items():
            w(f"  {info['kind']} {p}: {len(info['files'])} file(s) mention it")
            for f, n in info["files"].items():
                w(f"      {f}: full path {n['full_path']}, basename {n['basename']}")
    if plan.status:
        w("## git-status simulation (before -> after)")
        for k, v in plan.status["summary"].items():
            w(f"  {v:4}  {k}")
        for label in ("newly_trackable", "newly_ignored"):
            items = plan.status[label]
            w(f"  {label}: {len(items)}")
            for t in items:
                w(f"      {t['from']} -> {t['to']}")
        w(f"  violations: {len(plan.status['violations'])}")
        for v in plan.status["violations"]:
            w(f"      {v}")
        w(f"  simulation vs real mismatches: "
          f"{len(plan.status['simulation_vs_real_mismatches'])}")
        for v in plan.status["simulation_vs_real_mismatches"][:20]:
            w(f"      {v}")
    if plan.local_only_refs:
        w("## Publishable files that would reference archive/ or notes/")
        for x in plan.local_only_refs:
            w(f"  {x['file']} ({x['status_after']}): {', '.join(x['targets'])}")
    for label, items in (("Missing sources", plan.missing),
                         ("Skipped optional (absent)", plan.skipped_optional),
                         ("Conflicts", plan.conflicts), ("Warnings", plan.warnings)):
        w(f"## {label} ({len(items)})")
        for i in items:
            w(f"  {i}")
    w("## Counts")
    for k, v in counts(plan).items():
        w(f"  {k}: {v}")


# --------------------------------------------------------------------------- #
# Apply
# --------------------------------------------------------------------------- #
class ReorgError(RuntimeError):
    """Raised when the plan cannot be applied safely."""


def _atomic_write(path: Path, text: str) -> None:
    mode = path.stat().st_mode if path.exists() else None
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.reorg_")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, path)


def apply_plan(root: Path, spec: ReorgSpec, plan: Plan, backup_root: Path,
               allow_missing: bool = False, out=sys.stdout) -> dict:
    """Execute ``plan``; returns the results dict. Raises ReorgError on refusal."""
    root = root.resolve()
    if plan.conflicts:
        raise ReorgError(f"{len(plan.conflicts)} conflict(s); nothing changed")
    if plan.missing and not allow_missing:
        raise ReorgError(f"{len(plan.missing)} missing source(s); nothing changed "
                         "(use --allow-missing to proceed with the rest)")
    git_ok = is_git_repo(root)
    if any(o.action != "move" for o in plan.ops) and not git_ok:
        raise ReorgError("tracked-file operations need a git repository")
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    bdir = backup_root / ts
    if bdir.exists():
        raise ReorgError(f"backup dir exists: {bdir}")
    (bdir / "files").mkdir(parents=True)

    # 1. backup + manifest_before
    affected = {o.src for o in plan.ops} | plan.deleted_files() | \
        {r.path for r in plan.rewrites} | {".gitignore"}
    affected = {a for a in affected if (root / a).is_file()}
    for rel in sorted(affected):
        dst = bdir / "files" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dst)
        if sha256_file(dst) != sha256_file(root / rel):
            raise ReorgError(f"backup copy hash mismatch: {rel}; nothing changed")
    walk_before = walk_files(root, WALK_EXCLUDE_TOP)
    man_before = manifest(root, walk_before)
    (bdir / "manifest_before.json").write_text(json.dumps(man_before, indent=1,
                                                          ensure_ascii=False))
    sha_before = {r["path"]: r["sha256"] for r in man_before}

    # 2. deletes
    deleted_files: list[str] = []
    for d in plan.deletes:
        for f in d.tracked_files:
            git(root, "--literal-pathspecs", "rm", "--cached", "-q", "--", f)
        p = root / d.path
        if d.kind == "dir" and p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
        deleted_files.extend(d.files)

    # 3. moves / renames, hash-verified immediately
    moved_ok = 0
    for o in plan.ops:
        src, dst = root / o.src, root / o.dst
        if dst.exists():
            raise ReorgError(f"destination appeared during apply: {o.dst} "
                             f"(backup: {bdir})")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if o.action == "git mv":
            git(root, "mv", "--", o.src, o.dst)
        else:
            os.replace(src, dst)
            if o.action == "move+untrack":
                git(root, "--literal-pathspecs", "rm", "--cached", "-q", "--", o.src)
        if sha256_file(dst) != o.sha256:
            raise ReorgError(f"sha256 changed while moving {o.src} (backup: {bdir})")
        moved_ok += 1
    for d in sorted(set(plan.cleanup_dirs), key=len, reverse=True):
        p = root / d
        if p.is_dir():
            for sub, _dirs, _files in sorted(os.walk(p), key=lambda x: -len(x[0])):
                try:
                    os.rmdir(sub)
                except OSError:
                    pass

    # 4. rewrites (guarded by the plan-time hash)
    rewritten, skipped = [], []
    for r in plan.rewrites:
        p = root / r.final_path
        if sha256_file(p) != r.sha256_before:
            skipped.append(r.final_path)
            continue
        _atomic_write(p, r.new_text)
        rewritten.append(r.final_path)

    # 5. .gitignore and creates
    if plan.gitignore_after != plan.gitignore_before:
        _atomic_write(root / ".gitignore", plan.gitignore_after)
    created = []
    for c in spec.creates:
        p = root / c.path
        if p.exists():
            raise ReorgError(f"refusing to overwrite {c.path} (backup: {bdir})")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(c.content, encoding="utf-8")
        created.append(c.path)

    # 6. verification
    walk_after = walk_files(root, WALK_EXCLUDE_TOP)
    man_after = manifest(root, walk_after)
    (bdir / "manifest_after.json").write_text(json.dumps(man_after, indent=1,
                                                         ensure_ascii=False))
    sha_after = {r["path"]: r["sha256"] for r in man_after}
    mapping = plan.mapping()
    rewritten_set = set(rewritten) | {".gitignore"}
    lost, hash_changed = [], []
    for rel in sha_before:
        if rel in deleted_files:
            continue
        q = mapping.get(rel, rel)
        if q not in sha_after:
            lost.append(rel)
        elif rel in mapping and q not in rewritten_set and sha_after[q] != sha_before[rel]:
            hash_changed.append(rel)
    expected = len(man_before) - len(set(deleted_files)) + len(created)
    res = {
        "backup_dir": str(bdir),
        "moved": moved_ok,
        "rewritten": len(rewritten),
        "rewrite_skipped_changed_since_plan": skipped,
        "deleted_files": len(set(deleted_files)),
        "created": created,
        "files_before": len(man_before),
        "files_after": len(man_after),
        "files_expected_after": expected,
        "count_ok": len(man_after) == expected,
        "lost": lost,
        "moved_hash_changed": hash_changed,
    }
    print(f"{moved_ok} moved, {len(rewritten)} rewritten, {len(set(deleted_files))} "
          f"deleted, {len(lost)} lost (files {len(man_before)} -> {len(man_after)}, "
          f"expected {expected}; backup {bdir})", file=out)
    if skipped:
        print(f"[!] {len(skipped)} rewrite(s) skipped, file changed since plan: {skipped}",
              file=out)
    if lost or hash_changed or not res["count_ok"]:
        print("[!] VERIFICATION FAILED, restore from the backup directory", file=out)
    return res


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def write_plan_json(root: Path, plan: Plan, plan_out: str, mode: str,
                    results: Optional[dict] = None) -> Path:
    """Write the plan (and results) JSON."""
    path = Path(plan_out)
    if not path.is_absolute():
        path = root / plan_out
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"tool": "scripts/reorganize_repo.py", "mode": mode, "counts": counts(plan),
           "plan": plan.to_json(), "results": results}
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main(argv: Optional[list[str]] = None, spec: Optional[ReorgSpec] = None) -> int:
    """Entry point. Returns a process exit code."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="perform the plan (default: dry run)")
    ap.add_argument("--allow-missing", action="store_true",
                    help="apply the rest of the plan even if some sources are missing")
    ap.add_argument("--root", default=str(REPO_ROOT), help="repository root")
    ap.add_argument("--backup-root", default=str(DEFAULT_BACKUP_ROOT))
    ap.add_argument("--plan-out", default=DEFAULT_PLAN_OUT,
                    help="plan/results JSON (relative to --root unless absolute)")
    ap.add_argument("--rewrite-exclude", action="append", default=[],
                    help="fnmatch glob of files to leave unrewritten (repeatable)")
    ap.add_argument("--skip-status-sim", action="store_true",
                    help="skip the git-status simulation")
    ap.add_argument("--diff", action="store_true",
                    help="also print a unified diff of every planned rewrite")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    spec = spec or default_spec()
    plan_out_rel = args.plan_out
    if Path(plan_out_rel).is_absolute():
        try:
            plan_out_rel = str(Path(plan_out_rel).resolve().relative_to(root))
        except ValueError:
            pass
    plan = build_plan(root, spec, tuple(args.rewrite_exclude), plan_out_rel,
                      status_sim=not args.skip_status_sim)
    print_plan(plan)
    if args.diff:
        print("## Rewrite diffs")
        print_diffs(plan)
    if not args.apply:
        p = write_plan_json(root, plan, args.plan_out, "dry-run")
        print(f"\nDRY RUN: nothing changed. Plan written to {p}")
        blocking = bool(plan.conflicts) or (bool(plan.missing) and not args.allow_missing)
        if blocking:
            print("[!] --apply would refuse: resolve conflicts/missing sources first "
                  "(or pass --allow-missing for missing ones)")
        return 0
    try:
        results = apply_plan(root, spec, plan, Path(args.backup_root), args.allow_missing)
    except ReorgError as exc:
        print(f"[refused] {exc}")
        write_plan_json(root, plan, args.plan_out, "apply-refused", {"error": str(exc)})
        return 2
    p = write_plan_json(root, plan, args.plan_out, "apply", results)
    print(f"Plan + results written to {p}")
    ok = results["count_ok"] and not results["lost"] and not results["moved_hash_changed"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
