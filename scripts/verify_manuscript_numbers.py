#!/usr/bin/env python
"""원고에 적힌 수치가 커밋된 결과 파일에서 실제로 나오는지 전수 대조한다.

리뷰어가 "표본만 확인했다"고 남긴 부분을 전수로 바꾸는 게이트.
- 근거 있음(traceable): 결과 JSON/CSV에서 같은 값을 찾음
- 근거 없음(orphan): 못 찾음. 사람이 확인해야 하는 자리
"""
import json, re, pathlib, sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
MS = ROOT / "docs/manuscript/preprint.md"
# 원자료뿐 아니라 스크립트가 만든 파생 결과도 근거로 인정한다.
# 파생값은 원자료에 그 형태로 없지만, 재현 가능한 스크립트 출력이면 추적 가능하다.
DATA_DIRS = ["data/benchmark", "data/cohorts", "experiments", "docs/manuscript"]
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


def numbers_in_results():
    pool = set()
    for d in DATA_DIRS:
        p = ROOT / d
        if not p.exists():
            continue
        for f in list(p.rglob("*.json")) + list(p.rglob("*.csv")):
            if f.name in SELF_OUTPUT:
                continue
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


def main():
    ms, res = numbers_in_manuscript(), numbers_in_results()
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

    out = ROOT / "docs/manuscript/number_reconciliation.json"
    out.write_text(json.dumps(
        {"total": total, "traceable": sorted(traceable), "orphan": {k: v for k, v in orphan.items()}},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {out.relative_to(ROOT)}")
    return 1 if orphan else 0


if __name__ == "__main__":
    sys.exit(main())
