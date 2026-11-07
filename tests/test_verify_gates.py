"""Tests for the manuscript gates (scripts.verify_manuscript{,_numbers}).

Covers the 2026-09-24 reproducibility-audit fixes:
- the number-traceability gate draws evidence only from shipped dirs (never experiments/);
- worksheet checks report SKIP, not a vacuous PASS, when notes/ is absent;
- the Horak/OncoVI CIs the manuscript quotes are what src.eval.stats.bootstrap_ci yields.
All tests are offline and use synthetic inputs except the last, which skips when the
benchmark outputs are not present (public clone before the data bundle lands).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import scripts.verify_manuscript as vm
import scripts.verify_manuscript_numbers as vmn
from src.eval.stats import bootstrap_ci

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- numbers gate
def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj))


def test_default_evidence_dirs_are_shipped_only():
    assert "experiments" not in vmn.DATA_DIRS
    assert "data/outputs" in vmn.DATA_DIRS
    assert "data/benchmark" in vmn.DATA_DIRS
    assert not any(Path(d).parts[0] in vmn.PRIVATE_DIRS for d in vmn.DATA_DIRS)


@pytest.mark.parametrize("bad", ["experiments", "experiments/multimodel_faithfulness", "notes"])
def test_private_dirs_are_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        vmn.numbers_in_results(root=tmp_path, dirs=["data/outputs", bad])


def test_number_only_in_experiments_is_not_traced(tmp_path):
    _write(tmp_path / "experiments" / "run.json", {"acc": 0.4321})
    _write(tmp_path / "data" / "outputs" / "r.json", {"acc": 0.8771})
    pool = vmn.numbers_in_results(root=tmp_path)
    assert "0.877" in pool and "87.7" in pool          # shipped output counts
    assert "0.4321" not in pool and "0.432" not in pool  # private run does not


def test_self_output_never_counts_as_evidence(tmp_path):
    _write(tmp_path / "docs" / "manuscript" / "number_reconciliation.json", {"x": 0.1234})
    assert "0.1234" not in vmn.numbers_in_results(root=tmp_path)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_respect_gitignore_drops_ignored_files(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("data/outputs/raw.json\n")
    _write(tmp_path / "data" / "outputs" / "raw.json", {"v": 0.5551})
    _write(tmp_path / "data" / "outputs" / "kept.json", {"v": 0.6662})
    loose = vmn.numbers_in_results(root=tmp_path)
    strict = vmn.numbers_in_results(root=tmp_path, respect_gitignore=True)
    assert "0.5551" in loose and "0.5551" not in strict
    assert "0.6662" in strict


def test_no_write_leaves_reconciliation_untouched(tmp_path):
    out = tmp_path / "rec.json"
    vmn.main(["--no-write", "--out", str(out)])
    assert not out.exists()
    vmn.main(["--out", str(out)])
    assert json.loads(out.read_text())["total"] > 0


# ------------------------------------------------------------- worksheet SKIP
def test_worksheet_absent_reports_skip_not_pass(tmp_path):
    rep = vm.Report()
    vm.check_worksheet(rep, set(), tmp_path / "missing.md")
    assert len(rep.checks) == 2
    assert all(c["skipped"] for c in rep.checks)
    assert rep.failed == [] and len(rep.skipped) == 2


def test_worksheet_present_keeps_pass_fail(tmp_path):
    ws = tmp_path / "ws.md"
    ws.write_text("| gene | change |\n|---|---|\n| KRAS G12D | x |\n")
    rep = vm.Report()
    vm.check_worksheet(rep, {("KRAS", "G12D")}, ws)
    assert [c["ok"] for c in rep.checks] == [True, True]
    assert rep.skipped == []

    ws.write_text("| gene | change |\n|---|---|\n| KRAS G99Z | x |\n")
    rep = vm.Report()
    vm.check_worksheet(rep, {("KRAS", "G12D")}, ws)
    assert rep.checks[0]["ok"] is False and "KRAS G99Z" in rep.checks[0]["detail"]
    assert not rep.checks[0]["skipped"]


def test_report_summary_separates_skips(capsys):
    rep = vm.Report()
    rep.add("a", True)
    rep.skip("b", "absent")
    rep.print()
    out = capsys.readouterr().out
    assert "[SKIP] b" in out and "1/1 checks passed; 1 skipped" in out


# ----------------------------------------------------- manuscript-quoted CIs
BENCH = ROOT / "data" / "benchmark"


def _collapse(c: str) -> str:
    if c in ("Oncogenic", "Likely Oncogenic"):
        return "ONC"
    return "BEN" if c in ("Benign", "Likely Benign") else "VUS"


@pytest.mark.skipif(not (BENCH / "horak_vicc.json").exists(), reason="benchmark output absent")
def test_horak_vicc_ci_matches_bootstrap():
    rep = json.loads((BENCH / "horak_vicc.json").read_text())
    ci = bootstrap_ci([float(_collapse(r["vicc"]) == _collapse(r["gold"])) for r in rep["rows"]])
    assert rep["accuracy_3class_ci"] == ci
    # Pinned to the SOP-strict primary (2026-09-24). Previous configurations: os2_fixed
    # 0.686-0.871 (acc3 0.786); original 0.757-0.929 (acc3 0.843).
    assert rep["config"] == "sop_strict"
    assert (ci["lo"], ci["hi"]) == (0.543, 0.771)


# ---------------------------------------------------------------- stale-number guard
_NOTE = ("### Correction note: rule-arm configuration\n\nOriginal accuracy 0.843; retired holdout "
         "n = 458, AUROC 0.902, specificity 0.967; CancerVar p = 0.011.\n\n")


@pytest.mark.parametrize("stale", [
    "The rule arm reached 0.843 accuracy.",
    "ClinVar AUROC 0.902 was reported.",
    "specificity 0.967 on the holdout",
    "on the holdout (n = 458)",
    "differed from CancerVar (p = 0.011).",
])
def test_stale_guard_flags_withdrawn_values_outside_note(stale):
    text = "## Results\n\n" + stale + "\n\n" + _NOTE + "### Next\n\nclean text\n"
    assert vm.stale_hits(text), stale


def test_stale_guard_allows_values_inside_note_and_ko_heading():
    assert vm.stale_hits("## Results\n\nclean 0.657\n\n" + _NOTE + "## Discussion\n\nok\n") == []
    ko = "## 결과\n\n### 정정 노트: 규칙 arm\n\n0.843, n = 458, 0.902\n\n### 다음\n\n깨끗함\n"
    assert vm.stale_hits(ko) == []
    _, found = vm.strip_correction_note(ko)
    assert found


def test_stale_guard_ignores_longer_numbers():
    # 0.8431 or 10.843 are different numbers, not the withdrawn value
    assert vm.stale_hits("## R\n\nvalues 0.8431 and 10.843 and 0.9025\n") == []


def test_stale_guard_on_current_manuscripts():
    for p in (vm.PREPRINT, vm.PREPRINT_KO):
        if p.exists():
            t = p.read_text()
            assert vm.strip_correction_note(t)[1], f"{p.name}: correction note missing"
            assert vm.stale_hits(t) == [], f"{p.name}: {vm.stale_hits(t)[:3]}"
