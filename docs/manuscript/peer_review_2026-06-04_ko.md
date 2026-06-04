# 피어 리뷰 — "Citation-grounded retrieval for faithful LLM somatic variant interpretation"

**심사자(Reviewer):** (정밀종양학 / 임상정보학 분야 referee)
**날짜:** 2026-06-04
**원고:** `docs/manuscript/preprint.md` (bioRxiv preprint 초안)
**가정한 투고 등급:** JAMIA / npj Digital Medicine / Bioinformatics 급의 방법론·벤치마킹 저널

> 본 문서는 영문 리뷰 [peer_review_2026-06-04.md](peer_review_2026-06-04.md)의 한국어 번역본입니다. 리뷰는 R1–R7 수정을 적용하기 **이전** 원고를 기준으로 작성되었습니다.

---

## 1. 원고 요약

저자들은 두 개의 커뮤니티 표준(ClinGen/CGC/VICC 발암성[oncogenicity] 및 AMP/ASCO/CAP 임상 tier)에 따라 변이를 분류하는 dual-mode 체세포 변이 해석기를 제시한다. 분류는 하이브리드 인용-기반(citation-grounded) 검색 계층(구조화 지식베이스 조회, CIViC dense 검색, 지식 그래프)을 사용하며, 명시적인 "충실성 계약(faithfulness contract)" 아래 동작한다: 모든 주장은 검색된 식별자를 인용해야 하고, 변이-특이적 근거가 없으면 시스템은 abstain(VUS 부여)해야 한다. 세 개의 arm이 평가된다 — Generative LLM arm(gpt-4o-mini + self-consistency voting + 에이전트형 verifier), 방향-인식(direction-aware) Deterministic rule arm, 그리고 별도의 인용 가능한 VICC 점수기반(point-based) rule arm — 이를 56변이 5-cancer TCGA 코호트(충실성, leakage-free)와 외부 70변이 Horak et al. 2022 전문가 gold standard(정확도)에 대해 평가한다.

핵심 기여는 **방법론적이 아니라 평가적·응용적**이다: 검색 기반 grounding이 해석기를 *구성상(by construction)* 충실하고 감사 가능(auditable)하게 만들고(인용 fabrication 0% vs 비검색 시 46.4%), 확신에 찬 parametric over-calling을 억제하며(over-call 12/56가 VUS로 재분류), 어떤 정확도 효과도 leakage 산물이 아님(temporal-holdout, leave-own-evidence-out, second-model, embedding 통제)을 논한다. 정확도 주장은 의도적으로 절제되어 있다: generative arm은 *non-inferior*(우월이 아님)로 프레이밍되며, 별도의 인용 가능한 VICC rule arm은 Horak-70에서 3-class 정확도 0.843에 도달하고 open 엔진 OncoVI를 훨씬 높은 특이도(specificity)에서 대등하게 따라잡는다. 헤드라인은 임상 의사결정 지원의 전제조건으로서의 충실성/감사가능성이며, 검정력을 갖춘(powered) 정확도 연구는 명시적으로 후속으로 미루고 그 설계를 제시한다.

---

## 2. 종합 권고: **MAJOR REVISION (대폭 수정)**

비정상적으로 정직하고 잘 계측된 원고로, 프레이밍의 절제가 가장 큰 강점이다: 저자들은 정밀종양학-LLM 문헌이 빠지기 쉬운 과장(over-claiming)을 거듭 피하며, 내가 확인한 거의 모든 헤드라인 수치가 커밋된 결과 JSON과 정확히 일치한다(§6 상세). 충실성 격차는 실재하고 통계적으로 견고하며, leakage 통제는 내가 아는 어떤 유사 LLM-변이 논문보다 철저하고, 그림들은 깔끔하며 통계가 뒷받침하지 않는 효과를 시각적으로 암시하지 않는다.

그러나 아직 수용 가능하지 않으며, 그 이유는 (해결 가능하지만) 표면적이지 않은 세 가지다:

1. **헤드라인이 부분적으로 정의상 당연한(definitional) 것인데, 원고가 이를 충분히 인정하지 않는다.** "구성상 충실(faithful by construction)"이란, 가장 강한 충실성 수치(fabrication 0%, grounding/directional/abstention 1.0)가 부분적으로 *게이트가 강제한* 것이지 *발견된* 것이 아님을 뜻한다. 진정으로 경험적이고 반증 가능한 결과는 *게이트 이전(pre-gate)* RAG 동작(out-of-bundle 인용 0/106; 비검색 arm 대비 46.4%)이다. 논문은 이를 언급하지만, 이후 abstract와 Figure 1c를 게이트 이후의 "1.0 / 0%" 수치가 짊어지게 둔다. 이 순환성은 묻어두지 말고 드러내야 한다(Major 1 참조).

