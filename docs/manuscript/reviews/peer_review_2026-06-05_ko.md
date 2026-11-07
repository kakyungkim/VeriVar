> **과거 기록 (2026-09-24 표기).** 이 검토는 이전 원고판을 대상으로 한다. 여기 인용된 일부 수치(규칙 갈래 정확도 0.843, n = 458 ClinVar 홀드아웃, AUROC 0.902 등)는 이후 정정되거나 철회되었다. 현재 원고의 정정 내역과 `peer_review_2026-09-24.md`를 참고할 것.

# 피어 리뷰 — *Citation-grounded retrieval for faithful LLM somatic variant interpretation*

**심사 보고서**
**날짜:** 2026-06-05
**가정 등급:** JAMIA / npj Digital Medicine / Bioinformatics 급
**검토 원고:** `docs/manuscript/preprint.md` (현재 상태)

> 본 문서는 영문 리뷰 [peer_review_2026-06-05.md](peer_review_2026-06-05.md)의 한국어 번역본입니다. 이 리뷰는 [2026-06-04 리뷰](peer_review_2026-06-04.md)의 필수 수정(R1–R6)이 원고에 **반영된 이후**의 현재 원고를 평가한 것입니다.

---

## 권고: **MINOR REVISION (소폭 수정)**

신중하고 비범하게 자기절제된 원고이며, 이번 수정으로 이전 Major-revision을 부른 격차들이 실질적으로 메워졌다. 가장 큰 이전 위험 — 독자가 LLM 시스템에 0.843 정확도와 경험적으로 *측정된* 완벽 충실성을 귀속시키는 것 — 은 실질적으로 해소됐다: 0.843은 이제 "LLM이 아닌" 결정론적 rule 엔진에 반복·명시적으로 귀속되고, 충실성 스코어카드는 *게이트가 구성상 강제하는 것*으로 fence되며 *경험적* 게이트-이전 동작(out-of-bundle 인용 0/106 vs 비검색 arm 46.4%, CI 0 배제)을 먼저 앞세운다. generative arm 정확도 주장은 정직하게 "유의차 없음"으로 진술된다. 헤드라인 rule-arm·OncoVI 수치에 CI가 붙었고, 잠정 판정은 AI-보조·비병리학자-서명으로 명확히 표기됐으며, TRIPOD-AI/STARD 단락·variant-flow·model card·유전자별 표가 추가됐다. 남은 작업은 진정 사소하고 대체로 프레이밍 수준이다. 가장 의사결정-결정적인 남은 이슈는 *근거가 아니라 논문 구조*에 관한 것이다: 원고는 여전히 세 가지 서로 다른 산출물 — 충실한 generative 해석기, 경쟁력 있는 결정론적 VICC 엔진, 명시했으나 실행하지 않은 미래 벤치마크 — 을 하나의 충실성-우선 기치 아래 묶고 있어, 강한 rule-arm 결과가 제한된 generative 결과에 신뢰를 빌려주지 않도록 독자가 실제로 애써야 한다. 국소 수정은 다 됐고, 남은 것은 전체 takeaway를 오독 불가능하게 만드는 일이다.

---

## 원고 요약

저자들은 두 표준(ClinGen/CGC/VICC 발암성, AMP/ASCO/CAP 임상 tier)으로 변이를 분류하는 dual-mode 해석기를, 하이브리드 인용-기반 검색(구조화 조회, CIViC dense 검색, 지식 그래프)과 "충실성 계약"(모든 주장은 검색된 식별자 인용; 변이-특이 근거 없으면 VUS abstain) 아래 제시한다. Generative mode(LLM이 라벨 부여), Deterministic mode(rule이 라벨 부여, LLM은 근거만 서술), 비검색 baseline, 그리고 — 별도 arm으로 보고되는 — 인용 가능 VICC 점수기반 rule 엔진을 비교한다. 평가는 56변이 5-cancer TCGA 코호트와 외부 70변이 Horak(2022) 전문가 gold standard, leakage-free 충실성 지표, leakage 통제(temporal holdout, LOVO, second model, embedding ablation), bootstrap CI, exact McNemar로 수행된다. 핵심 주장: 검색이 generative 해석기를 구성상 충실·감사가능하게 만들고 확신에 찬 parametric over-calling을 억제하며, generative arm 정확도가 baseline과 유의차 없고, — 별도로 — 결정론적 VICC rule arm이 Horak-70에서 3-class 0.843에 도달해 더 높은 특이도에서 OncoVI와 통계적으로 구별 불가하다는 것.

