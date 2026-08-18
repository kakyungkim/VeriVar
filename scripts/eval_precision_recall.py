#!/usr/bin/env python
"""per-class precision/recall/F1, 혼동행렬, macro-F1, quadratic-weighted kappa를 계산한다.

원고 Discussion이 "Report per-class precision, recall, and F1 with full confusion
matrices, and adopt macro-F1 and quadratic-weighted kappa as primary endpoints"를
권고하면서 정작 본문에 그 표가 없어, 커밋된 결과에서 직접 계산한다.
표준 라이브러리만 쓴다(외부 의존 없음).
"""
import json, pathlib, sys
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 5단계 순서형 라벨 (quadratic weight 계산에 순서가 필요)
ORDER = ["Benign", "Likely Benign", "VUS", "Likely Oncogenic", "Oncogenic"]


def load_pairs(path, gold_key="gold", pred_key="pred"):
    d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    rows = d if isinstance(d, list) else d.get("rows", [])
    out = []
    for r in rows:
        g, p = r.get(gold_key), r.get(pred_key)
        if g and p:
            out.append((g, p))
    return out


def prf(pairs, labels):
    """per-class precision / recall / F1 / support"""
    tp = Counter(); fp = Counter(); fn = Counter()
    for g, p in pairs:
        if g == p:
            tp[g] += 1
        else:
            fp[p] += 1
            fn[g] += 1
    res = {}
    for c in labels:
        P = tp[c] / (tp[c] + fp[c]) if tp[c] + fp[c] else 0.0
        R = tp[c] / (tp[c] + fn[c]) if tp[c] + fn[c] else 0.0
        F = 2 * P * R / (P + R) if P + R else 0.0
        res[c] = {"precision": P, "recall": R, "f1": F, "support": tp[c] + fn[c]}
    return res


def quadratic_weighted_kappa(pairs, order):
    """순서형 라벨의 불일치를 거리 제곱으로 벌하는 kappa"""
    idx = {c: i for i, c in enumerate(order)}
    pairs = [(g, p) for g, p in pairs if g in idx and p in idx]
    n = len(pairs)
    if not n:
        return None
    k = len(order)
    O = [[0] * k for _ in range(k)]
    for g, p in pairs:
        O[idx[g]][idx[p]] += 1
    gh = Counter(idx[g] for g, _ in pairs)
    ph = Counter(idx[p] for _, p in pairs)
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) ** 2) / ((k - 1) ** 2)
            num += w * O[i][j]
            den += w * gh[i] * ph[j] / n
    return 1 - num / den if den else None


def confusion(pairs, labels):
    m = defaultdict(Counter)
    for g, p in pairs:
        m[g][p] += 1
    return m


def report(name, pairs):
    labels = [c for c in ORDER if any(c in (g, p) for g, p in pairs)]
    extra = sorted({c for g, p in pairs for c in (g, p)} - set(ORDER))
    labels += extra
    res = prf(pairs, labels)
    acc = sum(1 for g, p in pairs if g == p) / len(pairs)
    macro_f1 = sum(v["f1"] for v in res.values()) / len(res)
    qwk = quadratic_weighted_kappa(pairs, ORDER)

    print(f"\n{'='*66}\n### {name}   n = {len(pairs)}")
    print(f"{'class':<18}{'precision':>10}{'recall':>9}{'F1':>8}{'support':>9}")
    for c in labels:
        v = res[c]
        print(f"{c:<18}{v['precision']:>10.3f}{v['recall']:>9.3f}{v['f1']:>8.3f}{v['support']:>9}")
    print(f"{'-'*54}")
    print(f"{'accuracy':<18}{acc:>10.3f}")
    print(f"{'macro-F1':<18}{macro_f1:>10.3f}")
    if qwk is not None:
        print(f"{'quadratic κ':<18}{qwk:>10.3f}")

    print("\n혼동행렬 (행=정답, 열=예측)")
    m = confusion(pairs, labels)
    print(" " * 18 + "".join(f"{c[:9]:>11}" for c in labels))
    for g in labels:
        print(f"{g:<18}" + "".join(f"{m[g][p]:>11}" for p in labels))
    return {"n": len(pairs), "accuracy": acc, "macro_f1": macro_f1,
            "quadratic_kappa": qwk, "per_class": res}


if __name__ == "__main__":
    out = {}
    src = ROOT / "data/benchmark/clinvar_vicc_rows.json"
    if src.exists():
        out["clinvar_vicc"] = report("ClinVar VICC rule arm", load_pairs(src))
    # Horak-70: 한 파일에 세 팔(rule / RAG 있음 / RAG 없음)의 예측이 나란히 있다
    for f, pred_key, name in [
            ("data/benchmark/horak_results.json", "rule",       "Horak-70 규칙 팔"),
            ("data/benchmark/horak_results.json", "llm_rag",    "Horak-70 LLM + 검색"),
            ("data/benchmark/horak_results.json", "llm_norag",  "Horak-70 LLM, 검색 없음"),
            ("data/benchmark/horak_vicc.json",    "vicc",       "Horak-70 VICC 규칙")]:
        p = ROOT / f
        if not p.exists():
            continue
        pairs = load_pairs(p, pred_key=pred_key)
        if pairs:
            out[f"{pathlib.Path(f).stem}:{pred_key}"] = report(name, pairs)
    dst = ROOT / "docs/manuscript/precision_recall_report.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {dst.relative_to(ROOT)}")