2. **가장 의사결정-결정적인 단 하나의 이슈: 서로 다른 두 정확도 영역(generative ≈0.60 non-inferior vs VICC rule 0.843 "SOTA-급")이 halo effect를 유발하는 방식으로 뒤섞여 있다.** 독자가 abstract를 훑으면 "LLM 시스템이 0.843에 도달하고 OncoVI를 따라잡는다"고 받아들이게 된다. 사실이 아니다 — 그건 rule arm이며, 그 arm은 명시적으로 *LLM이 아니고* *신규성을 주장하지도 않는다*. 분리가 서술되어 있긴 하나 abstract, Discussion, Figure 5(“Ours (VeriVar) 0.843”을 한 행으로 나열하며 어느 arm이 낸 수치인지 흐림)에서 충분히 강하게 강제되지 않았다. 이를 빈틈없게 만들어야 한다(Major 2 참조).

3. **잠정적(provisional)이고 비전문가-미서명(non-expert-signed) 판정(adjudication)이 가장 강한 행동적 주장의 해석에 새어든다.** 저자들 자신의 잠정 판정(원고의 잠정-판정 논의가 바탕으로 삼는 워크시트)은 AI-보조 판정이 "beyond-rules" 사례에서 rule이 2/3 옳았음을 발견했고 이것이 VUS-과잉해소(over-resolution) 한계를 *강화*함을 칭찬받을 만큼 명시한다. 원고는 "행동적 변화이지 정확성은 아님"이라는 단서를 유지하지만, 그 잠정적 발견의 *방향* — 검토된 사례들에서 over-call 억제가 부분적으로 과보수적(over-conservative) abstention이라는 점 — 은 전달하지 않는다. 이는 공정성(fairness) 문제다(Major 3 참조).

핵심 주장 — 충실성/감사가능성이 보장되며 결과가 leakage에 견고하다 — 은 수정을 **견뎌낼 것**이며, 나는 그러리라 본다. 수정은 새 실험이 아니라 귀속(attribution)의 정밀성과 정의적 경계의 인정에 관한 것이다. 따라서 reject가 아니라 major revision이다.

---

## 3. 항목별 점수 (1–5; 5 = 우수)

| 평가 항목 | 점수 | 근거 |
|---|---|---|
| 독창성 / 중요성 | **3.5** | 변이 해석에 대한 "구성상 충실 + leakage-통제 평가" 프레이밍은 진정성 있고 시의적절한 틈새다. 다만 시스템 구성요소(하이브리드 RAG, 인용 가능 VICC rule, abstention)는 개별적으로는 선행연구(ALCE, OncoVI, MedRAG)이며, 저자들도 방법론적 신규성을 주장하지 않는 것이 옳다. 중요성은 평가의 엄밀성에 있고, 이는 실질적이나 점진적(incremental)이다. |
| 방법론적 엄밀성 | **4** | 방향-인식 rule(허수아비[strawman] 아님), 강제된 enum, 오프라인 재현성, 4개의 직교적 leakage 통제, 결정론적 검증 게이트. 강하다. single-sample/단일-주모델 설계와 작은 n에 의해 상한이 제한된다. |
| 통계적 타당성 | **4** | bootstrap CI + exact McNemar가 정확도 비교가 등장하는 모든 곳에 적용됨. non-inferiority 프레이밍이 정직하고 CI/p-값이 본문, Table 1, 그림에 보고됨. 미흡점: 형식적 non-inferiority margin 사전 지정 없음; temporal-sweep 행에 CI 없음(공개됨); VICC-arm 0.843이 여러 곳에서 CI 없이 보고됨. |
| 재현성 | **4.5** | 모든 헤드라인 수치가 커밋된 JSON과 일치; 결과별 스크립트 명시; 오프라인 스냅샷; 결정론적 anti-fabrication 게이트. repo URL은 아직 placeholder. |
| 명료성 | **3.5** | 전반적으로 우수한 과학적 글쓰기지만, Results §3.3와 abstract의 generative-vs-rule arm 혼재는 실제 이해 위험 요소이며, Discussion이 길고 Results와 일부 중복된다. |
| 그림 / 표 | **4.5** | CI·McNemar p가 표기되고 그림이 효과를 과장하지 않음(오해 유발 시각적 우위 없음). 실질적 쟁점은 귀속과 명료성: Fig 5 행 라벨링과 Fig 3b의 ClinVar-OOD 지점에 설명 필요. |

---

## 4. 섹션별 코멘트

