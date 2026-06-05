# 논문 작업을 위한 Agent / Skill 운영 (스터디 핸드아웃)

*혼자 쓰지 말고 **오케스트라처럼** 쓰기 — 역할을 가진 여러 에이전트·스킬·메모리로 분업하고, 적대적으로 검증하고, 배운 걸 도구에 되먹인다.*

사례: 이 저장소의 체세포 변이 해석 프리프린트(EN/KO)를 작성·검토한 실제 세션들.

---

## 0. 세 단어로

- **Agent = 누가 한다** — 별도 컨텍스트를 가진 독립 작업자. 큰 하위작업을 위임하거나, 병렬로 띄우거나, *적대적 검증*에 쓴다.
- **Skill = 어떻게 한다** — 재사용 가능한 절차·체크리스트(코드가 아니라 글로 박아둔 "이 작업의 비타협 규칙").
- **Memory = 지난번에 뭘 배웠나** — 세션을 넘어 지속되는 사용자 선호·프로젝트 상태·교훈. 반복 실수를 막는다.

> 사람은 *판단*에 집중하고, 정확성·일관성·검증의 반복 노동은 도구에 맡긴다.

---

## 1. 왜? — "혼자 쓰기"의 전형적 실패

1. **정확성** — 숫자를 기억에서 적다가 틀린다(예: 같은 지표라도 n=69 vs n=93에서 값이 다른데 혼동).
2. **일관성** — 그림 번호·캡션·본문 참조가 어긋난다(본문은 Figure 5인데 파일은 옛 이름).
3. **그림** — 기본 matplotlib 출력은 "PPT 슬라이드"처럼 보인다(밀도·정합·잘림).
4. **리뷰** — 자기 글의 약점(과대주장·사족·누락)이 안 보인다.
5. **범위 혼동** — 검토 단계에서 "사전 QA(인용·숫자·그림 점검)"와 "본질적 과학 판단"을 섞어버린다.

→ 각각을 **전담 도구**에 맡기면 사람은 의사결정에 집중할 수 있다.

---

## 2. 이 저장소의 실제 카탈로그

도구는 두 곳에 산다: **프로젝트 전용**(`.claude/agents/`, 이 repo에서만) vs **전역 재사용**(`~/.claude/agents/`, `~/.claude/skills/`, 모든 프로젝트).

### Agent (역할자)

| Agent | 위치 | 역할 | 언제 |
|---|---|---|---|
| **research-methodologist** | 전역 | 가설·기여·실험/평가 설계, 통계·leakage 엄밀성 감사 | 착수·설계 |
| **literature-scout** | 전역 | 선행연구 발굴 + 정직한 포지셔닝 + 인용 | related work / 주장 근거 |
| **novelty-strategist** | 전역 | 선행연구 지도 + 스쿱체크 + 차별화 각도 제안 | 주장 확정 전 |
| **manuscript-writer** | 프로젝트 | 초안·섹션·그림 생성(결과 JSON에서) | 프로즈 필요 시 |
| **variant-analysis** | 프로젝트 | 분석 파이프라인·평가 수트 실행/확장 | 실험 |
| **variant-adjudicator** | 프로젝트 | 특정 변이 판정(잠정, 사람 확인 전제) | discordant 사례 |
| **frontend-dev / backend-dev** | 프로젝트 | 대시보드·리포트 UI / 파이프라인·데이터·테스트 | 데모 그림·코드 |
| **design** | 전역 | 로고·브랜드 마크(SVG) | 아이덴티티 |
| **paper-critic** | 전역 | **내부** 적대적 사전리뷰 + 그림 레이아웃 QA → 수정 목록 | 제출/공개 전 |
| **reviewer** | 전역 | **외부** 정식 저널 referee 리뷰 시뮬레이션 | 내부 패스 통과 후(선택) |
| **paper-orchestrator** | 프로젝트 | 멀티-에이전트 워크플로 **계획**(실행 아님) → 단계 DAG·게이트·Workflow 스크립트 | 큰 작업 착수 전 |
| **presenter** | 프로젝트 | 원고 → 슬라이드 덱·발표노트(청중별) | 발표 자료 필요 시 |

> **오케스트레이터 주의:** 서브에이전트는 다른 서브에이전트를 못 띄운다(중첩 불가). 그래서 `paper-orchestrator`는 *실행자가 아니라 계획자*다 — 계획을 내면 **메인 세션 또는 Workflow 도구**가 그 계획대로 에이전트를 띄워 실행한다.

