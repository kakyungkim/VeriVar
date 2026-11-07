# HARNESS.template.md — 랩 구조 (Agent 하네스 지도) — 템플릿

*Designed by Ka-Kyung Kim, 2026 — a reusable paper-production harness, contributed as a scaffold.*

> 이 파일은 재사용 템플릿이다. `<FILL: …>`와 `<DOMAIN_ANALYSIS_AGENT>` 자리를 팀의 실제 주제·도구로 채워 팀 레포의 `docs/HARNESS.md`로 둔다.

이 문서는 팀의 `.claude` 하네스를 **하나의 연구 랩**으로 본 지도다.
각 agent는 직원이 아니라 **랩의 멤버(연구원)** 이고, 사람(+메인 루프)이 랩을 이끄는 **PI**다.
운영 규칙·라우팅·산출물 계약의 요약은 팀 `CLAUDE.md`의 *Agent routing & artifact contract* 에 둔다(`CLAUDE-routing.template.md` 참고). 이 파일은 그 확장판(멤버 명부 + 관계도 + JD)이다.

- 멤버는 **누가 일을 시작할지** 사람이 매번 지정하지 않아도, CLAUDE.md 라우팅표로 자연어 요청에서 배정된다.
- 멤버는 결과를 **대화에만 남기지 않고** 산출물 계약(아래)에 따라 파일로 넘긴다.
- `paper-orchestrator`는 *계획만* 짠다. 실제 멤버 호출(실행)은 PI/메인 루프가 한다 — subagent는 subagent를 못 부르기 때문.

---

## 1. 멤버 명부 (Roster)

재사용 멤버(아래 1~7, 8~9는 선택)는 그대로 두고, **주제별 분석 슬롯**(`<DOMAIN_ANALYSIS_AGENT>`)과 선택적 **검증 슬롯**(`<DOMAIN_VERIFIER_AGENT>`)만 팀이 채운다. 그림 생성은 **agent가 아니라 Skill/스크립트**라 별도 표기(그림 작업은 `manuscript-writer` agent가 소유).

| # | 멤버 | 소속 벤치 | 한 줄 역할 | 채움 여부 |
| --- | --- | --- | --- | --- |
| D | `<DOMAIN_ANALYSIS_AGENT>` | 분석실 | **(팀이 공급)** 주제별 분석/실험·eval·통계 실행/확장 | **FILL** |
| D2 | `<DOMAIN_VERIFIER_AGENT>` (선택) | 분석실 | **(선택)** 모호/경계 사례의 **잠정** 판정(전문가 사인오프 필요) | 선택 |
| 1 | `literature-scout` | 문헌·기획 | 선행연구 탐색·정직한 포지셔닝·related work | 재사용 |
| 2 | `novelty-strategist` | 문헌·기획 | 차별화 각도 + 가장 싼 입증 실험 제안 | 재사용 |
| 3 | `research-methodologist` | 문헌·기획 | 가설·기여문·실험설계, 누수/통계 감사 | 재사용 |
| 4 | `manuscript-writer` | 집필실 | 프리프린트/저널/블로그 본문·초안 작성 + 그림 연계 | **FILL**(경로 placeholder) |
| 5 | `presenter` | 집필실 | 슬라이드·발표·발제(청중 맞춤) | 재사용 |
| 6 | `paper-critic` | 심사·QA | 제출 전 적대적 자체검토 + 그림 시각 QA | 재사용 |
| 7 | `paper-orchestrator` | 코디네이션 | 멀티-agent 작업 **계획** 수립(실행은 PI) | 재사용 |
| 8 | `design` (선택) | 엔지니어링 | 로고·아이콘·브랜드·그림 미감(SVG/PNG) | 재사용 |
| 9 | `reviewer` (전역, 선택) | 심사·QA | 정식 venue 스타일 **공식 리뷰 문서** 작성 | 재사용 |
| S | 그림 생성 (Skill/스크립트, agent 아님) | 엔지니어링 | 결과 파일에서 그림 생성·번호 정합 | **FILL**(스크립트/스킬 지정) |

> ⚠️ 그림 생성은 Skill/스크립트로 두는 것을 권장한다. agent로 호출하면 실패한다. 그림은 `manuscript-writer` agent가 `<FILL: 그림 생성 스크립트/스킬>`을 실행해 만든다. 단순 재생성은 메인 루프가 직접 돌려도 된다(결정론적, 결과 파일에서 생성).

---

## 2. 관계도 (Org / collaboration chart)

```
                         PI = 사람 + 메인 루프
                    (호출·승인·공개 게이트 책임)
                              │
                    ┌─────────┴─────────┐
                    │  paper-orchestrator│  ← 계획만(실행 X)
                    └─────────┬─────────┘
                              │ "이 순서로 돌려라" (plan)
   ┌──────────────┬──────────┼───────────────┬──────────────┐
   ▼              ▼          ▼                ▼              ▼
 문헌·기획      분석실      집필실          심사·QA       엔지니어링
 ────────      ──────      ──────          ───────       ──────────
 literature-   <DOMAIN_    manuscript-     paper-critic  design(선택)
   scout        ANALYSIS_   writer         reviewer(선택) [그림 생성=
 novelty-       AGENT>      presenter       (그림 QA는     skill/스크립트,
   strategist  <DOMAIN_                     paper-critic)   run by writer]
 research-      VERIFIER_
   methodologist  AGENT>(선택)
```

### 일이 흐르는 표준 경로 (논문 생산 루프)

