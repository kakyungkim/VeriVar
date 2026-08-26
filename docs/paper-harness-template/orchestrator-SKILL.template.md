---
name: paper-production-orchestrator
description: 논문 생산 루프의 입구(진행표/팀장) 스킬 템플릿. "논문 풀 파이프라인 돌려줘", "프리프린트 업데이트해서 제출 준비", "분석→집필→그림→검수까지 한 번에", "그림만 다시", "리뷰만 다시", "critic 지적 반영해", "최신 결과로 본문 갱신" 같이 분석·집필·그림·검수·검증·발표를 엮는 요청에서 사용한다. 기존 멤버(<DOMAIN_ANALYSIS_AGENT>, manuscript-writer, 그림 스킬, paper-critic, reviewer, presenter 등)를 정해진 순서로 호출하고 부분 재실행을 처리한다. 새 agent는 만들지 않는다.
---

# paper-production-orchestrator (논문 생산 루프 진행표 / 팀장) — 템플릿

> 이 파일은 재사용 템플릿이다. `<FILL: …>` 자리를 팀 환경의 실제 경로·스탠스로 채운 뒤
> 팀 레포의 `.claude/skills/paper-production-orchestrator/SKILL.md`로 둔다.

이 Skill은 **메인 루프(PI)가 실행**한다. 메인 루프는 Agent 도구로 멤버를 직접 부를 수 있으므로, "계획만" 하는 `paper-orchestrator`(agent)와 달리 실제로 루프를 돌린다. 멤버는 전부 기존 정의를 재사용한다 — 신규 agent 0개.

전체 랩 구조·멤버 JD는 `HARNESS.md`(팀 버전), 라우팅·산출물 계약 요약은 팀의 `CLAUDE.md` 참조.

## 언제 이 스킬을 쓰나
- 초기/전체: "논문 풀 파이프라인", "프리프린트 업데이트해 제출 준비", "분석부터 발표까지".
- 부분 재실행: "그림만 다시", "리뷰만", "분석만 다시", "발표만".
- 보완/이어서: "critic 지적 반영", "최신 결과로 본문 갱신".

## 실행 모드 분기 (먼저 확인)
1. 산출물 존재·최신 여부 확인:
   - `<FILL: result files — 분석 산출 JSON/표>`
   - `<FILL: manuscript files>`, `<FILL: figures dir>`
2. 분기:
   - **없음 / "풀 파이프라인" / "제출 준비"** → 초기·전체(전 단계).
   - **있음 + 특정 부분 요청** → 부분 재실행(해당 단계만, 나머지 기존 파일 재사용).
   - **"지적 반영" / "최신 결과로 갱신"** → 변경 지점의 **하류 단계만** 다시.
3. `<DOMAIN_ANALYSIS_AGENT>`가 LLM을 쓰는 경우, **offline mock 경로**(API 키 미설정 등)로 돌았는지 확인한다. mock이면 "실 LLM 결과 아님 / 데모"를 보고에 명시한다.

## 멤버 구성 (전원 기존 재사용)
`<DOMAIN_ANALYSIS_AGENT>`(팀이 공급하는 주제별 분석/실험 agent), manuscript-writer(그림 포함 — 그림 스킬/그림 생성 스크립트 사용), paper-critic, reviewer, presenter. (기획 단계 선택: research-methodologist, literature-scout, novelty-strategist) (선택: `<DOMAIN_VERIFIER_AGENT>` — discordant/over-call 등 잠정 판정이 필요할 때.)

> 참고: 그림 생성은 **agent가 아니라 Skill/스크립트**로 두는 것을 권장한다. 그림은 `manuscript-writer` agent가 `<FILL: 그림 생성 스크립트 또는 그림 스킬>`을 실행해 만든다. 단순 재생성이면 메인 루프가 직접 그 스크립트를 돌려도 된다(결정론적, 결과 파일에서 생성).