`horak_vicc.json`과 `oncovi_headtohead.json`을 spot-check함: 0.843/0.841 rule-arm 수치, OncoVI 0.797, McNemar p=0.66, 특이도 대비, discordant-pair 카운트가 모두 커밋된 산출물과 일치. 재현성은 이 투고의 진정한 강점이다.

---

## Major points (주요 지적)

**1. 충실성 재프레이밍은 이제 정확하나, 논문은 그 논리적 귀결을 더 분명히 인정해야 한다.** 수정본은 *경험적* 게이트-이전 발견(검색 arm이 인용 106건, out-of-bundle 0건, 출처-범주 imprecision 18.9%)과 *구성상* 게이트-이후 스코어카드(hallucination 0, grounding 1.0, abstention recall 1.0)를 올바르게 분리하고, §3.1은 "검색되지 않은 식별자를 일절 안 내는 시스템은 정의상 fabrication 0, grounding 1.0이 된다"고 명시한다. 이전 리뷰가 요청한 정직한 프레이밍 그대로이며 잘 됐다. 잔여 이슈는 abstract와 일부 figure 캡션(Figure 1c, 2c)이 여전히 네 개의 1.0을 by-construction 한정 없이 "scorecard"/"contract behaviours … 모두 1.0"으로 제시한다는 점이다. abstract와 그림만 보는 — 대다수인 — 독자는 여전히 네 개의 완벽 충실성 지표가 측정됐다고 받아들일 수 있다. 가장 값싼 충분 수정: 진정 경험적·반증가능한 단일 수치(게이트-이전 0/106 vs 비검색 46.4%, CI 0 배제)를 요약되는 모든 곳에서 헤드라인 충실성 통계로 삼고, 1.0 4종을 abstract와 두 캡션에서 본문이 이미 하듯 "계약 보장(강제됨, 측정 아님)"으로 라벨하라.

**2. generative arm의 기여는 거의 전적으로 한 비교에 의존하며, 그 비교는 저자 자신의 분석상 검정력이 부족하다.** 충실성-vs-비검색 격차(0% vs 46.4%)는 연구의 하중 지지 경험적 결과이고 견고하다. 그러나 거기 실리는 *해석적* 무게 — 검색이 임상적으로 의미 있게 "확신에 찬 parametric over-calling을 억제"한다 — 는 12/56(21.4%) over-call→VUS 재분류에 기대는데, 그 정확성을 저자들은 옳게 주장하지 않는다. 새로 추가된 잠정 판정(beyond-rules 3건 중 2건이 LLM의 abstention이 아니라 rule을 지지)은 칭찬할 만큼 솔직하나 프레이밍에 반한다: 그 12건 중 몇은 교정이 아니라 과보수적 abstention일 수 있음을 시사한다. 원고는 이를 산문에서 정직하게 다루나, abstract는 여전히 21.4%를 반대-신호 없이 긍정으로("검색이 12건을 … 근거-기반 VUS로 재분류") 나열한다. 새 실험을 요청하는 게 아니다 — 저자들은 판정을 검정력 있는 연구로 옳게 미뤘다. abstract와 Discussion 주요-발견 단락이 잠정 판정의 방향(재분류에 과잉-abstention이 포함될 수 있음)을 담아 "over-calling 억제" 주장이 입증되지 않은 net-positive 정확도/안전 효과로 읽히지 않게 하라는 것이다.