```
research-methodologist / literature-scout / novelty-strategist   (기획·근거)
        └─▶ <DOMAIN_ANALYSIS_AGENT> ──▶ <FILL: result files>      (분석·검증)
                 └─(모호 사례)─▶ <DOMAIN_VERIFIER_AGENT>           (잠정 판정, 선택)
        └─▶ manuscript-writer ──▶ <FILL: manuscript files>        (집필)
                 ║  그림 스크립트/스킬 ──▶ <FILL: figures dir>     (그림)
        └─▶ paper-critic ──▶ reviewer ──▶ <FILL: peer review>     (심사)
                 └─▶ (수정 반영) manuscript-writer
        └─▶ <FILL: verify gate> ──▶ presenter                     (검증→발표)
```

- `∥`/`║` = 병렬 가능, `└─▶` = 산출물 전달.
- **검증 게이트**(헤드라인 숫자 결정론적 재계산)와 **공개 게이트**(`<FILL: 소속/IP 등 공개 전 검토>`)는 PI가 통과시킨다.

---

## 3. 멤버별 JD (Job Description)

각 JD = 책임 / 입력 / 산출물 / 하지 않는 것(경계). 권위 있는 전체 정의는 각 `.claude/agents/<name>.md` 본문.

### 분석실

**`<DOMAIN_ANALYSIS_AGENT>`** — 주제별 분석 파이프라인 운영자 **(팀이 공급하는 단 하나의 슬롯)**
- 책임: 팀 주제의 데이터 수집/처리, 모델/실험, eval 스위트(성능·ablation·외부 벤치마크·누수 통제 split·통계·오류 분석)를 실행/디버그/확장.
- 입력: 커밋된 스냅샷, 분석 코드, 기존 결과 파일.
- 산출물: `<FILL: result files — 분석/통계 JSON 일체>`.
- 경계: 본문 프로즈는 쓰지 않는다(→ manuscript-writer). 통계가 뒷받침 안 하는 우월 주장 금지.

**`<DOMAIN_VERIFIER_AGENT>`** (선택) — 잠정 판정자
- 책임: 모호·경계·discordant 사례에 대해 근거 기반 **잠정** 판정.
- 산출물: 검증된 근거가 달린 판정 노트. 경계: 전문가 사인오프 대체 아님. 메모리 기반 값 날조 금지(1차 출처에서만 인용).

### 문헌·기획

**`literature-scout`** — 선행연구 탐색·포지셔닝. 산출물: related-work 섹션/레퍼런스. 경계: 새 실험설계는 research-methodologist 소관.

**`novelty-strategist`** — 차별화 전략가. 풍경 조사 + scoop 플래그 + 구체적 차별화 기여·가장 싼 입증 실험. literature-scout와 research-methodologist 사이.

**`research-methodologist`** — 방법론·감사. 거친 아이디어 → 가설·기여문·엄밀한 실험/평가 설계; baseline/ablation/metric; 누수·통계 사전 점검. 경계: 프로즈 작성·실행 안 함.

### 집필실

**`manuscript-writer`** — 본문 집필. 입력: **검증된 base(숫자를 메모리로 재유도 금지)** — 결과 요약 + 결과 파일. 산출물: `<FILL: manuscript files>`. 경계: 분석 실행 안 함. 통계 우월 주장 금지.

**`presenter`** — 발표물 제작. 완성/초안 매뉴스크립트 → Marp/reveal 덱·발표노트·청중 맞춤본. 모든 숫자·그림은 매뉴스크립트/결과 파일에서 인용. 경계: 논문 작성·그림 생성·리뷰 안 함.

### 심사·QA

**`paper-critic`** — 제출 전 적대적 검토자(내부). 과대주장·누락 baseline/ablation·통계 갭·누수·재현성·신규성 + **그림 시각 QA**(텍스트-그래픽 겹침, tofu, 잘림). 우선순위 fix 제시. QA를 소유.

**`reviewer`** (전역, 선택) — venue 스타일 권고·항목별 점수·리포팅 가이드라인 체크가 담긴 **실제 referee 리뷰 문서**. 경계: 사전 QA(번호·출처·그림 렌더)는 이미 끝났다고 가정(paper-critic 소관).

### 엔지니어링·제작 (선택)

**`design`** — 비주얼/브랜드(로고·아이콘·컬러·그림 미감), SVG 마스터 + 다중 PNG. 경계: 결과 기반 데이터 그림(→ 그림 스킬)·UI 코드 아님.

**그림 생성 (Skill/스크립트, agent 아님)** — 결과 파일에서 그림 생성·임베드·번호 정합(하드코딩 숫자 금지). agent로 호출하면 실패 — `manuscript-writer`가 스크립트/스킬로 사용.

### 코디네이션

**`paper-orchestrator`** — 연구 코디네이터(계획 전용). 목표+현 상태 → 실행 계획(+선택적 Workflow 스크립트). 경계: **직접 실행하지 않는다.** 계획을 PI가 실행.

---

## 4. 현재 하네스 상태 (성숙도 메모 — 팀이 채움)

| 항목 | 상태 |
| --- | --- |
| 멤버(agent) 정의 | `<FILL>` (재사용 7 + 도메인 슬롯 채움 여부) |
| 자연어 라우팅 | `<FILL>` (CLAUDE.md 라우팅표 적용?) |
| 산출물 계약 | `<FILL>` (파일 경로 검증?) |
| 입구(Orchestrator **Skill**) | `<FILL>` (orchestrator-SKILL 설치?) |
| 검증 게이트 | `<FILL>` (헤드라인 숫자 결정론적 재계산 스크립트?) |
| 개선 루프(improvement-log) | `<FILL>` (회고를 어디에 기록?) |

> 멤버가 일급이어도 **연결 조직(입구·라우팅·산출물 계약·검증 게이트·개선 루프)** 이 비면 성숙도가 낮다.
> 이 스캐폴드는 그 연결 조직을 함께 제공한다 — 도메인 분석 슬롯만 채우면 동작한다.