### Skill (절차·규율)

| Skill | 무엇 | 핵심 규율 |
|---|---|---|
| **scientific-writing** | IMRAD 프로즈 작성 | 불릿 아닌 문단, 보고지침(STROBE 등) |
| **journal-fit** | 대상 저널 하우스스타일 맞춤 | 섹션순서·초록형식·그림예산을 *파라미터*로 |
| **manuscript-figures** | 그림 세트 규율 | 데이터에서 생성·언급순 번호·**시각 QA**·밀도 |
| **scientific-visualization / matplotlib** | 출판급/저수준 작도 | 컬러맹 안전·벡터·컬럼폭 |
| **statistical-analysis / statsmodels** | 검정 선택·보고 | CI·검정·가정 점검 |
| **citation-management** | 인용 검증·BibTeX | DOI/메타데이터 정합 |
| **literature-review** | 체계적 문헌검색 | 다중 DB·검증 인용 |
| **benchmark-sota** | SOTA에 밀리지 말 것 | 최강 도구와 정면 비교 |
| **peer-review / scholar-evaluation** | 형식 리뷰/정량 평가 | 체크리스트·루브릭 |
| **research-lookup** | 최신 정보 조회 | 근거 검색 |
| **project-handoff-checkpoint** | 상태 보존 | HANDOFF/TODO 갱신 |

> Agent는 "가서 X 해라", Skill은 "X는 이렇게 하는 거다". 에이전트가 작업하면서 스킬을 자동으로 끌어 쓴다.

### Memory (세션을 넘는 학습)

이 프로젝트에 실제 적립된 규칙들(예):

- **완료 과대주장 금지** — 하위작업·서버 단계 남았는데 "done" 금지; 완료/진행/대기/블록을 구분.
- **여러 요청 = 각각 보고** — 사용자가 여러 건을 던지면 항목별 상태로.
- **반-조작 교훈** — 변이 수치는 기억이 아니라 JSON/Crossref/ClinVar에서 검증.
- **내부 PM 문서는 보조자료 아님** — HANDOFF/TODO/STUDY_SUMMARY/devlog를 외부 리뷰·원고의 "supporting material"로 인용 금지.
- **리뷰어 calibration(혼합)** — `reviewer` 출력 형식 = 생의학 referee 산문 + OpenReview식 점수표(실제 오픈 피어리뷰 벤치마킹).

---

## 3. 표준 논문 워크플로

```
research-methodologist (설계)
        │
literature-scout / novelty-strategist (선행연구·스쿱·차별화)
        │
variant-analysis (실험·평가 수트 실행)
        │
manuscript-writer (초안 + 그림)  ──[skill] scientific-writing / journal-fit
        │                          ──[skill] manuscript-figures / scientific-visualization
        │
paper-critic (내부 적대적 리뷰 + 그림 QA) ──▶ 수정
        │
[gate] verify_manuscript (결정론적 숫자·인용 재검증)
        │
reviewer (외부 referee 리뷰, 선택) ──▶ 추가 수정
```

병렬화: 의존성 없는 작업은 동시에 띄운다(예: "그림 벤치마크 리서치"와 "대시보드 리빌드"를 함께). 결과만 회수해 사람이 판단.

---

## 4. 핵심 사상 ① — 자기개선 루프

```
   생성 ──▶ 적대적 critic ──▶ 수정 ──▶ 교훈을 skill/agent/memory에 등록
    ▲                                              │
    └──────────────  다음엔 안 틀림  ◀─────────────┘
```

- 그림에 글자 겹침/잘림 발견 → paper-critic 그림 QA로 수정 → **그 결함 패턴을 manuscript-figures 스킬에 등록** → 다음 논문에선 처음부터 점검.
- 즉 **도구가 매 실수마다 똑똑해진다.** 메모리는 "장기 협업자"의 기억 역할.

---

## 5. 핵심 사상 ② — 내부 검토(critic) vs 외부 리뷰(reviewer)를 분리

이번 작업에서 가장 크게 정리된 부분. 둘은 **역할이 다르다.**