### Abstract
- 전반적으로 절제된 보고의 모범. 충실성, non-inferiority, McNemar p-값이 모두 명시됨.
- **문제:** VICC rule arm 결과("0.843 … OncoVI 대등 … 훨씬 높은 특이도")가 충실성 헤드라인과 거의 동등한 비중으로 제시되어, 빠르게 읽는 독자가 이를 LLM 시스템에 귀속시킨다. abstract에 이 arm이 *결정론적 rule 엔진이며 LLM이 아니고 신규 분류기로 주장되지 않는다*는 명시 문구를 추가하라 — §선행연구비교에서 한 동일한 단서가 그 수치가 처음 등장하는 곳에 나와야 한다.
- "추가로 인용의 18.9%가 정확한 변이 수준 식별자가 아니라 출처 범주만 지칭… 충실성 게이트가 이를 0%로 줄임" — 좋다. 다만 그 0%가 *게이트-강제*임을 (§3.1뿐 아니라) 여기서도 밝혀, 경험적 주장은 게이트 이전 0/106 out-of-bundle 수치임을 분명히 하라.

### Background and Significance
- 본 작업을 새 방법이 아니라 알려진 완화책의 응용으로 적절히 자리매김한다. 두 실패 모드(인용 hallucination + parametric leakage) 프레이밍이 명료하고 설계를 잘 동기화한다.
- 격차 진술("선행 변이-해석 연구 중 leakage-통제 정확도 평가와 leakage-free 충실성 감사를 함께 보고한 사례 없음")은 그럴듯하며 논문의 진짜 기여다. 다만 빠르게 변하는 분야이고 두 동시기(concurrent) 연구([16],[17])가 이미 인용되어 있으니, "To our knowledge" 류 주장에 날짜를 덧붙여 완화하는 것을 고려하라.

### Methods
- 데이터셋, 지식 소스, 검색 arm, 충실성 계약이 명확히 기술되어 보조 요약과 일치한다.
- **gpt-4o-mini를 주 모델로 사용**한 것은 *충분히 정당화됨*(코호트 규모 dual-mode + ablation 비용; 보수적 능력 하한; gpt-4o 재현 제공). preprint로서 방어 가능하고 정직하게 논증된 선택이다. 상위 저널 심사자는 여전히 (당신이 미룬) multi-family 스윕을 원할 것이다.
- 56/398 코호트 선택(AlphaMissense-only 및 무근거 변이 상한)은 비용 통제로 공개됨 — 좋다. 다만 정확한 선택 규칙(계층적 선택 기준)을 재현 가능하게 기술해, 코호트가 showcase 변이(BRAF V600E가 명시적으로 설계됨) 쪽으로 cherry-pick된 것으로 보이지 않게 하라.
- **보고지침 격차(§5 참조):** Methods가 외부 벤치마크를 진단정확도 평가로 프레이밍하지 않는다. STARD식 흐름(선별 n → 좌표 보유 n → 근거 검색됨 n → 분류됨 n)과 TRIPOD-AI식 model card를 추가하라.

### Results
- §3.1 충실성: 분모(44 vs 46 vs 56)가 신중히 설명됨. 좋다. 다만 이 섹션은 경험적 게이트-이전 수치를 *앞세우고* 1.0/0%를 게이트-강제로 명확히 표시해야 한다.
- §3.2 Ablation: 12/56(21.4%) over-call→VUS 재분류는 `ablation_report.json`에서 **정확히 재현 가능**(12개 전부 열거함). "행동적 변화이지 정확성 아님" 단서가 존재하고 반복됨. 잠정 판정의 *방향*(rule 2/3 옳음)이 누락됨 — Major 3 참조.
- §3.3 정확도: generative arm과 VICC-rule arm 결과가 뒤섞이는 지점. 소제목이 도움은 되나, 섹션이 "정확도 결과는 인용 가능 VICC rule arm이 짊어진다"로 시작해 generative arm 이전에 rule arm에 네 단락을 쓴다 — 논문 자신의 강조(충실성 우선, rule arm은 "정확도를 희생할 필요 없음"의 시연)를 뒤집는다. 재배열하거나 더 명시적으로 분리하라.
- §3.3 독립 일반화(ClinVar n=458): 여기서의 정직함은 모범적이다 — benign recall 0, 균형 3-class 0.505, AUROC는 onc-vs-rest로만. 이 단서를 두드러지게 유지하고 "AUROC 0.902"가 단서 없이 돌아다니지 않게 하라.
- §3.4 Leakage 통제: 철저하고 우위가 아니라 견고성으로 올바르게 해석됨. LLM parametric leakage가 여전히 미통제(비검색 floor로만 정량화)라는 명시 진술은 정확히 옳으며 그대로 유지하라.
- §3.5 Discordance: 모든 범주 카운트가 `discordance_analysis.json`과 일치. KRAS G12V 맥락-의존 사례는 잘 선택되었고 `analyses_report.json`과 일치.

