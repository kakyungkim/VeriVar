<!-- ===================================================================== -->
<!-- Paste this block into your team's CLAUDE.md.                            -->
<!-- Fill every <FILL: …> and name your <DOMAIN_ANALYSIS_AGENT>.            -->
<!-- Reusable paper-production harness scaffold (CC BY 4.0,                  -->
<!-- Designed by Ka-Kyung Kim, 2026).                                       -->
<!-- ===================================================================== -->

## Agent routing & artifact contract

Full harness map (roster, org chart, per-agent JDs): **`docs/HARNESS.md`** (from `HARNESS.template.md`).

### Natural-language routing

Route a request to the right agent even when the user does not name one. Project-local agents live in `.claude/agents/`; some (e.g. `reviewer`) may be global. Figure work is owned by the `manuscript-writer` agent, which runs `<FILL: figure-generation script>` (or invokes the figure skill).

**Multi-step paper work → the orchestrator Skill, not a single agent.** When the request spans several stages — "풀 파이프라인 / 프리프린트 업데이트해 제출 준비 / 분석→집필→그림→검수까지 / 그림만 다시 / 리뷰만 다시 / critic 지적 반영" — use the **`paper-production-orchestrator`** Skill (`.claude/skills/paper-production-orchestrator/SKILL.md`). It runs in the main loop and calls the members below in order, handling partial re-runs and the verify gate. Single-stage requests route directly to one agent:

| Request (natural language) | First agent |
| --- | --- |
| "분석 돌려줘 / 재실행 / eval·통계 / 오류 분석" | `<DOMAIN_ANALYSIS_AGENT>` |
| "이 경계 사례 누가 맞아 / 모호 판정" (선택) | `<DOMAIN_VERIFIER_AGENT>` (provisional; needs expert sign-off) |
| "프리프린트/저널/블로그 초안·섹션 써줘" | `manuscript-writer` |
| "그림 만들어줘 / 그림 번호 정리" | `manuscript-writer` (runs `<FILL: figure script>` / figure skill) |
| "선행연구 / related work / 스쿱 확인" | `literature-scout` |
| "차별화 각도 / 뭘 새로 해야 하나" | `novelty-strategist` |
| "가설·실험설계·분석계획 점검·감사" | `research-methodologist` |
| "제출 전 적대적 자체검토 / 그림 QA" | `paper-critic` |
| "정식 venue 리뷰 시뮬레이션" | `reviewer` |
| "발표자료/슬라이드/발제" | `presenter` |
| "로고·아이콘·브랜드·그림 미감" | `design` |
| "여러 단계를 어떤 순서로 엮을지 계획만" | `paper-orchestrator` (plans only; the main loop executes) |

### Artifact contract

Agents do not leave intermediate results in chat only — they write/read these files (verify the paths in your repo).

| Stage | Writer | Artifact | Read next by |
| --- | --- | --- | --- |
| Analysis / experiments | `<DOMAIN_ANALYSIS_AGENT>` | `<FILL: result files — e.g. data/outputs/*.json (+ csv)>` | eval, manuscript-writer, verifier |
| Eval / stats | `<DOMAIN_ANALYSIS_AGENT>` | `<FILL: eval/stats result files>` | manuscript-writer, paper-critic |
| Adjudication (optional) | `<DOMAIN_VERIFIER_AGENT>` | provisional adjudication note (expert sign-off) | manuscript-writer |
| Manuscript + figures | manuscript-writer (figures via `<FILL: figure script>` / figure skill) | `<FILL: manuscript files>`, `<FILL: figures dir>` | paper-critic, reviewer, presenter |
| Verification gate | (before any commit/post) | `<FILL: verify-gate command>` | human |
| Review | paper-critic / reviewer | `<FILL: peer review note path>` | manuscript-writer |
| Presentation | presenter | slide deck / handout | human |
| State handoff | (all) | `<FILL: state/handoff doc>`, `<FILL: TODO doc>` | next session |

**Human-approval gates:** public release (preprint/blog) is held pending `<FILL: your pre-release review — e.g. IP/affiliation check>`; `<DOMAIN_VERIFIER_AGENT>` verdicts are provisional until a domain expert signs off.
