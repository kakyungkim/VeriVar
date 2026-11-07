"""Tests for scripts/reorganize_repo.py on a throw-away git fixture repository."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts import reorganize_repo as rr

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git not available")

GITIGNORE = """\
.DS_Store
LOCAL.md
private/
ppt/
"""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout


def _write(root: Path, rel: str, content: str | bytes) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")


def _snapshot(root: Path) -> dict[str, str]:
    """path -> sha256 of every file outside .git."""
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and ".git" not in p.parts}


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _write(root, ".gitignore", GITIGNORE)
    _write(root, "LICENSE", "MIT\n")
    _write(root, "LICENSE.txt", "MIT\n")
    _write(root, "COPY.txt", "different\n")
    _write(root, "CLAUDE.md",
           "Map: **[docs/HARNESS.md](docs/HARNESS.md)**. See `LOCAL.md`.\n"
           "Keep `LOCAL.md.bak` as is. 한국어: docs/HARNESS.md를 본다.\n")
    _write(root, "docs/HARNESS.md", "# Harness\nBack to [CLAUDE](../CLAUDE.md).\n")
    _write(root, "docs/template/README.md", "Create `docs/HARNESS.md` in your repo.\n")
    _write(root, "docs/old/a.md", "see [b](b.md) and [top](../HARNESS.md)\n")
    _write(root, "docs/old/b.md", "b\n")
    _write(root, "figs/F6.png", b"\x89PNG-binary-\x00\x01")
    _write(root, "figs/legacy.png", b"legacy-bytes")
    _write(root, "paper.md", "![dash](figs/F6.png) and figs/F6.png\n")
    _write(root, "scripts/run.py", 'OUT = "docs/HARNESS.md"\n')
    _write(root, "data.json", json.dumps({"p": "docs/HARNESS.md"}) + "\n")
    _write(root, "LOCAL.md", "local only, see docs/HARNESS.md\n")        # ignored
    _write(root, "private/keep.txt", "private\n")                        # ignored
    _write(root, "ppt/deck.pptx", b"deck")                               # ignored
    _write(root, "docs/.DS_Store", b"junk")
    _write(root, "pkg/__pycache__/m.cpython-311.pyc", b"pyc")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-q",
         "-m", "fixture")
    return root


def _spec() -> rr.ReorgSpec:
    return rr.ReorgSpec(
        moves=[
            rr.Move("docs/HARNESS.md", "docs/harness/HARNESS.md"),
            rr.Move("docs/old/", "docs/new/"),
            rr.Move("LOCAL.md", "notes/publication/"),
            rr.Move("ppt/*", "archive/ppt/", cleanup_src_dir=True),
            rr.Move("figs/legacy.png", "archive/figs/"),
            rr.Move("private/keep.txt", "shared/"),
            rr.Move("docs/working/*", "notes/", optional=True),
        ],
        renames=[rr.Rename("figs/F6.png", "figS3.png")],
        deletes=[rr.Delete("LICENSE.txt", "identical_to:LICENSE"),
                 rr.Delete("COPY.txt", "identical_to:LICENSE")],
        path_rewrites=[rr.PathRewrite("F6.png", "figS3.png")],
        auto_rule_excludes={"docs/HARNESS.md": ("docs/template/*",)},
        gitignore_edits=[rr.GitignoreEdit("append_block", lines=("archive/", "notes/"))],
        creates=[rr.CreateFile("archive/README.md", "archive\n")],
        must_be_ignored=("archive/", "notes/"),
        must_be_trackable=("docs/harness/",),
    )


def _run(repo: Path, tmp_path: Path, *extra: str, spec: rr.ReorgSpec | None = None) -> int:
    return rr.main(["--root", str(repo), "--backup-root", str(tmp_path / "bak"),
                    "--plan-out", str(tmp_path / "plan.json"), *extra],
                   spec=spec or _spec())


def test_dry_run_changes_nothing(repo: Path, tmp_path: Path) -> None:
    before, status = _snapshot(repo), _git(repo, "status", "--porcelain", "--ignored")
    assert _run(repo, tmp_path) == 0
    assert _snapshot(repo) == before
    assert _git(repo, "status", "--porcelain", "--ignored") == status
    doc = json.loads((tmp_path / "plan.json").read_text())
    assert doc["mode"] == "dry-run" and doc["results"] is None
    assert doc["plan"]["skipped_optional"] == ["docs/working/*"]
    assert doc["plan"]["missing"] == []


def test_plan_contents(repo: Path) -> None:
    plan = rr.build_plan(repo, _spec(), plan_out_rel="none.json")
    actions = {o.src: o.action for o in plan.ops}
    assert actions["docs/HARNESS.md"] == "git mv"
    assert actions["figs/legacy.png"] == "move+untrack"     # tracked -> archive/
    assert actions["LOCAL.md"] == "move"                    # ignored file
    assert actions["figs/F6.png"] == "git mv"
    deleted = {d.path for d in plan.deletes}
    assert "LICENSE.txt" in deleted and "COPY.txt" not in deleted
    assert any("COPY.txt is not identical" in w for w in plan.warnings)
    assert {"docs/.DS_Store", "pkg/__pycache__"} <= deleted
    # status simulation: ignored private file moved to a trackable place
    newly = {t["to"] for t in plan.status["newly_trackable"]}
    assert "shared/keep.txt" in newly
    assert plan.status["violations"] == []
    assert plan.status["simulation_vs_real_mismatches"] == []


def test_apply_moves_renames_rewrites(repo: Path, tmp_path: Path) -> None:
    before = _snapshot(repo)
    assert _run(repo, tmp_path, "--apply") == 0
    doc = json.loads((tmp_path / "plan.json").read_text())
    res = doc["results"]
    assert res["count_ok"] and res["lost"] == [] and res["moved_hash_changed"] == []

    # moves and renames, bytes preserved
    assert not (repo / "docs/HARNESS.md").exists()
    assert (repo / "figs/figS3.png").read_bytes() == b"\x89PNG-binary-\x00\x01"
    assert (repo / "docs/new/b.md").exists() and not (repo / "docs/old").exists()
    assert (repo / "archive/ppt/deck.pptx").exists() and not (repo / "ppt").exists()
    assert (repo / "notes/publication/LOCAL.md").exists()
    # git: history-preserving rename for tracked files, untrack for archive
    staged = _git(repo, "diff", "--cached", "--name-status", "-M")
    assert "docs/HARNESS.md\tdocs/harness/HARNESS.md" in staged
    assert "figs/F6.png\tfigs/figS3.png" in staged
    assert "D\tfigs/legacy.png" in staged
    assert "D\tLICENSE.txt" in staged
    assert "archive/figs/legacy.png" not in _git(repo, "ls-files")

    # rewrites: path rules, Korean particle, boundary, scoped exclude, JSON, links
    claude = (repo / "CLAUDE.md").read_text()
    assert "[docs/harness/HARNESS.md](docs/harness/HARNESS.md)" in claude
    assert "docs/harness/HARNESS.md를" in claude
    assert "`notes/publication/LOCAL.md`" in claude
    assert "`LOCAL.md.bak`" in claude                               # not a match
    assert (repo / "docs/template/README.md").read_text() == \
        "Create `docs/HARNESS.md` in your repo.\n"                   # excluded
    assert (repo / "scripts/run.py").read_text() == 'OUT = "docs/harness/HARNESS.md"\n'
    assert json.loads((repo / "data.json").read_text())["p"] == "docs/harness/HARNESS.md"
    assert (repo / "paper.md").read_text() == "![dash](figs/figS3.png) and figs/figS3.png\n"
    assert "(../../CLAUDE.md)" in (repo / "docs/harness/HARNESS.md").read_text()
    a = (repo / "docs/new/a.md").read_text()
    assert "[b](b.md)" in a and "[top](../harness/HARNESS.md)" in a

    # deletes, junk, gitignore, creates
    assert not (repo / "LICENSE.txt").exists() and (repo / "COPY.txt").exists()
    assert not (repo / "docs/.DS_Store").exists()
    assert not (repo / "pkg/__pycache__").exists()
    assert "archive/" in (repo / ".gitignore").read_text().splitlines()
    assert (repo / "archive/README.md").read_text() == "archive\n"

    # backup: every affected file copied byte-identically + manifests
    bdir = Path(res["backup_dir"])
    assert (bdir / "manifest_before.json").exists() and (bdir / "manifest_after.json").exists()
    for rel in ("CLAUDE.md", "docs/HARNESS.md", "figs/F6.png", "LICENSE.txt", ".gitignore"):
        got = hashlib.sha256((bdir / "files" / rel).read_bytes()).hexdigest()
        assert got == before[rel]
    man = {r["path"]: r["sha256"] for r in
           json.loads((bdir / "manifest_before.json").read_text())}
    assert man["figs/F6.png"] == before["figs/F6.png"]


def test_refuses_overwrite(repo: Path, tmp_path: Path) -> None:
    _write(repo, "docs/harness/HARNESS.md", "already here\n")
    before = _snapshot(repo)
    assert _run(repo, tmp_path, "--apply") == 2
    assert _snapshot(repo) == before
    doc = json.loads((tmp_path / "plan.json").read_text())
    assert doc["mode"] == "apply-refused"
    assert any("refusing to overwrite" in c for c in doc["plan"]["conflicts"])


def test_missing_source_requires_allow_missing(repo: Path, tmp_path: Path) -> None:
    spec = _spec()
    spec.moves.append(rr.Move("nope.md", "docs/"))
    before = _snapshot(repo)
    assert _run(repo, tmp_path, "--apply", spec=spec) == 2
    assert _snapshot(repo) == before
    assert _run(repo, tmp_path, "--apply", "--allow-missing", spec=spec) == 0
    assert (repo / "docs/harness/HARNESS.md").exists()


def test_hash_mismatch_during_move_is_fatal(repo: Path, tmp_path: Path,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    real_replace = rr.os.replace

    def corrupting_replace(src, dst):
        real_replace(src, dst)
        if str(dst).endswith("deck.pptx"):
            with open(dst, "ab") as fh:
                fh.write(b"!")

    plan = rr.build_plan(repo, _spec(), plan_out_rel="none.json", status_sim=False)
    monkeypatch.setattr(rr.os, "replace", corrupting_replace)
    with pytest.raises(rr.ReorgError, match="sha256 changed"):
        rr.apply_plan(repo, _spec(), plan, tmp_path / "bak")


def test_rewrite_skipped_if_file_changed_since_plan(repo: Path, tmp_path: Path) -> None:
    plan = rr.build_plan(repo, _spec(), plan_out_rel="none.json", status_sim=False)
    _write(repo, "scripts/run.py", 'OUT = "docs/HARNESS.md"  # edited concurrently\n')
    res = rr.apply_plan(repo, _spec(), plan, tmp_path / "bak")
    assert "scripts/run.py" in res["rewrite_skipped_changed_since_plan"]
    assert "edited concurrently" in (repo / "scripts/run.py").read_text()


@pytest.mark.parametrize("text,expected", [
    ("see NOTE_a.md.", "see notes/h/NOTE_a.md."),
    ("already notes/h/NOTE_a.md", "already notes/h/NOTE_a.md"),     # root anchor
    ("keep NOTE_a.md.bak", "keep NOTE_a.md.bak"),
    ("xNOTE_a.md", "xNOTE_a.md"),
    ("NOTE_a.md에서", "notes/h/NOTE_a.md에서"),
])
def test_root_anchor_boundaries(text: str, expected: str) -> None:
    rules = rr._build_rules(
        rr.ReorgSpec(path_rewrites=[rr.PathRewrite("NOTE_a.md", "notes/h/NOTE_a.md",
                                                   anchor="root")]),
        rr.Plan("/", "", ""))
    ctx = rr._Ctx(set(), set(), {}, [], set())
    assert rr.compute_edits(text, "x.txt", "x.txt", rules, ctx, [])[0] == expected