### Discussion / Limitations
- Limitations가 정직하고 포괄적(완만한 절대 정확도, VUS 과잉해소, 희귀변이 얇은 커버리지, 미통제 parametric leakage, single-sample/single-model, 단순화된 deterministic baseline, 코호트 상한). 대부분의 투고보다 낫다.
- "검정력 있는 정확도 평가를 향하여" 소절은 진정 유용하며 저자들이 자기 연구가 무엇을 주장할 수 없는지 정확히 이해함을 보인다. 검정력 분석(0.05 이득에 수백 변이 필요)은 신뢰성 자산이다.
- 다중 모델 proof-of-concept(§Discussion)는 예비적이라고 적절히 분리되어 있으나 Discussion에서 *새 결과*(평균 일치도 0.929, 44/56 만장일치, 25% abstention)를 도입한다. 이를 단서와 함께 Results로 승격하거나 한 문장의 전향적 서술로 압축하라. Discussion의 새 정량 발견은 심사자가 짚을 구조적 약점이다.

### References
- "Lin 2025 RAG" 인용 정정에 관한 주석은 내부 provenance 메모로 읽히므로 **출판본에서는 제거해야 한다**(독자용 아님). placeholder repo URL과 "[to confirm]" 소속은 게시 전 해결해야 한다.

### Figures
- **Fig 1**(시스템 + 충실성 스코어카드): 깔끔. 다만 "VICC arm OncoVI 대비 벤치마크" 주석과 패널 (a)의 0.843이 다시금 rule-arm 정확도를 전체 시스템에 귀속시킬 위험.
- **Fig 2**(fabrication 0.46→0; 12/56 waffle; 계약 동작 1.0): 정확, CI 표기, 과장 없음. waffle plot이 정확히 12칸 채워짐.
- **Fig 3**(OncoVI head-to-head, ROC+OOD, 오류 비대칭, 민감도 다이얼): 모든 값이 JSON과 일치. **3b에서** "ClinVar OOD 작동점 AUROC 0.902"가 시각적으로 무엇을 뜻하는지 명확히 하라 — 단일 마커가 다른 데이터셋의 작동점을 나타내는데 독자가 곡선 위 점으로 오독할 수 있다.
- **Fig 4**(generative confusion, discordance 막대, cross-cancer): recall 값(0.79/0.37/0.71)이 `horak_results.json`과 일치. 좋다.
- **Fig 5**(capability landscape): 유용하나 "Ours (VeriVar) … 0.843 / 0.973 / 1.00" 행이 VICC rule arm의 정확도/특이도와 LLM 시스템의 인용 정확도를 한 행에 섞는다. 각 셀이 어느 arm에서 왔는지 분리하거나 주석하라. 또 제품명 "VeriVar"가 공개본 의도인지 확인하라.
- **S1–S3**: CI/p-값을 적절히 보고하고 시각적 과장이 없음; 실질적 우려 없음.

---

## 5. 보고지침 점검

이는 방법론·벤치마킹 + 진단정확도 연구다. 가장 관련된 두 도구는 **TRIPOD-AI**(예측모델 보고)와 **STARD** 진단정확도 렌즈(Horak/ClinVar 평가가 본질적으로 전문가 참조표준 대비 분류-정확도 연구이므로)이다. 현재 어느 것도 인용·준수되지 않는다.

**STARD식 항목 — 누락 또는 부분적:**
- 참여자/변이 **흐름도(flow diagram)** 없음(후보 398 → 분류 56; Horak 70; OncoVI-공유 69; ClinVar 458). 추가하라.
- 참조표준이 잘 명시됨(Horak 전문가 라벨) — 좋다.
- **불확정 결과(VUS/abstention)** 가 하나의 class로 처리됨 — 좋고 임상적으로 적절하나, STARD "intermediate result" 처리 결정으로 명시해야 한다.
- 지식 스냅샷의 **시점/버전**을 한 표로 보고하지 않음(Methods 곳곳에 흩어짐).