| | **paper-critic (내부)** | **reviewer (외부)** |
|---|---|---|
| 목적 | 제출 전 고치기용 적대적 triage | 저널 referee가 실제 제출하는 심사 |
| 자세 | "다 뒤져서 결함 찾기" | "**사전 QA는 됐다 전제**, 본질만 판단" |
| 다룸 | 과장·누락 baseline·통계 결함·leakage·**재현성·그림 시각 QA·수치 vs JSON 대조·인용 점검** | 신규성/포지셔닝, 방법 타당성, 통계, 프레이밍 공정성, over-claiming, venue 적합성 |
| **안** 다룸 | — | **인용 정확성/완전성, 그림 렌더링, 수치-출처 기계적 대조, 참고문헌 충실성** (전부 사전 QA) |
| 산출 | 우선순위 수정 목록 | 권고(accept/revise/reject) + 점수 + 저자용/편집자용 코멘트 |

**왜 중요한가:** "출처/숫자/그림이 제대로 되어 있는지"는 **당연히 끝냈어야 할 사전 작업**이지, *외부 심사자가 리뷰에 적을 내용이 아니다.* 실제 referee는 본질적 과학 판단만 한다.

**2단계 운영:**
1. **내부 패스** = `paper-critic` + `verify_manuscript` 게이트 + `citation-management`/`literature-scout` + 그림 QA → **여기서 기계적 점검을 전부 끝내고 수정.**
2. **외부 패스** = `reviewer` → 사전 QA 완료를 전제하고 **본질적 판단만** 담은 referee 리포트.

→ 검증 방법: `reviewer`를 **실제 오픈 피어리뷰로 벤치마킹**했다. eLife(Reviewed Preprint), OpenReview/ICLR, F1000Research의 실제 referee 리포트를 받아 비교 → 세 곳 모두 "논문 재진술 → 본질 판단 → 권고" 구조이고 **사전 QA를 하지 않음**을 확인. 이를 근거로 `reviewer`의 출력 형식을 **생의학 referee 산문 + 점수표 혼합**으로 고정.

> 교훈: 스코프를 안 박아두면 외부 reviewer가 *내부 critic처럼* 전수 점검(QA)으로 흘러간다. 도구의 **역할 경계**를 정의에 명시해야 한다.

---

## 6. 운영 원칙 (체크리스트)

- **검증 게이트**: 모든 헤드라인 수치는 결정론적 스크립트(`verify_manuscript`)로 재계산·대조. 사람·LLM 기억을 믿지 않는다.
- **반-조작**: 인용·숫자는 1차 출처/JSON에서 확인. "같은 모델로 다시 검토"는 자기 환각을 못 잡는다 → 결정론 게이트 + 다른 엔진 + 사람.
- **항목별 보고**: 여러 요청은 각각 상태(완료/진행/대기/블록)로.
- **과신 금지**: critic·reviewer도 틀린다. 적대적 다수결·재현으로 교차검증.
- **비용 감각**: 큰 위임만 에이전트(병렬·반복은 토큰을 쓴다), 작은 건 직접.
- **사람이 최종 판단**: 도구는 초안·검증·일관성. 과학적/임상적 책임은 사람.

---

## 7. 재사용 플레이북 (다음 논문에 그대로)

1. **research-methodologist**로 가설·기여·평가 설계 잡기.
2. **literature-scout / novelty-strategist**로 선행연구·스쿱·차별화 점검.
3. 실험(**variant-analysis** 등) → 결과 JSON 확정.
4. **manuscript-writer** + (`scientific-writing`/`journal-fit`) 초안, (`manuscript-figures`) 그림(데이터에서·언급순 번호).
5. **내부 패스**: `paper-critic`(프로즈+그림 QA) + `verify_manuscript` 게이트 + `citation-management` → 전부 수정.
6. **외부 패스(선택)**: `reviewer`(혼합 형식, 본질-only) → referee 리포트 → 추가 수정.
7. 발견된 결함 패턴을 **skill/agent/memory에 등록**(자기개선).
8. EN 확정 후 번역본 동기화(그림·번호 일괄 재배선).

---

## 8. 한 장 요약

> **논문 쓰기 = 오케스트레이션.**
> (1) 역할 가진 에이전트로 분업 · (2) 표준 절차는 스킬로 · (3) **내부 검토(QA)와 외부 리뷰(본질)를 분리** · (4) 적대적으로 검증 · (5) 배운 걸 도구에 되먹이고 · (6) 사람은 판단에 집중.

*발표용 슬라이드: [../talk_agent_skill_paperwriting_ko.md](../talk_agent_skill_paperwriting_ko.md)*