**3. 논문의 구조가 여전히 강한 rule-arm 결과가 제한된 generative 결과를 보조하게 둔다.** 가장 의사결정-결정적인 남은 이슈이며 사실이 아니라 구조의 문제다. 섹션별 귀속은 이제 정확하다 — 0.843은 abstract·§3.3·Table 1·Discussion에서 결정론적-LLM-아님으로 fence됐다. 그러나 논문의 *제목*, 프레이밍("faithful LLM … interpretation"), 서사 궤적은 LLM 시스템에 관한 것인데, 유일한 경쟁력 있는 정확도 결과는 저자들이 신규성을 명시적으로 주장하지 않는(OncoVI가 이미 criterion-to-source 매핑을 함) rule 엔진의 것이다. 따라서 독자는 헤드라인 수치(0.843, SOTA와 구별 불가)가 가장 덜 신규한 구성요소에서 나오고, 신규 구성요소(충실한 generative 해석)는 명시적으로 정확도 진전이 아닌 논문을 마주한다. 방어 가능하고 정직하게 공개됐으나 안착시키기 어려운 이야기다. 프레이밍에서 이 논문이 어느 쪽인지 정하길 권한다: (a) LLM 변이 해석을 위한 충실성·감사가능성 방법론 기여이고, VICC 엔진은 "프레임워크가 정확도-경쟁력 있을 수 있다"는 보조 전시물로 확실히 부차적으로 두거나; (b) rule 엔진에 제목/abstract에서 동등 비중을 주는 2-기여 논문. 현재 텍스트는 둘 사이를 맴돈다. 신규성 공개를 고려하면 (a)가 더 깔끔하고 정직하며, abstract와 Discussion에서 rule-arm 결과를 co-headline이 아니라 "같은 감사가능 프레임워크가 경쟁력 있는 정확도에도 도달할 수 있다"로 일관되게 위치시키면 된다.

**4. parametric leakage는 여전히 미통제다 — 충분히 공개됐으나, 실행된 통제에 과의존하지 않게 프레이밍하라.** 저자들은 temporal-holdout·LOVO 통제가 검색-corpus 채널만 다루며 LLM 자체 parametric leakage는 비검색 floor로만 정량화됨을 명시(§3.7, Limitations)한다. 옳은 공개다. 우려는 abstract 셋째 문장("어떤 정확도 효과가 진짜인지 leakage 산물인지")과 leakage-통제 서사가 leakage가 폭넓게 무력화된 것처럼 읽힐 수 있다는 점인데, 사실 유명 driver 변이에 가장 관련된 채널(parametric recall)이 유일하게 미통제로 남은 채널이다. 어차피 방어할 generative 정확도 효과가 없으니(Major 2/3), 가장 깔끔한 수정은 leakage 프레이밍을 거기에 맞추는 것이다: 통제는 *충실성* 동작과 generative 정확도 효과의 부재가 corpus-leakage 산물이 아님을 확립한다, 그뿐. 제안된 깨끗한 ClinVar-2024 temporal holdout(Discussion)이 parametric 채널의 올바른 미래 도구이며, "추가 벤치마크"가 아니라 "현재 미통제 채널을 다루는 통제"로 명명되어야 한다.

**5. OncoVI head-to-head는 공정하나 OncoVI의 홈셋에서 채점되며, 안전-프로파일 논증엔 명시적 caveat 하나가 필요하다.** 저자들은 비교가 Horak-70, "OncoVI 자신의 홈셋"에서 이뤄짐을 공개하고, 더 높은 특이도에서의 동등 결과를 독립 벤치마크가 아니라 동일 변이 head-to-head로 프레이밍 — 적절하다. 정직한 VUS 9건의 abstention-우선 엔진이 over-call 9건의 엔진보다 "안전"하다는 실질 주장은 잘 논증됐고 임상적으로 타당하다. 빠진 caveat 하나: 안전-오류-프로파일 논증은 놓친 발암성 호출(엔진이 abstain하나 OncoVI가 잡는 9개 true-oncogenic 변이)의 운영 비용이 over-call 비용보다 낮다고 가정한다. VUS abstention이 환자가 가용 표적치료를 못 받는다는 의미인 상황에서 그 비대칭은 자명하지 않다. 원고는 이미 민감도 격차를 인정하고 dial을 제시한다; "안전"이 "이 워크플로에서 과치료가 미탐지보다 더 해롭다"는 임상 가정에 조건부임을 인정하는 한 문장 추가가 필요하다 — draft-and-review 보조도구엔 타당하나 보편적이지 않다.

---

## Minor points (사소 지적)

