# 국제 규제 기준 — 원문 확보와 원고 인용 앵커

작성: 2026-08-08. 목적: 원고(국제 저널 투고본)에 인용할 규제 근거를 **FDA와 국제 표준으로만** 세운다.
식약처 안내서-1511-01 분석([README.md](README.md))은 **개념 도출용 내부 자료로만 쓰고 원고에서 인용하지 않는다.**
아래 6건은 모두 2026-08-08에 원문 PDF를 내려받아 해당 대목을 직접 대조했다.

## 확보 상태 (전건 원문 대조 완료)

| # | 문서 | 발행 | 상태 | URL |
|---|---|---|---|---|
| A | FDA, *Clinical Decision Support Software* (Guidance for Industry and FDA Staff) | **2026-01-29** 재발행 (2026-01-06판 대체, 그 판이 2022-09판 대체) | 최종 | `fda.gov/media/109618/download` |
| B | FDA, *Marketing Submission Recommendations for a Predetermined Change Control Plan for AI-Enabled Device Software Functions* | **2025-08-18** 갱신 (원발행 2024-12-04) | 최종 | `fda.gov/media/166704/download` |
| C | FDA, *AI-Enabled Device Software Functions: Lifecycle Management and Marketing Submission Recommendations* | 2025-01-07 | **초안** (2026-08 현재 미확정, FY2026 최종화 예정목록에 등재) | `fda.gov/media/184856/download` |
| D | FDA, *Total Product Lifecycle Considerations for Generative AI-Enabled Devices* (Digital Health Advisory Committee 회의 Executive Summary, 30면) | 2024-11-20~21 | 자문위 자료 | `fda.gov/media/182871/download` |
| E | FDA·Health Canada·MHRA, *Good Machine Learning Practice for Medical Device Development: Guiding Principles* (10원칙) | 2021-10 | 3개국 공동 원칙 | `fda.gov/media/153486/download` |
| F | Gallifant J, et al. *The TRIPOD-LLM reporting guideline for studies using large language models.* Nat Med 2025;31(1):60–69 | 2025-01 | 보고 지침 | doi:10.1038/s41591-024-03425-5 |

> **README의 "링크 소멸 3건"은 정정한다.** `media/182871`(문서 D)과 `media/109618`(문서 A) 모두 현재 정상 응답한다.
> 앞선 확인이 404로 잘못 판정한 원인은 curl 호출에서 `-o /dev/null`과 리다이렉트 처리가 겹친 것이었고, FDA가 media ID를 재배치한 것이 아니었다.
> 다만 `media/109618`이 이제 **2022년판이 아니라 2026-01-29판을 반환**하므로, 2022년판을 인용한 2차 출처는 그대로 쓸 수 없다.

## 개념 → 국제 기준 앵커 매핑

식약처 분석에서 얻은 관점을 원고에 넣되, 근거는 아래 국제 문서로 바꿔 단다.