**TRIPOD-AI 항목 — 누락 또는 부분적:**
- **Model card**: 주 모델, 버전/날짜, temperature, voting n, verifier, 프롬프트 가용성 — 본문에 있으나 구조화된 표여야 한다.
- **표본 크기 정당화**: 주 연구에 대해 명시적으로 부재(이는 "powered evaluation" 절에서 인정됨, 좋다) — 다만 TRIPOD-AI는 이를 한계로 앞부분에 명시하기를 기대한다.
- **보정(calibration)**: voting-confidence 보정이 (§3.5) 서술적으로만 보고됨; 보정 그림이나 수치를 표준 형식으로 보고하라.
- **공정성/하위집단**: 유전자별·암종별 분해가 JSON(`analyses_report.json`)에 있음; EZH2/PTEN 얇은-커버리지 약점이 감사 가능하도록 유전자별 정확도/abstention을 표면화하라.

TRIPOD-AI + STARD를 인용하는 짧은 "Reporting" 단락과 흐름도를 추가하면 가정한 저널 등급에 대해 투고가 실질적으로 강화된다.

---

## 6. 고위험 지점에 대한 구체적 정밀검토 (요청에 따름)

**(a) 충실성 헤드라인은 진정 뒷받침되는가, 부분적으로 정의상 당연한가?**
**부분적으로 정의상 당연하며, 이를 인정해야 한다.** 경험적이고 반증 가능한 발견은: (i) RAG arm이 게이트 이전 out-of-bundle 인용 0/106을 냄; (ii) 비검색 arm이 26/56(0.464, 95% CI 0.339–0.589, 0을 배제)에서 fabricate함. 둘 다 `stats_report.json` 및 `eval_report.json`과 일치. 강하고 진정하다. 반면 게이트 이후 "hallucination 0 / grounding 1.0 / directional 1.0 / abstention 1.0"(Fig 1c)은 *계약-강제*다: 검색되지 않은 식별자를 일절 내지 않는 시스템은 정의상 fabrication 0이 된다. 원고는 그만큼("by construction") 말하지만 강제된 수치를 전면에 둔다. **수정:** abstract와 §3.1에서 게이트-이전 경험적 수치를 앞세우고, 1.0/0%를 측정된 결과가 아니라 계약이 제공하는 보장으로 명시적으로 라벨하라. 18.9%(20/106) 출처-범주 imprecision은 정직한 측정 잔차이자 당신이 가진 가장 정보량 큰 충실성 수치다 — 부각하라.

**(b) 작은 n과 non-inferiority 정직성 (56-코호트, 70-Horak).**
**정직하다.** CI와 exact McNemar가 정확도 비교가 등장하는 모든 곳(abstract, §3.3, §3.4, Table 1, Fig 4)에 보고됨. generative arm은 명시적으로 *non-inferior, 우월 아님*(McNemar p=1.0 vs no-RAG, p=0.61 vs rule)으로, `stats_report.json`(a_better 15/14, 9/6)과 일치. **다룰 단서:** (i) 형식적 non-inferiority *margin*이 사전 지정되지 않음 — 현재 "non-inferior"는 겹치는 CI의 구어적 해석이지 non-inferiority 검정이 아니다; "comparable / 유의차 없음"으로 완화하거나 margin을 지정하라. (ii) VICC-arm 0.843이 자주 CI 없이 보고됨; n=70에서 CI가 넓으니 generative arm에서 하듯 0.843이 등장하는 모든 곳에 동반해야 한다.

**(c) Leakage 통제 — 설득력 있는가? 잔여 parametric leakage가 인정되는가?**
**논문에서 가장 강한 부분 중 하나.** 4개의 직교 통제(pre-2012 temporal holdout, LOVO, gpt-4o, embedding) 모두 정확도를 통계적으로 불변으로 둔다; 값들이 `horak_temporal.json`, `horak_lovo.json`(0.614 vs 0.600, p=1.0), `horak_gpt4o.json`(0.70, p=0.21), `embed_ablation.json`과 일치. 결정적으로 원고는 **LLM parametric leakage가 여전히 미통제**이며 비검색 floor로만 정량화됨을 명시한다 — 정확하고 정직한 입장이니 유지하라. 한 가지 뉘앙스: LOVO 통제는 변이의 *자기* CIViC 근거를 제거하지만 same-gene/same-residue 근거는 여전히 정답을 새게 할 수 있다(rule arm에 대한 neighbour-inheritance를 언급함); LOVO는 자기-근거 leakage는 통제하나 잔기-이웃(residue-neighbour) leakage는 통제하지 않음을 명시하라.