1. **Abstract 분량·전면배치.** abstract Results 단락이 게이트-이전 충실성·게이트-이후 보장·generative 비유의·rule arm·OncoVI head-to-head·leakage 통제를 담은 ~250단어의 문장-밀집 블록이다. 타깃 venue에선 단어 제한 초과이며 파싱이 어렵다. 단일 경험적 충실성 수치와 rule-arm 헤드라인으로 시작하고 leakage-통제 나열을 마무리 절 하나로 옮기는 것을 고려하라.
2. **"유의차 없음" vs "non-inferior".** Objective·Discussion은 margin 미지정이라 non-inferiority 검정이 아니라 겹치는 CI·비유의 McNemar를 보고한다고 신중히 말한다. 좋다. 다만 "comparable"이 여러 곳에서 "유의차 없음"과 함께 등장하는데 약한 동등성 주장으로 읽힐 수 있다. "유의차 없음(margin 미지정; n=70에서 차이의 증거 부재이지 동등성의 증거가 아님)"을 선호하라.
3. **temperature 0.4 self-consistency vs 결정론 주장.** model card는 "결정론"용 temperature 0이나 voting 패스는 0.4로 표기. 주 generative 수치가 0.4의 n=3 voting에 의존하므로 단일-run 결과가 엄밀히 결정론적이지 않아 "재현성" 프레이밍과 약간 긴장한다. 투표된 호출의 run-to-run 분산(또는 샘플링 고정 시드) 한 줄 주석이면 닫힌다.
4. **잠정 판정 n=3.** beyond-rules 판정은 3변이만 다루고 AI-보조이며 명확히 표기됨. (Major 2대로 abstract-수준 언급을 추가한다면) n=3을 명시해 체계적 리뷰로 읽히지 않게.
5. **Figure 5 capability landscape.** 캡션은 위치가 "동일 입력 head-to-head 아님"이고 수치 셀이 각 출처 연구에서 옴을 올바르게 명시. 옳은 disclaimer; landscape 표가 행 간 비교를 유도하므로 정확도 수치가 행 간 직접 비교 불가임도 명시하라.
6. **유전자별 표(S1) PTEN 행.** generative-arm PTEN 정확도 0.00(n=6) — 두드러지고 정직한 공개. PTEN 6건 미스가 모두 과잉-abstention 패턴(무작위 오류 아님)임을 적는 한 절이면 독자가 이를 무작위 오류가 아닌 VUS-과잉해소 약점과 연결하는 데 도움.
7. **ClinVar 일반화 셋 프레이밍.** n=458 ClinVar 결과는 "발암성 탐지, 전체 3-class 아님"(benign recall 0, 균형 3-class 0.505)으로 정직히 한정됨. 좋다. AUROC 0.902는 §3.5에서처럼 인접 "oncogenic-vs-rest, 3-class 아님" 한정 없이는 어떤 요약에도 등장해선 안 된다.

---

## 항목별 점수 (1–5)

| 항목 | 점수 | 한 줄 근거 |
|---|---|---|
| 중요성 / 독창성 | 4 | 변이 해석에서 충실성-우선 축 + leakage 통제는 진정·잘 위치한 격차; 경쟁력 있는 정확도가 명시적으로 비신규인 rule 엔진의 것이라 완화. |
| 방법 타당성 | 4 | 방법이 엄밀하고 정직하게 한정됨; 주 유보는 미통제 parametric leakage(공개됨)와 단일-run·0.4-voting generative 추정. |
| 통계 타당성 | 4 | bootstrap CI·exact McNemar 전반 사용, 비유의를 윤색 없이 보고; n=70 검정력 부족(저자가 진술·수정안 제시). |
| 재현성 | 5 | 스냅샷-오프라인, 90 테스트, 결과별 스크립트; spot-check 헤드라인 수치가 커밋 JSON과 일치. |
| 명료성 | 3 | 국소적으로 정밀하나 전체적으로 밀집; 3-산출물 구조와 단일 과장 abstract가 takeaway를 작업의 가치보다 파악하기 어렵게 함. |
| 그림 / 표 | 4 | 표/캡션이 근거-담지이고 rule-arm 오류-비대칭 프레이밍이 좋음; 1.0 "scorecard" 캡션이 여전히 측정-아닌-강제 충실성을 암시할 위험. |

