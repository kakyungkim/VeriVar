#!/usr/bin/env python
"""원고에 적힌 수치가 커밋된 결과 파일에서 실제로 나오는지 전수 대조한다.

리뷰어가 "표본만 확인했다"고 남긴 부분을 전수로 바꾸는 게이트.
- 근거 있음(traceable): 결과 JSON/CSV에서 같은 값을 찾음
- 근거 없음(orphan): 못 찾음. 사람이 확인해야 하는 자리
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
MS = ROOT / "docs/manuscript/preprint.md"
# 원자료뿐 아니라 스크립트가 만든 파생 결과도 근거로 인정한다.
# 파생값은 원자료에 그 형태로 없지만, 재현 가능한 스크립트 출력이면 추적 가능하다.
# 근거는 저장소와 함께 배포되는(shipped) 폴더에서만 찾는다. 공개 복제본의 독자가
# 같은 파일로 같은 판정을 재현할 수 있어야 하기 때문이다.
# (2026-09-24 점검: 비공개 experiments/를 근거로 삼고 data/outputs/는 빠뜨렸던 것을 바로잡음.)
DATA_DIRS = ["data/outputs", "data/benchmark", "data/cohorts", "data/golden", "docs/manuscript"]
# 배포되지 않는 작업 폴더. 여기서만 잡히는 근거는 공개 복제본에서 재현되지 않으므로
# DATA_DIRS에 들어오면 실행을 거부한다.
PRIVATE_DIRS = {"experiments", "notes"}
# 이 검사기 자신의 출력은 제외한다. 넣으면 자기 출력을 근거로 삼아 항상 100%가 된다.
SELF_OUTPUT = {"number_reconciliation.json"}

# 원고에서 뽑을 수치: 소수 2~4자리, 퍼센트, n=
PAT = re.compile(r"(?<![\w.])(0\.\d{2,4}|\d{1,3}\.\d{1,2}(?=\s?%))(?![\w.])")
PAT_N = re.compile(r"\bn\s?=\s?(\d{1,4})\b")
# 근거 대조에서 뺄 흔한 값
TRIVIAL = {"0.05", "0.01", "0.50", "0.95", "1.00", "0.00"}


def numbers_in_manuscript():
    text = MS.read_text(encoding="utf-8", errors="ignore")
    body = re.split(r"\n#+\s*References", text)[0]          # 참고문헌 제외
    body = re.sub(r"```.*?```", "", body, flags=re.S)        # 코드블록 제외
    found = defaultdict(list)
    for line in body.split("\n"):
        for m in PAT.finditer(line):
            found[m.group(1)].append(line.strip()[:110])
        for m in PAT_N.finditer(line):
            found["n=" + m.group(1)].append(line.strip()[:110])
    return found


def _check_dirs(dirs):
    """Refuse evidence dirs that are not shipped with the repository."""
    bad = [d for d in dirs if pathlib.PurePosixPath(d).parts[0] in PRIVATE_DIRS]
    if bad:
        raise ValueError(f"unshipped evidence dirs not allowed: {bad}")


def _git_ignored(root, files):
    """Subset of `files` that git ignores (i.e. would not ship in a clone)."""
    if not files:
        return set()
    try:
        out = subprocess.run(
            ["git", "check-ignore", "--stdin"], cwd=root, capture_output=True, text=True,
            input="\n".join(str(f.relative_to(root)) for f in files))
    except (OSError, ValueError):
        return set()
    return {root / line for line in out.stdout.splitlines() if line}


def evidence_files(root=ROOT, dirs=None, respect_gitignore=False):
    """JSON/CSV files that may serve as evidence for a manuscript number."""
    dirs = DATA_DIRS if dirs is None else dirs
    _check_dirs(dirs)
    files = []
    for d in dirs:
        p = root / d
        if not p.exists():
            continue
        files += [f for f in list(p.rglob("*.json")) + list(p.rglob("*.csv"))
                  if f.name not in SELF_OUTPUT]
    if respect_gitignore:
        ignored = _git_ignored(root, files)
        files = [f for f in files if f not in ignored]
    return sorted(files)


def numbers_in_results(root=ROOT, dirs=None, respect_gitignore=False):
    pool = set()
    for f in evidence_files(root, dirs, respect_gitignore):
        try:
            raw = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in re.finditer(r"-?\d+\.\d+|\b\d+\b", raw):
            v = m.group(0)
            pool.add(v)
            if "." in v:                                 # 반올림 표기까지 허용
                try:
                    x = float(v)
                except ValueError:
                    continue
                pool.add(f"{x:.2f}")
                pool.add(f"{x:.3f}")
                pool.add(f"{x * 100:.1f}")
    return pool


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--respect-gitignore", action="store_true",
                    help="drop evidence files git ignores (what a fresh clone would contain)")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "docs/manuscript/number_reconciliation.json",
                    help="where to write the reconciliation JSON")
    ap.add_argument("--no-write", action="store_true", help="print only; write nothing")
    args = ap.parse_args(argv)
    ms = numbers_in_manuscript()
    res = numbers_in_results(respect_gitignore=args.respect_gitignore)
    traceable, orphan = {}, {}
    for num, ctxs in ms.items():
        key = num[2:] if num.startswith("n=") else num
        (traceable if (key in res or key in TRIVIAL) else orphan)[num] = ctxs

    total = len(ms)
    print(f"원고 고유 수치      {total}개")
    print(f"  근거 있음        {len(traceable)}개 ({len(traceable)/total*100:.0f}%)")
    print(f"  근거 못 찾음      {len(orphan)}개 ({len(orphan)/total*100:.0f}%)")
    print()
    print("=== 사람이 확인해야 하는 수치 ===")
    for num, ctxs in sorted(orphan.items(), key=lambda kv: -len(kv[1]))[:25]:
        print(f"  {num:>8}  ({len(ctxs)}회)  {ctxs[0]}")

    if not args.no_write:
        out = args.out
        out.write_text(json.dumps(
            {"total": total, "traceable": sorted(traceable), "orphan": {k: v for k, v in orphan.items()}},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n저장: {out}")
    return 1 if orphan else 0


if __name__ == "__main__":
    sys.exit(main())