**(d) VICC rule arm "0.843, OncoVI 대등, 높은 특이도" vs 완만한 generative 정확도 — 과장 없이 프레이밍됐는가?**
**대체로 그렇지만, 가장 약한 프레이밍 지점(Major 2).** 수치는 정확하다: `horak_vicc.json`은 0.843(5-class 0.643, AUROC 0.906, spec 0.973, sens 0.697); `oncovi_headtohead.json`은 69 공유에서 ours 0.841 vs OncoVI 0.797(McNemar p=0.664, 12 vs 9 only-correct), spec 0.972 vs 0.806. 오류-비대칭 논증(정직한 abstention 9건 vs 확신 over-call 9건, 대칭 카운트지만 비대칭 임상 위험)은 정당하고 잘 제시됐다. 위험은 순전히 *귀속*에 있다: 이 arm은 결정론적 rule 엔진이며 명시적으로 *LLM이 아니고 신규성도 주장 안 함*(OncoVI가 이미 기준을 근거에 매핑함을 인정). 어떤 독자도 0.843을 "LLM 시스템"에 귀속시킬 수 없게 하라. 또한 "OncoVI 대등"은 비유의적 McNemar(p=0.66)에 근거 — 즉 *구별 불가* — 이를 "더 높은 특이도에서 통계적으로 구별 불가한 정확도"로 진술하고, OncoVI가 자기 *홈셋*(Horak-70)에서 채점됨(어느 쪽도 유리하게 하지 않으나 공개해야 함; 당신은 future-work 절에서 함 — 앞으로 끌어오라)을 명시하라.

**(e) 12/56 over-call→VUS 재분류 — "행동적 변화이지 검증된 정확성 아님" 단서가 일관되게 적용되는가?**
**단서는 일관되게 존재하나, 잠정적 *방향*이 누락됨(Major 3).** 12개 변이가 `ablation_report.json`과 정확히 일치. "21.4%는 행동적 변화를 측정하지 정확성이 아님" 단서가 abstract, §3.2, Discussion에 등장. 그러나 저자들 자신의 잠정 판정 기록(원고의 잠정-판정 논의의 바탕 워크시트)은 검토된 3개 "beyond-rules" 사례에서 **rule이 2/3 옳았다**는 잠정 AI-보조 판정(PTEN R130* 및 PIK3CA R88Q: LLM이 과잉 abstain; ESR1 E247K는 LLM 우세)을 기록하며, 이는 명시적으로 *VUS-과잉해소 한계를 강화*한다. 프로젝트 자체의 잠정 검토가 over-call-억제의 정확성에 불리한 쪽으로 기우는데, "판정 대기" 뒤에 숨어선 안 된다. 검토된 사례들의 예비(비전문가-미서명) 검토가 여러 재분류가 과보수적 abstention임을 시사하며 이는 문서화된 VUS-과잉해소 약점과 일치함을 진술하라. 이는 논문의 정직성을 약화가 아니라 강화한다.

**(f) gpt-4o-mini를 주 모델로 — 충분히 정당화됐는가?**
**그렇다**, preprint로서: 비용(코호트 규모 dual-mode + ablation), 보수적 능력 하한, 결론을 바꾸지 않는 gpt-4o 재현(0.70 vs 0.60, p=0.21). 상위 저널은 여전히 multi-family 스윕(Llama/Mixtral)을 요청할 것이며, 당신은 이를 적절히 미룬다.

**(g) 잠정(비전문가-미서명) 판정 — 주장에서 제대로 분리됐는가?**
**원고 본문에서는 그렇다** — 어떤 정확성 주장도 판정 위에 세워지지 않았고, 워크시트가 근거로 인용되지 않는다. 유일한 격차는 그 *방향* 누락(점 e). 출판본에 전문가-검증된 정확성으로 읽힐 수 있는 진술이 **전혀** 없도록 하고, 어떤 보드 인증 병리학자도 판정에 서명하지 않았음을 명시하라.