**종합 평점:** 4 / 5 — 새 근거가 아니라 프레이밍 수준 정비가 필요한, 견실·정직·재현 가능한 기여.
**심사자 확신도:** 4 / 5 — LLM/RAG-유전체 문헌, VICC/AMP 표준, 통계에 익숙함; 파이프라인을 독립 재실행하진 않았고 rule-엔진 criterion-firing 내부에 대한 확신은 완전하기보다 중간.

---

## 보고지침 노트

해당 도구가 올바르게 식별됨: 예측모델 보고엔 **TRIPOD-AI**, 전문가 참조표준 대비 외부 정확도 평가엔 **STARD** 진단정확도 렌즈(TRIPOD-AI/STARD 단락·variant flow·model card가 이제 존재하여 이전 리뷰의 주 보고 격차를 해소). QA가 아니라 지침 항목으로서 남은 실질 요청:
- **STARD 중간-결과 처리**는 원칙적으로 다뤄짐(VUS/abstention을 보고 class로). STARD식 variant flow를 산문이 아니라 본문 내 작은 흐름도 또는 명시적 count chain으로 만들어 398 → 56(코호트)와 70 / 69 / 458(외부) 경로가 한눈에 감사 가능하게.
- **TRIPOD-AI 표본크기 정당화**는 부재-and-deferred로 선언됨(비검정력 연구엔 수용 가능)이나, Discussion의 검정력 분석(0.05 효과에 수백 변이)을 Methods "Reporting" 단락에서 교차참조해 선언과 해법이 함께 있게.
- **TRIPOD-AI 하위집단 보고**는 유전자별 Table S1로 충족됨; 얇은-커버리지 유전자(EZH2, PTEN)를 post hoc가 아니라 사전 진술 하위집단 한계로 적는 것을 고려.
- CONSORT/PRISMA/ARRIVE는 해당 없음(시험·체계적 리뷰·동물 연구 없음).

---

## 편집자에게 보내는 비공개 코멘트

이전 형태에서 실제 과장 문제(완벽-충실성 스코어카드와, 일반 독자가 LLM에 귀속시킬 0.843 정확도)를 안고 있던 논문의 강한 수정본이다. 저자들은 편리한 길이 아니라 옳은 길을 택했다: 게이트-강제 지표를 구성상-보장으로 fence하고, 단일 반증가능 충실성 수치를 앞세우며, 0.843을 신규성 주장하지 않는 결정론적 rule 엔진에 반복·명시 귀속하고, CI와 비병리학자-서명 잠정 판정을 추가하며, 정확도 주장에 필요한 검정력 있는 연구를 (실행이 아니라) 명시했다. 핵심 과학 주장이 이제 근거와 부합하고, 공개 산출물이 헤드라인 수치를 spot-check로 재현한다.

핵심 주장 — 인용-기반 검색이 LLM 변이 해석기를 구성상 충실·감사가능하게 만들 수 있고, 같은 프레임워크 안에서 open SOTA 엔진 대비 정확도를 희생하지 않고 할 수 있다 — 은 수정을 견디며 작성된 대로 지지 가능하다. 남은 우려는 무결성이 아니라 프레이밍이다: 논문은 신규하지만-제한된 기여(충실 generative 해석, 정확도 이득 없음)와 경쟁력 있지만-비신규인 기여(VICC rule 엔진)를 묶어, 독자가 둘을 분리하려 애써야 한다. 이는 Major revision에 이르지 않는다고 본다 — 모든 필수 공개가 이제 본문에 있기 때문이다; 수정은 오독 방지를 위한 abstract/캡션/Discussion 정비와 몇 개의 한 줄 caveat(parametric-leakage 범위, "안전"의 임상 가정, 잠정 판정의 과잉-abstention 방향)이다. Minor revision 후 수용에 편안하며 2차 심사자 재심은 불필요하다고 보나, 최종본에서 abstract와 figure 캡션이 by-construction 한정을 담는지 편집자가 확인하길 바란다. 통계 보고의 정직함은 이 venue 등급에선 논문에 유리한 점이며 "부정적 결과"로 불이익받기보다 인정받아야 한다.
