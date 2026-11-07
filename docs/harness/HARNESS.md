# HARNESS.md — 랩 구조 (Agent 하네스 지도)

이 문서는 LLM_Variant_Pipeline의 `.claude` 하네스를 **하나의 연구 랩**으로 본 지도다.
각 agent는 직원이 아니라 **랩의 멤버(연구원)** 이고, 사람(+메인 루프)이 랩을 이끄는 **PI**다.
운영 규칙·라우팅·산출물 계약의 요약은 [CLAUDE.md](../../CLAUDE.md) → *Agent routing & artifact contract* 에 있다. 이 파일은 그 확장판(멤버 명부 + 관계도 + JD)이다.

- 멤버는 **누가 일을 시작할지** 사람이 매번 지정하지 않아도, CLAUDE.md 라우팅표로 자연어 요청에서 배정된다.
- 멤버는 결과를 **대화에만 남기지 않고** 산출물 계약(아래)에 따라 파일로 넘긴다.
- `paper-orchestrator`는 *계획만* 짠다. 실제 멤버 호출(실행)은 PI/메인 루프가 한다 — subagent는 subagent를 못 부르기 때문.

---

## 1. 멤버 명부 (Roster)

프로젝트-로컬 멤버 12명(`.claude/agents/`) + 자주 협업하는 전역 agent 2명(`reviewer`, `presentation-architect`). `manuscript-figures`는 **agent가 아니라 Skill**이라 별도 표기(그림 작업은 `manuscript-writer` agent가 소유).

| # | 멤버 | 소속 벤치 | 한 줄 역할 | 도구 | 위치 |
| --- | --- | --- | --- | --- | --- |
| 1 | `variant-analysis` | 분석실 | 듀얼모드 파이프라인·eval·통계 실행/확장 | Bash, Read, Edit, Write, Grep, Glob | local |
| 2 | `variant-adjudicator` | 분석실 | discordant 변이의 **잠정** 판정(병리 사인오프 필요) | Bash, Read, Grep, Glob, Write, Edit, WebSearch, WebFetch | local |
| 3 | `literature-scout` | 문헌·기획 | 선행연구 탐색·정직한 포지셔닝·related work | WebSearch, WebFetch, Read, Write, Edit, Bash | local |
| 4 | `novelty-strategist` | 문헌·기획 | 차별화 각도 + 가장 싼 입증 실험 제안 | WebSearch, WebFetch, Read, Grep, Glob, Write | local |
| 5 | `research-methodologist` | 문헌·기획 | 가설·기여문·실험설계, 누수/통계 감사 | Read, Write, Edit, Bash, Grep, Glob, WebSearch, WebFetch | local |
| 6 | `manuscript-writer` | 집필실 | 프리프린트/저널/블로그 본문·초안 작성 | Read, Write, Edit, Bash, Grep, Glob | local |
| 7 | `presenter` | 집필실 | 슬라이드·발표·발제(청중 맞춤) | Read, Write, Edit, Bash, Grep, Glob | local |
| 8 | `paper-critic` | 심사·QA | 제출 전 적대적 자체검토 + 그림 시각 QA | Read, Grep, Glob, Bash, WebSearch, WebFetch | local |
| 9 | `backend-dev` | 엔지니어링 | 파이프라인·모델·retrieval·eval·테스트 코드 | Bash, Read, Edit, Write, Grep, Glob | local |
| 10 | `frontend-dev` | 엔지니어링 | Streamlit 대시보드·HTML 리포트·시각화 UX | Bash, Read, Edit, Write, Grep, Glob | local |
| 11 | `design` | 엔지니어링 | 로고·아이콘·브랜드·그림 미감(SVG/PNG) | Read, Write, Edit, Bash | local |
| 12 | `paper-orchestrator` | 코디네이션 | 멀티-agent 작업 **계획** 수립(실행은 PI) | Read, Grep, Glob, Write | local |
| G1 | `reviewer` | 심사·QA | 정식 venue 스타일 **공식 리뷰 문서** 작성 | (global) | global **agent** |
| G2 | `presentation-architect` | 집필실 | 발표 덱 구조 설계(서사·순서) | (global) | global **agent** |
| S1 | `manuscript-figures` | 엔지니어링 | 결과 파일에서 그림 생성·번호 정합 | (해당 없음) | **Skill** (agent 아님) |

> ⚠️ `manuscript-figures`는 Skill이다. agent로 호출(subagent_type)하면 실패한다. 그림은 `manuscript-writer` agent가 `docs/manuscript/figures/make_figures.py`를 실행하거나 이 스킬을 호출해 만든다. 단순 재생성은 메인 루프가 직접 `make_figures.py`를 돌려도 된다(결정론적, JSON에서 생성).

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
 literature-   variant-    manuscript-     paper-critic  backend-dev
   scout        analysis    writer         reviewer(G)   frontend-dev
 novelty-      variant-    presenter       (그림 QA는    [manuscript-
   strategist   adjudicator presentation-   paper-critic)   figures=skill,
 research-                  architect(G)                    run by writer]
   methodologist                                          design