## 품질 기준선
- `<FILL: your quality/framing stance>` 유지 — 통계가 뒷받침하지 않는 우월 주장 금지.
- 숫자는 결과 파일·검증된 base에서만(메모리 재유도 금지). bootstrap CI + 적절한 유의성 검정 동반.
- 그림은 결과 파일에서 생성(하드코딩 금지), 번호는 첫 언급 순.

## 실행 흐름

1. **모드 분기** → 실행할 단계 집합 결정.
2. **(선택) 기획·근거** — 새 방향일 때만: research-methodologist / literature-scout / novelty-strategist.
3. **분석·eval** — `<DOMAIN_ANALYSIS_AGENT>` → `<FILL: result files>`. mock 경고 확인.
   - 잠정 판정이 필요하면 `<DOMAIN_VERIFIER_AGENT>` → 잠정 판정 노트(전문가 사인오프 필요).
4. **집필 + 그림** — `manuscript-writer` → `<FILL: manuscript files>`. 그림은 `<FILL: 그림 생성 스크립트/스킬>` 실행 → `<FILL: figures dir>`. 그림만 재실행이면 이 단계만, 스크립트를 직접 돌려도 된다(결정론적, 결과 파일에서 생성).
5. **검수** — `paper-critic`(적대적 + 그림 시각 QA) → 지적 노트.
   - 블로킹 지적이면 6으로, 경미하면 메모만 남기고 진행.
6. **수정** — `manuscript-writer`가 critic 지적 반영 → 본문 갱신.
7. **(선택) 정식 리뷰** — 요청 시 `reviewer` → `<FILL: peer review note path>`.
8. **검증 게이트** — `<FILL: your verify-gate command — 헤드라인 숫자를 결과 파일에서 결정론적으로 재계산>`.
   - **실패하면 멈추고 사람에게 보고**한다. 커밋·발행하지 않는다.
9. **(선택) 발표** — 요청 시 `presenter` → 덱·발제.

각 단계 산출물은 **파일로 남긴다**(대화로만 끝내지 않는다). 다음 단계는 그 파일을 읽는다.

## 산출물 계약
| 단계 | 멤버 | 산출 파일 | 다음이 읽음 |
| --- | --- | --- | --- |
| 분석·eval | `<DOMAIN_ANALYSIS_AGENT>` | `<FILL: result files>` | 집필·검수 |
| 판정(선택) | `<DOMAIN_VERIFIER_AGENT>` | 잠정 판정 노트 | 집필 |
| 집필 | manuscript-writer | `<FILL: manuscript files>` | 검수·리뷰·발표 |
| 그림 | manuscript-writer (그림 스킬/스크립트) | `<FILL: figures dir>` | 집필·검수 |
| 검수 | paper-critic | 적대 노트 + 그림 QA | 집필(수정) |
| 리뷰 | reviewer | `<FILL: peer review note path>` | 집필(수정) |
| 발표 | presenter | 슬라이드/발제 | 사람 |

## 실패 처리 / 멈춤 조건
- verify 게이트 실패 → **멈춤**, 무엇이 왜 실패했는지 보고.
- `<DOMAIN_ANALYSIS_AGENT>`가 mock 경로 → 결과는 데모, "실 결과 아님" 명시.
- 단계 산출 파일이 안 생김 → 재시도 1회, 그래도 실패면 사람에게 보고.

## 사람 승인 게이트 (자동화하지 않음)
- **공개**(프리프린트/blog 게시)는 `<FILL: 공개 전 검토 게이트 — 예: 소속·IP 검토>` 전까지 **보류**. 이 Skill은 절대 게시하지 않는다.
- `<DOMAIN_VERIFIER_AGENT>` 판정은 전문가 **사인오프 전까지 잠정**.
- 외부 발송(메일·메신저·제출)은 사람 승인 뒤에만.

## 마무리
- 최종 보고에 **무엇을 어떤 순서로 돌렸고, 어떤 파일이 갱신됐고, verify 통과 여부, 남은 일**을 명시한다(done/in-progress/blocked 구분).
- 부분 재실행이면 "건드리지 않은 단계"도 명시한다.
