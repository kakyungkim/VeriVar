# 피어 리뷰 — "Citation-grounded retrieval for faithful LLM somatic variant interpretation"

**심사자(Reviewer):** (정밀종양학 / 임상정보학 분야 referee)
**날짜:** 2026-06-04
**원고:** `docs/manuscript/preprint.md` (bioRxiv preprint 초안)
**가정한 투고 등급:** JAMIA / npj Digital Medicine / Bioinformatics 급의 방법론·벤치마킹 저널

> 본 문서는 영문 리뷰 [peer_review_2026-06-04.md](peer_review_2026-06-04.md)의 한국어 번역본입니다. 리뷰는 필수 수정을 원고에 반영하기 **이전** 원고를 기준으로 작성되었습니다.
>
> *형식: 생의학 저널 referee 리포트(산문형 major/minor) + 항목별 점수표 — 혼합 house style(eLife / Nature-npj 투명 피어리뷰 / OpenReview 벤치마킹).*
> *범위: 본질적 과학 판단만. 사전 QA(인용/출처 정확성, 그림 렌더링, 기계적 수치-출처 대조, 참고문헌 완전성)는 완료된 것으로 전제하며 저자의 QA 파이프라인(citation-management / 검증 게이트 / paper-critic)이 담당한다 — 여기서는 의도적으로 나열하지 않는다.*

---

## 권고: **MAJOR REVISION (대폭 수정)**

비정상적으로 정직하고 잘 계측된 원고로, 프레이밍의 절제가 가장 큰 강점이다: 저자들은 정밀종양학-LLM 문헌이 빠지기 쉬운 과장을 거듭 피하며, 충실성 격차는 실재하고 통계적으로 견고하고, leakage 통제는 내가 아는 어떤 유사 LLM-변이 논문보다 철저하다. 핵심 주장 — 충실성/감사가능성이 구성상 보장되고 결과가 leakage에 견고하다 — 은 수정을 견뎌낼 것이며, 내 우려는 타당성이 아니라 귀속(attribution)의 정밀성에 관한 것이고 새 실험을 요하지 않는다. **가장 의사결정-결정적인 이슈는 표현상의 문제다:** 원고는 매우 다른 두 정확도 영역(완만하고 명시적으로 우월하지 않은 ~0.60의 generative LLM, 그리고 open 엔진 OncoVI를 따라잡는 0.843의 강한 결정론적 VICC rule 엔진)을 보고하는데, 현재 프레이밍이 rule arm의 강한 수치가 LLM 시스템에 halo를 드리우게 둔다. 이 점과 "faithful by construction" 헤드라인의 부분적 정의성이 minor가 아니라 major revision으로 두는 이유다.

---

## 원고 요약

저자들은 두 커뮤니티 표준(ClinGen/CGC/VICC 발암성, AMP/ASCO/CAP 임상 tier)으로 변이를 분류하는 dual-mode 해석기를, 하이브리드 인용-기반 검색 계층(구조화 KB 조회, CIViC dense 검색, 지식 그래프)과 명시적 "충실성 계약"(모든 주장은 검색된 식별자를 인용; 변이-특이 근거 없으면 abstain=VUS) 아래 제시한다. 세 arm — Generative LLM(gpt-4o-mini + self-consistency voting + 에이전트형 verifier), 방향-인식 Deterministic rule, 별도의 인용 가능 VICC 점수기반 rule — 을 56변이 5-cancer TCGA 코호트(충실성, leakage-free)와 외부 70변이 Horak 2022 전문가 gold standard(정확도)에 대해 평가한다. 명시된 기여는 방법론적이 아니라 평가적·응용적이다: 검색 grounding이 해석기를 충실·감사가능하게 만들고, 확신에 찬 parametric over-calling을 억제하며, (temporal-holdout, leave-own-evidence-out, second-model, embedding 통제로) leakage 산물이 아님을 보이고, 검정력 있는 정확도 연구는 명시적으로 후속으로 미루며 그 설계를 제시한다.

---

## Major points (주요 지적)

1. **"faithful by construction"의 정의적 경계를 인정하라.** 가장 강한 충실성 수치(hallucination 0, grounding/directional/abstention 1.0; Fig 1c)는 부분적으로 *게이트가 강제*한 것이지 발견된 것이 아니다 — 검색되지 않은 식별자를 일절 안 내는 시스템은 정의상 fabrication 0이다. 진정으로 경험적·반증가능한 발견은 *게이트 이전* 동작이다: RAG arm이 out-of-bundle 인용 0/106, 비검색 arm이 26/56(0.464, 95% CI 0.339–0.589, 0 배제)에서 fabricate. 원고는 "by construction"을 말하지만 게이트 이후 1.0/0%를 abstract·Fig 1c에 전면화한다. *수정:* abstract와 §3.1에서 게이트-이전 경험적 수치를 앞세우고 1.0/0%를 계약이 제공하는 보장으로 명시; 18.9%(20/106) 출처-범주 imprecision을 정직한 측정 잔차로 부각 — 논문에서 가장 정보량 큰 충실성 수치다.