**(h) 본문 수치 vs JSON — 발견된 불일치:**
모든 헤드라인 수치를 커밋된 JSON과 재계산/교차확인함. 발견:
- **모든 주요 수치 일치** — 충실성(0/46, 44/44, 10/10, 근거 있음에도 abstain 2건), 46.4% [0.339–0.589], 12/56, κ 값, Horak 3-class(0.557/0.586/0.600), McNemar(p=1.0; p=0.61), LOVO(0.614, p=1.0), gpt-4o(0.70, p=0.21), temporal(0.586/0.629/0.600/0.643), embedding(0.243/0.229/0.229), VICC(0.843, AUROC 0.906, spec 0.973, sens 0.697), OncoVI head-to-head(0.841 vs 0.797, p=0.664), ClinVar(n=458, AUROC 0.902, spec 0.967, sens 0.537), discordance 범주, cross-cancer, AlphaMissense 일치도 0.944(17/18), verifier(10 변경, 6 rule쪽/4 반대, 0.518→0.571). 탁월한 재현성이다.
- **사소 불일치 #1 (multimodel POC):** 원고(Suppl. §)는 "부분 불일치 12건"이라 하나 `multimodel_faithfulness_poc.json`은 임계값 0.66에서 `abstained: 14`(abstention_rate 0.25 = 14/56)를 보고. 56−44 만장일치 = 12지만 abstain = 14; "12 부분 불일치"와 "14 abstain"이 모두 느슨히 쓰임. 화해시켜라(만장일치=44, 부분=12, 그러나 abstention 규칙이 14건 abstain → abstention 규칙 vs 만장일치를 명확히).
- **사소 불일치 #2 (OncoVI 수치):** abstract/Table은 OncoVI 0.797(69-공유, head-to-head JSON)을, 본문 다른 곳과 `horak_vicc.json`의 `baselines.oncovi_3class`는 0.80(공개 full-93)을 사용. 각 집합에 대해 둘 다 정확하나, 매 인스턴스가 어느 집합인지 진술하라(대체로 함 — §3.6와 Table 2의 내부 일관성을 확인: Table 2 참조 행이 69 공유에서 OncoVI 0.797이라 함, 좋음).
- **사소 불일치 #3 (temporal full-corpus 지점):** 본문(§3.4)이 temporal-sweep full-corpus 지점(0.586)이 별도 re-embed/re-index 실행이라 주 파이프라인(0.600)과 다름을 올바르게 표시. 공개됨; 유지하라.
- 원고 본문에 **fabricate된 변이 미검출**(프로젝트 자체 게이트가 이전에 "TP53 Y220C" 실수를 잡았음; 올바르게 부재).

---

## 7. 저자에게 보내는 코멘트 (Comments to the Authors)

이것은 진정 신중한 작업이며, 정확도를 과장하기를 거부하는 절제는 원고의 미덕이다 — 이 하위 분야에서 마땅한 만큼 드물다. 충실성 격차는 견고하고, leakage 통제는 LLM 변이 해석에서 내가 본 가장 철저한 것이며, 당신의 수치는 대부분의 투고가 근접하지 못하는 수준으로 공개 산출물과 일치한다.

이를 "정직한 preprint"에서 "출판 가능한 방법론·벤치마킹 논문"으로 옮기려면 새 실험이 아니라 **귀속 정밀성**에 집중하라:

1. **"구성상 충실"의 정의적 경계를 인정하라.** 경험적 게이트-이전 수치(out-of-bundle 0/106; 비검색 46.4%, CI가 0 배제)와 18.9% 출처-범주 imprecision을 앞세우고, 1.0/0% 계약 동작을 측정된 창발 속성이 아니라 *게이트가 강제하는 보장*으로 명시하라.
2. **generative-arm vs VICC-rule-arm 분리를 빈틈없게 하라** — abstract, §3.3, Fig 1, Fig 5에서. 어떤 독자도 0.843 / "OncoVI 대등"을 LLM에 귀속시킬 수 없어야 한다. 첫 등장 시 VICC arm이 결정론적 rule 엔진이며 LLM이 아니고 신규성 주장 아님을 진술하라.
3. **잠정 판정의 방향을 전달하라.** 당신의 워크시트가 beyond-rules 사례에서 rule 2/3 옳음을 발견해 VUS 과잉해소를 강화한다. 그렇게 말하라; 이는 over-call-억제 주장을 약화가 아니라 신뢰성 있게 만든다.
4. **VICC-arm 0.843이 등장하는 모든 곳에 CI를 추가하라** — generative arm에서 이미 하듯이.
5. **STARD/TRIPOD-AI 보고 단락, 변이 흐름도, model card, 유전자별 분해를 추가하라.**
6. placeholder(소속, repo URL)를 해결하고, 독자용 reference-provenance 메모를 제거하며, §6(h)의 두 사소 multimodel/OncoVI 수치 불일치를 화해시켜라.

이 중 어느 것도 파이프라인 재실행을 요하지 않으며, 모두 한 번의 수정으로 도달 가능하다.

---

## 8. 편집자에게 보내는 비공개 코멘트 (Confidential Comments to the Editor)

이는 응용 시스템과 비정상적으로 엄밀한 충실성/leakage 평가를 보고하는, 견실하고 정직한 preprint 등급 원고다. 과학은 타당하고 재현 가능하다 — 나는 본질적으로 모든 헤드라인 수치를 저자의 커밋된 JSON 산출물과 독립적으로 화해시켰고 일치한다(12/56 재분류, 4개 leakage 통제, OncoVI head-to-head 포함). 충실성/감사가능성 핵심 주장은 견고하며 **수정을 견뎌낼 것**이다; 내 우려는 타당성이 아니라 귀속의 정밀성에 관한 것이다.