```

### 일이 흐르는 표준 경로 (논문 생산 루프)

```
research-methodologist / literature-scout / novelty-strategist   (기획·근거)
        └─▶ variant-analysis ──▶ data/outputs/*.json             (분석·검증)
                 └─(discordant)─▶ variant-adjudicator             (잠정 판정)
        └─▶ manuscript-writer ──▶ docs/manuscript/preprint*       (집필)
                 ║  make_figures.py (manuscript-figures skill) ──▶ figures/*   (그림)
        └─▶ paper-critic ──▶ reviewer ──▶ peer_review_*.md        (심사)
                 └─▶ (수정 반영) manuscript-writer
        └─▶ verify_manuscript (게이트) ──▶ presenter              (검증→발표)
```

- `∥`/`║` = 병렬 가능, `└─▶` = 산출물 전달.
- **검증 게이트**(`scripts.verify_manuscript`)와 **공개 게이트**(회사/IP 검토)는 PI가 통과시킨다.

---

## 3. 멤버별 JD (Job Description)

각 JD = 책임 / 입력 / 산출물 / 하지 않는 것(경계). 권위 있는 전체 정의는 각 `.claude/agents/<name>.md` 본문.

### 분석실

**`variant-analysis`** — 듀얼모드 분석 파이프라인 운영자
- 책임: cohort/knowledge fetch, hybrid retrieval, Mode A(LLM)·Mode B(rule) 분류, eval 스위트(faithfulness·ablation·외부 벤치마크·temporal split·통계·discordance)를 실행/디버그/확장.
- 입력: 커밋된 스냅샷, `src/*`, 기존 `data/outputs/*`.
- 산출물: `data/outputs/cohort_interpretation.json` 및 eval/통계 JSON 일체.
- 경계: 본문/매뉴스크립트 프로즈는 쓰지 않는다(→ manuscript-writer). faithfulness·non-inferior 스탠스를 깨는 정확도 우월 주장 금지.

**`variant-adjudicator`** — 잠정 변이 판정자
- 책임: discordant/rule-초과/over-call 변이에 대해 근거 기반 "rule vs LLM 중 누가 맞나"의 **잠정** 판정.
- 입력: 지정된 변이, `data/outputs/*`, 외부 근거(ClinVar/CIViC 등 검증).
- 산출물: 검증된 근거가 달린 판정 노트.
- 경계: 전문가 사인오프 대체 아님. 파이프라인 실행/집필 안 함. **메모리 기반 값 날조 금지**(JSON·1차 출처에서만 인용).

### 문헌·기획

**`literature-scout`** — 선행연구 탐색·포지셔닝
- 책임: 선행연구 발굴·종합, gap 매핑, 정직한 기여 포지셔닝, 인용 달린 related-work.
- 산출물: related-work 섹션 / 레퍼런스 목록. 경계: 새 실험설계는 research-methodologist 소관.

**`novelty-strategist`** — 차별화 전략가
- 책임: 풍경 조사 + scoop/동시연구 플래그 + **구체적 차별화 기여**와 가장 싼 입증 실험 제안.
- 경계: literature-scout(있는 것 정직히 정리)와 research-methodologist(설계로 전환) 사이에 위치.

**`research-methodologist`** — 방법론·감사
- 책임: 거친 아이디어 → 날카로운 가설·기여문·엄밀한 실험/평가 설계; baseline/ablation/metric 설계; 누수·통계 사전 점검.
- 경계: 프로즈 작성·파이프라인 실행 안 함.

### 집필실

**`manuscript-writer`** — 본문 집필
- 책임: medRxiv 프리프린트(및 저널/블로그)의 프로즈·초록·섹션 작성, 그림 연계.
- 입력: **검증된 base(숫자를 메모리로 재유도 금지)** — HANDOFF/STUDY_SUMMARY + 결과 JSON.
- 산출물: `docs/manuscript/preprint{,_ko}.{md,html}`. 경계: 분석 실행 안 함. 통계 우월 주장 금지.

**`presenter`** — 발표물 제작
- 책임: 완성/초안 매뉴스크립트 → Marp/reveal 덱·발표노트·청중 맞춤본. 모든 숫자·그림은 매뉴스크립트/결과 파일에서 인용.
- 경계: 논문 작성·그림 생성·리뷰 안 함. 임상 인접 연구 디스클레이머 유지.

### 심사·QA

**`paper-critic`** — 제출 전 적대적 검토자(내부)
- 책임: 과대주장·누락 baseline/ablation·통계 갭·누수·재현성·신규성 + **그림 시각 QA**(텍스트-그래픽 겹침, tofu, 잘림). 우선순위 fix 제시.
- 산출물: 적대적 검토 노트. QA를 소유 — 전수 검토 책임.

**`reviewer` (global)** — 공식 리뷰 문서 작성
- 책임: venue 스타일 권고(accept/minor/major/reject)·항목별 점수·리포팅 가이드라인 체크가 담긴 **실제 referee가 제출할 리뷰 문서**.
- 경계: 사전 QA(번호·출처·그림 렌더)는 이미 끝났다고 가정(그건 paper-critic 소관).

### 엔지니어링·제작

**`backend-dev`** — 백엔드/파이프라인 코드. `src/pipeline.py`, `src/models/`, knowledge/retrieval/classify/eval, fetch/eval 스크립트, 데이터 스냅샷, 테스트. 경계: UI/리포트 렌더링 안 함.

**`frontend-dev`** — UI. Streamlit 대시보드(`src/dashboard/app.py`) + 인터랙티브 HTML 리포트(`templates/cohort_report.html` + `src/report/cohort_report.py`). 경계: 파이프라인/데이터/eval 백엔드 안 함.

**`design`** — 비주얼/브랜드(로고·아이콘·컬러·그림 미감), SVG 마스터 + 다중 PNG. 경계: 결과 기반 데이터 그림(→ manuscript-figures)·UI 코드(→ frontend-dev) 아님.

**`manuscript-figures` (Skill, agent 아님)** — 결과 파일에서 그림 생성·임베드·번호 정합(하드코딩 숫자 금지). agent로 호출하면 실패 — `manuscript-writer`가 `make_figures.py`를 실행하거나 이 스킬을 호출해 사용.

### 코디네이션

**`paper-orchestrator`** — 연구 코디네이터(계획 전용)
- 책임: 목표+현 상태 → 어떤 멤버가 어떤 순서로, 무엇이 병렬, 검증/적대 게이트 위치, 중단 조건의 **실행 계획**(+선택적 Workflow 스크립트).
- 경계: **직접 실행하지 않는다.** 계획을 PI(또는 Workflow 도구)가 실행.

---

## 4. 현재 하네스 상태 (성숙도 메모)

| 항목 | 상태 |
| --- | --- |
| 멤버(agent) 정의 | 🟢 12 local + 3 global, JD·도구 경계 명확 |
| 자연어 라우팅 | 🟡 CLAUDE.md 표로 신규 추가됨(이 문서와 함께) |
| 산출물 계약 | 🟡 CLAUDE.md 표로 명문화됨(파일 경로 검증) |
| 입구(Orchestrator **Skill**) | 🟢 `paper-production-orchestrator` Skill(2026-06-13 추가). `paper-orchestrator` agent는 계획 전용으로 유지 |
| 검증 게이트 | 🟢 `scripts/verify_manuscript.py` + `scripts/verify_manuscript_numbers.py`(2026-09-24 실행: 원고 수치 243개 중 242개 traceable). 이전 구성 수치도 traceable로 통과하는 맹점이 있어 주 결과 파일과 수작업 대조 필요(`docs/reference/traceability_check.md`) |
| 공개 일정 | 🟡 medRxiv(Genetic and Genomic Medicine) 게시와 저장소 공개 2026-10-10 예정, 블로그는 DOI 확보 뒤 |
| 팀 런타임(TeamCreate/Task/SendMessage) | 🔴 없음 — 멤버를 PI가 수동 호출 |
| 개선 루프(improvement-log) | 🔴 없음 — 회고가 커밋/HANDOFF에 분산 |

> 비교 기준: econ-radar / paper-radar는 Orchestrator Skill + 팀 런타임 + improvement-log까지 갖춘 5단계 하네스.
> 이 랩은 멤버가 일급이고 입구 Skill과 검증 게이트를 갖췄으나 **팀 런타임과 개선 루프**가 비어 있어 약 3단계.
> 더 적극적 보강(논문 생산 루프 Orchestrator Skill화)은 [CLAUDE.md](../../CLAUDE.md) 라우팅표를 입구 Skill로 승격하는 작업으로 가능.

---

*변경 이력:*
- *2026-06-13 — HARNESS.md 신설(랩 멤버 명부·관계도·JD). CLAUDE.md에 라우팅표·산출물 계약표 추가.*
- *2026-09-27 — 상태 표 갱신: 입구 Skill 🟢, 검증 게이트와 공개 일정(medRxiv, 2026-10-10) 행 추가, bioRxiv 표기를 medRxiv로 교체.*
- *2026-06-13 — `paper-production-orchestrator` Skill 추가(B-tier 입구). "그림만 다시" 검증 런에서 `manuscript-figures`가 agent가 아니라 **Skill**임을 발견 → 로스터·관계도·JD·라우팅·orchestrator 전체 교정(그림은 `manuscript-writer` agent가 `make_figures.py`/스킬로 수행).*