2. **generative arm vs VICC-rule arm 분리를 빈틈없게(의사결정-결정적 수정).** abstract를 훑는 독자는 "LLM 시스템이 0.843에 도달하고 OncoVI를 따라잡는다"고 받아들인다. 아니다 — *결정론적 rule arm*이며, LLM이 아니고 신규성 주장도 아니다. 분리가 서술되어 있으나 abstract·§3.3·Fig 1·Fig 5(“Ours … 0.843”을 한 행으로 나열, 어느 arm인지 흐림)에서 강제되지 않았다. *수정:* abstract와 §3.3의 0.843 첫 등장에 "결정론적 rule 엔진이며 LLM이 아니고 신규 분류기 주장 아님" 명시; §3.3을 generative(충실성 우선) 결과가 rule arm보다 먼저 오도록 재배열; Fig 1/Fig 5의 각 정확도 셀을 산출 arm에 귀속. "OncoVI 대등"은 비유의 McNemar(p=0.66)에 근거하므로 "더 높은 특이도에서 통계적으로 구별 불가한 정확도"로 진술하고, OncoVI가 자기 홈셋(Horak-70)에서 채점됨을 앞으로 끌어오라.

3. **잠정 판정의 *방향*을 전달하라.** "21.4%(12/56) over-call→VUS" 재분류에는 "행동적 변화이지 검증된 정확성 아님" 단서가 있어 좋으나, 저자들 자신의 잠정 판정 기록은 검토된 3개 "beyond-rules" 사례에서 rule이 2/3 옳음(PTEN R130*·PIK3CA R88Q는 과보수적 LLM abstention; ESR1 E247K는 LLM 우세)을 발견했고, 이는 문서화된 VUS-과잉해소 한계를 *강화*한다. 프로젝트 자체의 잠정 검토가 억제의 정확성에 불리한데 "판정 대기"에 기대선 안 된다. *수정:* §3.2/Limitations에 예비(비전문가-미서명) 검토가 여러 재분류를 과보수적 abstention으로 시사함을 진술 — 정직성을 강화함 — 하되, 어떤 보드 인증 병리학자도 서명하지 않았음을 명시.

4. **모든 VICC-arm 0.843에 CI 병기, "non-inferior" 표현 규율.** n=70에서 0.843 CI가 넓으니 generative arm처럼 점추정치에 동반해야 한다. 또 "non-inferior"는 사전 지정 margin 대비 검정이 아니라 겹치는 CI의 구어적 해석(McNemar p=1.0 vs no-RAG, p=0.61 vs rule)이다. *수정:* margin을 사전 지정하거나 "comparable / 유의차 없음"으로 재진술.

5. **관련 보고지침 준수.** 진단정확도 + 예측모델 연구인데 **TRIPOD-AI**도 **STARD** 렌즈도 인용·준수되지 않는다. *수정:* "Reporting" 단락 추가; variant flow diagram(후보 398 → 분류 56; Horak 70; OncoVI 69 공유; ClinVar 458)과 명시적 "intermediate result(VUS/abstention)" 처리; knowledge-snapshot 시점/버전 표; 구조화 model card(모델/버전, temperature, voting n, verifier, 스냅샷, 재현 모델); EZH2/PTEN 얇은-커버리지가 감사 가능하도록 유전자별 정확도/abstention 표.

---

## Minor points (사소 지적)

1. **gpt-4o-mini 주 모델**은 preprint로서 충분히 정당화됨(코호트 규모 비용; 보수적 능력 하한; 결론 불변의 gpt-4o 재현 0.70 vs 0.60, p=0.21). 상위 venue는 multi-family 스윕(Llama/Mixtral)을 원할 것이니 한계로 앞에 명시하라.
2. **코호트 선택**(56/398, AlphaMissense-only·무근거 변이 상한)은 비용 통제로 공개됨; 정확한 계층적 선택 규칙을 재현 가능하게 기술해 showcase-편향으로 읽히지 않게(BRAF V600E는 설계상 포함).
3. **다중 모델 POC**가 Discussion에 새 정량 결과(평균 일치도 0.929; 44/56 만장일치; 25% abstention)를 도입. Results-with-caveats로 승격하거나 한 문장으로 압축; Discussion의 새 발견은 구조적 약점.
4. **그림:** Fig 3b의 ClinVar-OOD 작동점(AUROC 0.902)이 시각적으로 무엇인지 명확화 — 다른 데이터셋의 곡선 밖 단일 마커라 곡선 위로 오독될 수 있음; Fig 5 행을 분리/주석해 rule-arm 정확도/특이도 셀과 시스템 인용-정확도 셀이 섞이지 않게. AUROC 0.902가 등장하는 곳마다 ClinVar 단서(benign recall 0; 균형 3-class 0.505)를 유지.
5. **Leakage 뉘앙스:** LOVO가 자기-근거 leakage는 통제하나 잔기-이웃 leakage는 통제 안 함(same-gene/same-residue 근거가 정답을 새게 할 수 있음)을 명시.
6. **지표:** 미래 검정력 연구에 스스로 권한 대로 quadratic-weighted κ / macro-F1을 주 ordinal 지표로 고려.
7. **자리매김:** "선행 연구 중 leakage-통제 정확도 평가 + leakage-free 충실성 감사를 함께 보고한 사례 없음" 주장은 그럴듯하고 진짜 기여다; 동시기 연구 2건([16],[17])이 이미 인용됐으니 날짜를 명시하라.
8. **하우스키핑(거버넌스, QA 아님):** "Lin 2025 RAG" 인용 정정에 관한 독자용 내부 주석 제거, placeholder repo URL과 "[to confirm]" 소속을 게시 전 해결.