의사결정-결정적 이슈는 과학적 오류가 아니라 표현상의 위험이다: 원고는 매우 다른 두 정확도 영역(완만하고 명시적으로 non-inferior한 ~0.60의 generative LLM, 그리고 OncoVI를 따라잡는 0.843의 강한 결정론적 VICC rule 엔진)을 보고하는데, 현재 프레이밍이 rule arm의 강한 수치가 LLM 시스템에 halo를 드리우게 둔다. "구성상 충실" 헤드라인의 부분적 정의성과 결합하면, 부주의한 독자가 기여를 과대해석할 수 있다. 재구성과 명시적 분리로 해결 가능하다.

심각도: 중간. fabrication도, 통계적 부정도 없으며, limitations 섹션은 통상보다 솔직하다. 신규성은 점진적(구성요소는 선행연구; 기여는 평가 프레이밍)이며 이는 preprint 및 방법론·벤치마킹 저널에 적절하나, 최상위 저널은 저자들이 직접 제시한 검정력 있는 multi-family 후속 없이는 n=70 규모와 단일-주모델 설계를 빈약하다고 볼 수 있다. 귀속 수정을 강제하는 major revision 후 수용되는 것을 나는 편안히 받아들일 것이며; preprint에는 새 실험 라운드가 필요하다고 보지 않으나, 저널본은 더 큰 벤치마크의 덕을 볼 것이다.

편집자를 위한 거버넌스 메모 하나: 원고는 미해결 소속/IP placeholder와 제품명("VeriVar")을 담고 있다; 이들과 저장소 URL은 게시 전 확정되어야 하며, 저자는 어떤 독점(고용주) 데이터나 로직도 포함되지 않았음을 확인해야 한다 — 그들 자신의 문서가 이 경계에 적극적 주의를 기울이고 있음을 시사한다.

---

## 9. 우선순위 수정 목록

### 필수 (수용 전 반드시 해결)
1. **R1 — 충실성 주장을 부분적으로 게이트-강제로 분리**; 게이트-이전 경험적 수치를 앞세우고; 18.9% imprecision 잔차를 부각. (§Abstract, §3.1)
2. **R2 — generative-arm vs VICC-rule-arm 분리 강제** — Abstract, §3.3, Fig 1, Fig 5에서; rule arm이 결정론적이고 LLM이 아니며 신규성 아님을 진술; 0.843을 "LLM 시스템"에 결코 붙이지 말 것.
3. **R3 — 잠정 판정의 방향 추가**(beyond-rules에서 rule 2/3 옳음; 과보수적 abstention), 비전문가-미서명임을 명시 유지. (§3.2, Limitations)
4. **R4 — 모든 VICC-arm 0.843 등장에 CI 추가**; non-inferiority margin을 지정하거나 "non-inferior"를 "유의차 없음"으로 재진술. (§3.3, Table 1/2)
5. **R5 — 보고지침 준수:** STARD/TRIPOD-AI 단락, 변이 흐름도, model card, 유전자별 정확도/abstention 추가. (§Methods/Results)
6. **R6 — placeholder 해결**(소속, repo URL), 독자용 reference-provenance 메모 제거, Ferber [18] 서지 완전성 확인.
7. **R7 — 사소 수치 불일치 화해:** multimodel "12 부분 불일치" vs 14 abstain; 모든 OncoVI 0.797 vs 0.80 인스턴스가 변이 집합을 명시하게. (§Discussion/§3.6/Table 2)

### 선택 (강화되나 preprint에는 비차단)
8. **O1 — 다중 모델 POC 승격 또는 압축**: Discussion에 새 정량 결과를 도입하지 말 것.
9. **O2 — Fig 3b 명확화**(ClinVar-OOD 작동점은 곡선 밖, 다른 데이터셋) 및 Fig 5 셀별 arm 귀속.
10. **O3 — 정확한 계층적 코호트-선택 규칙 진술**, 56/398 선택이 감사 가능하고 showcase-편향으로 읽히지 않도록.
11. **O4 — LOVO가 자기-근거는 통제하나 잔기-이웃 leakage는 통제 안 함을 명시.**
12. **O5 — quadratic-weighted κ / macro-F1을 주 ordinal 지표로 고려**, 당신이 미래 연구에 스스로 권한 대로.

---

*심사자가 신규성/자리매김 평가에 참조한 선행연구:*
- OncoVI (Carta et al., medRxiv 2024) — 93변이 guideline 셋에서 정확도 80% / 민감도 88%: https://www.medrxiv.org/content/10.1101/2024.10.10.24315072v1
- Lin et al. 2025, npj Precision Oncology 9(1):141 — over-classification 발견: https://www.nature.com/articles/s41698-025-00935-4