| 원고 반영 항목 | 도출한 개념 (내부) | 원고에 실제로 인용할 국제 근거 | 대조한 대목 |
|---|---|---|---|
| (a) 평가변수 선택 정당화 | 획일적 성능 기준을 두지 않고 사용 맥락별로 평가변수를 개별 제시 | **D** 논의문항 1(d) + **F** TRIPOD-LLM | D: "Performance metrics will typically vary with device intended use." / F: 초록의 "task-specific performance reporting" |
| (b) dual-mode 규제 해석 | 있던 정보의 재배열인지 새 정보의 생성인지로 갈림 | **A** 21st Century Cures Act §520(o)(1)(E) 4개 기준, 특히 기준 4 | A: "intended for the purpose of enabling such health care professional to independently review the basis for such recommendations … so that it is not the intent that such health care professional rely primarily on any of such recommendations" |
| (b) 근거 제시 방식 | 근거를 사람이 되짚을 수 있게 제시 | **A** 기준 4 충족 권고 (c)·(d)항 | A: "provide a plain language description of the underlying algorithm development and validation"; 출력·라벨링이 "clinical practice guidelines with the date or version, published literature"를 식별해 제공 |
| (c) 사람 개입 미측정 공백 | 모델 단독 성능과 사람이 낀 성능을 나누어 확인 | **E** GMLP 원칙 7 + **A** 자동화 편향 문단 | E: "Focus Is Placed on the Performance of the Human-AI Team … rather than just the performance of the model in isolation." / A: "Automation bias is the propensity of humans to over-rely on a suggestion from an automated system … errors of commission … or omission" |
| (d)(e) 모델 교체 동등성·회귀 테스트 | 모델 세대교체는 핵심 성능이 허가 범위 안임을 확인하는 조건부 변경 | **B** PCCP 3부 구조 | B: Modification Protocol은 "verification and validation activities (including pre-defined acceptance criteria) for those modifications" 포함. 구성요소는 데이터 관리, 재학습, 성능평가, 갱신절차 |
| (d) 외부 모델 드리프트 감시 책임 | 외부 상용 모델 자체는 관리 대상 밖, 응용 제작자가 책임 | **D** + **E** 원칙 10 + **C** | D: 파운데이션 모델은 "generally not meant to have a specific medical device intended use"이나 이를 쓴 제품은 "may be the focus of FDA's device regulatory oversight"이고, 제작자가 모델 속성·구조·학습 데이터 정보를 얻기 어렵다고 명시 / D: "Postmarket performance monitoring … particularly because they are non-deterministic" / E 원칙 10: 배포 모델의 실사용 모니터링과 드리프트 관리 |
| (f) Provenance 확장 | 프롬프트·파라미터·가드레일 버전 고정 기록 | **B** Description of Modifications + 품질시스템 문서화 | B: 변경은 품질시스템에 따라 문서화해야 하고(21 CFR 820.30(i), 820.70(b)), Modification Protocol이 "data, test methods, analysis methods, and specified acceptance criteria"를 식별하도록 요구 |
| 환각의 임상적 중대성 | — | **D** | D: "hallucinations, particularly those that may appear to be authentic outputs to users, may present a significant challenge in certain health care applications where highly accurate, truthful information is critical." |

## 인용 시 주의

1. **문서 C는 초안이다.** 2026-08 현재 최종본이 아니므로 원고에서 "draft guidance"임을 명시하고, 확정 요구사항처럼 쓰지 않는다.
2. **문서 D는 가이던스가 아니라 자문위원회 논의자료다.** FDA의 확정된 입장이 아니라 "FDA가 논의에 부친 쟁점"으로 서술한다.
3. **문서 B는 LLM·파운데이션 모델을 명시하지 않는다.** 본문에 "foundation model", "large language model" 문자열이 없다(원문 전수 검색으로 확인). ML 일반에 대한 변경관리 틀이므로, VeriVar에 적용할 때는 "이 틀을 LLM 응용에 적용하면"이라는 유추임을 밝힌다.
4. **문서 A는 비의료기기 CDS의 제외 기준을 다룬다.** VeriVar가 그 기준을 충족한다거나 규제 대상이 아니라고 **판정하지 않는다.** research-only 선언을 유지하고 설계 논의의 참조로만 쓴다.
5. FDA 가이던스는 모두 "Contains Nonbinding Recommendations" 표시가 있다. 법적 구속력이 있는 요구사항으로 서술하지 않는다.

## 원고 참고문헌 항목 (등록 예정 번호 22~27)

```
22. U.S. Food and Drug Administration. Clinical Decision Support Software: Guidance for Industry and Food and Drug Administration Staff. Issued January 29, 2026 (superseding the January 6, 2026 issue). Docket FDA-2017-D-6569.
23. U.S. Food and Drug Administration. Marketing Submission Recommendations for a Predetermined Change Control Plan for Artificial Intelligence-Enabled Device Software Functions: Guidance for Industry and Food and Drug Administration Staff. Issued August 18, 2025 (originally issued December 4, 2024).
24. U.S. Food and Drug Administration. Artificial Intelligence-Enabled Device Software Functions: Lifecycle Management and Marketing Submission Recommendations. Draft guidance, January 7, 2025.
25. U.S. Food and Drug Administration. Total Product Lifecycle Considerations for Generative AI-Enabled Devices. Executive Summary for the Digital Health Advisory Committee Meeting, November 20-21, 2024.
26. U.S. Food and Drug Administration, Health Canada, Medicines and Healthcare products Regulatory Agency. Good Machine Learning Practice for Medical Device Development: Guiding Principles. October 2021.
27. Gallifant J, Afshar M, Ameen S, et al. The TRIPOD-LLM reporting guideline for studies using large language models. Nat Med 2025;31(1):60-69. doi:10.1038/s41591-024-03425-5
```

원문 PDF는 저장소에 커밋하지 않는다(README와 같은 방침). 재확보는 위 URL로 한다.
