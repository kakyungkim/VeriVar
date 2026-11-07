# Paper-production harness — starter kit

*Designed by Ka-Kyung Kim, 2026 — a reusable paper-production harness, contributed as a scaffold.*
Licensed **CC BY 4.0** (see [LICENSE](LICENSE)).

A **topic-agnostic scaffold** for running a research paper from analysis to talk as a repeatable
multi-agent harness: a roster of reusable agents (methodology, literature, writing, critic, reviewer,
presenter, design), an orchestrator that drives them in order with partial re-runs, an artifact
contract so stages hand off through files (not chat), and a two-stage review + deterministic verify
discipline before anything ships. The only topic-coupled piece is a single pluggable analysis slot.

## How to use (keep it clean)
1. **Copy** `agents/*.md` into your team repo's **`.claude/agents/`** (project scope).
2. **Install the orchestrator**: copy `orchestrator-SKILL.template.md` to
   `.claude/skills/paper-production-orchestrator/SKILL.md`.
3. **Wire routing**: paste `CLAUDE-routing.template.md` into your team's `CLAUDE.md`; put the lab map
   from `HARNESS.template.md` at `docs/HARNESS.md`.
4. **Add `manuscript-writer`**: copy `manuscript-writer.template.md` to
   `.claude/agents/manuscript-writer.md` and fill its placeholders.
5. **Fill every `<FILL: …>` placeholder IN THE TEAM ENVIRONMENT** (paths, result files, your
   headline/framing stance, verify-gate command, affiliation). Do this in the team repo, not here.
6. Do **NOT** put any of this in `~/.claude/` — that mixes contexts across projects. Keep it
   project-scoped to the team repo.

## The pluggable slot
Everything except one role is reused as-is. The team supplies **one** topic-specific agent,
`<DOMAIN_ANALYSIS_AGENT>` — the analysis/experiment agent that runs your domain's pipeline, eval,
and statistics and writes the result files. (Optionally a `<DOMAIN_VERIFIER_AGENT>` for provisional
adjudication of borderline cases.) The rest — methodology, literature-scout, novelty-strategist,
manuscript-writer, paper-critic, reviewer, presenter, design, and the orchestrator — is the reusable
connective tissue and does not change with the topic.

## File manifest
| File | Purpose | Reuse |
| --- | --- | --- |
| `agents/research-methodologist.md` | hypothesis/contribution + rigor & leakage audit | reuse as-is |
| `agents/literature-scout.md` | prior-art discovery + honest positioning + related work | reuse as-is |
| `agents/novelty-strategist.md` | scoop check + differentiated angles | reuse as-is |
| `agents/paper-critic.md` | internal adversarial review + figure visual QA | reuse as-is |
| `agents/paper-orchestrator.md` | plans (does not execute) a multi-agent workflow | reuse as-is |
| `agents/presenter.md` | manuscript → slide deck / talk | fill paths |
| `agents/design.md` | logos/icons/brand & figure aesthetics (SVG+PNG) | reuse as-is |
| `manuscript-writer.template.md` | preprint/journal/blog prose + figures | **fill required** |
| `orchestrator-SKILL.template.md` | entry-point Skill: drives the loop, partial re-runs | **fill required** |
| `HARNESS.template.md` | lab roster / org chart / per-agent JDs | **fill required** |
| `CLAUDE-routing.template.md` | NL routing + artifact-contract tables for CLAUDE.md | **fill required** |
| `DESIGN_NOTES.md` | rationale: why the harness is built this way | reuse as-is (reference) |
| `README.md` / `LICENSE` | this file + CC BY 4.0 note | reference |

## IP / provenance
This kit carries **only generic methodology and engineering best-practice** — agent roles, an
orchestration pattern, an artifact contract, and review/verify discipline. It contains **no
proprietary data, no domain-specific logic, and no employer content**; all topic-specific material
has been replaced by `<FILL: …>` placeholders and a pluggable analysis slot. Contributed by
Ka-Kyung Kim under **CC BY 4.0** — reuse and adapt freely, keep the attribution.

## Pre-handoff checklist
Before sharing the kit, confirm it is free of any source-project traces:

```bash
# --exclude=README.md skips this file itself (the pattern below necessarily names the
# source-project terms; that QA command is the only place they appear in the kit.
# Replace EmployerA|EmployerB|username with your own organisation names and handle.)
grep -rinE "variant|VeriVar|somatic|Horak|cohort|VICC|oncogenic|cBioPortal|CIViC|EmployerA|EmployerB|username|STUDY_SUMMARY" docs/harness/paper-harness-template/ --exclude=README.md
# must return ZERO hits
```

- [ ] grep above returns zero hits (no topic/company/personal traces).
- [ ] every `<FILL: …>` placeholder is filled in the team environment.
- [ ] `<DOMAIN_ANALYSIS_AGENT>` is named and its agent file exists in the team repo.
- [ ] the verify-gate command actually recomputes the headline numbers.
- [ ] nothing was placed in `~/.claude/` (project-scoped only).
- [ ] the attribution line is present in README, DESIGN_NOTES, and HARNESS.