---

## 항목별 점수

| 항목 | 점수 (1–5) | 근거 |
|---|---|---|
| 중요성 / 독창성 | **3.5** | 변이 해석의 "구성상 충실 + leakage-통제 평가" 프레이밍은 진정·시의적절한 틈새; 구성요소(하이브리드 RAG, 인용 가능 VICC rule, abstention)는 개별 선행연구이며 신규성 주장 안 함이 옳다. 중요성은 평가 엄밀성 — 실질적이나 점진적. |
| 방법 타당성 | **4** | 방향-인식 rule(허수아비 아님), 강제 enum, 오프라인 재현성, 4개 직교 leakage 통제. single-sample/단일-주모델 설계와 작은 n이 상한. |
| 통계 타당성 | **4** | bootstrap CI + exact McNemar가 정확도 비교마다 적용; 비우월 프레이밍 정직. 미흡: non-inferiority margin 미지정; VICC-arm 0.843이 때때로 CI 없이 보고. |
| 재현성 | **4.5** | 공개 JSON 산출물이 헤드라인 수치를 spot-check로 뒷받침; 결과별 스크립트 명시; 오프라인 스냅샷; 결정론적 anti-fabrication 게이트. (repo URL placeholder.) |
| 명료성 | **3.5** | 우수한 글쓰기지만 generative-vs-rule arm 혼재(abstract, §3.3)가 실제 이해 위험이고 Discussion이 Results와 일부 중복. |
| 그림 / 표 | **4** | CI·McNemar p 표기; 오해 유발 시각 우위 없음. 실질 쟁점은 귀속/명료성(Fig 5 행, Fig 3b OOD 지점). |

**종합 권고: Major revision.   심사자 확신도: 4/5 (높음).**

---

## 보고지침 노트

가장 관련된 도구: **TRIPOD-AI**(예측모델 보고)와 **STARD** 진단정확도 렌즈(Horak/ClinVar 평가는 전문가 참조표준 대비 분류-정확도 연구). 현재 둘 다 미인용. 저자가 추가할 누락/부분 항목: 참여자/변이 **흐름도**; 명시적 **intermediate-result(VUS/abstention) 처리**; 단일 **knowledge-snapshot 시점/버전** 표; 구조화 **model card**; 앞부분 **표본크기 한계**; 표준형 **calibration** 보고; **유전자별/암종별 하위집단** 정확도/abstention. Major 5 참조.

---

## 편집자에게 보내는 비공개 코멘트

응용 시스템과 비정상적으로 엄밀한 충실성/leakage 평가를 보고하는 견실하고 정직한 preprint 등급 원고. 과학은 타당하고 공개 산출물이 헤드라인 수치를 spot-check로 뒷받침하며, 충실성/감사가능성 핵심 주장은 견고해 수정을 견딘다. 의사결정-결정적 이슈는 과학적 오류가 아니라 표현상 위험 — 매우 다른 두 정확도 영역(완만·비우월 generative LLM, OncoVI를 따라잡는 강한 결정론적 rule 엔진)이 rule arm의 강한 수치로 LLM 시스템에 halo를 드리우게 프레이밍됐고, "faithful by construction" 헤드라인의 부분적 정의성이 이를 가중. 재구성·명시적 분리로 해결 가능.

심각도: 중간. fabrication·통계 부정 없음; limitations가 통상보다 솔직. 신규성은 점진적(구성요소는 선행연구; 기여는 평가 프레이밍)이며 preprint·방법론 venue에 적절하나, 최상위 저널은 저자들이 직접 제시한 검정력 있는 multi-family 후속 없이는 n=70 규모와 단일-주모델 설계를 빈약하다 볼 수 있다. 귀속 수정을 강제하는 major revision 후 수용을 지지하며; preprint에는 새 실험 불필요. 거버넌스: 미해결 소속/IP placeholder, 제품명, 저장소 URL을 게시 전 확정하고, 어떤 독점(고용주) 데이터/로직도 포함되지 않았음을 확인해야 한다.

---

*심사자가 신규성/자리매김 평가에 참조한 선행연구:*
- OncoVI (Carta et al., medRxiv 2024) — 93변이 guideline 셋에서 정확도 80% / 민감도 88%: https://www.medrxiv.org/content/10.1101/2024.10.10.24315072v1
- Lin et al. 2025, npj Precision Oncology 9(1):141 — over-classification 발견: https://www.nature.com/articles/s41698-025-00935-4
