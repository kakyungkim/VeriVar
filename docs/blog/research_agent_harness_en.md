<!-- DRAFT — HOLD. Publish only after company/IP review + the paper goes public; then move to the blog repo _posts/en/. Do NOT push now. date/permalink finalized at publish time. -->
---
layout: single
title: "I Had Twelve Agents and No Team — Rebuilding a Research AI Harness"
date: 2026-06-14 09:00:00 +0900
lang: en
ref: research-agent-harness
featured: true
categories: [AI & Tooling]
tags: [Claude Code, AI Agents, Agent Harness, Research Workflow, Building in Public]
permalink: /en/2026/06/14/research-agent-harness/
excerpt: "Last time I automated the news with a team of agents. This time I brought the same harness thinking to a research project — and the starting point was the opposite: I already had twelve specialist agents, and it still didn't run well."
---

{% include lang-switch.html %}

Hi — I'm Ka-Kyung, a bioinformatics researcher working across clinical data, genomics, and machine learning.

In my [last post](https://kakyungkim.github.io/en/2026/06/10/econ-radar-agent-harness/), I wrote about giving up on reading economic news by hand and building a team of AI agents (econ-radar) instead. The point there was handing repetitive work to a team with separated roles. This post is about bringing that same harness thinking into my research project — except the starting point was reversed. econ-radar was designed as a team from day one. The research project already had **twelve specialist agents**, and it still didn't run well. This is the story of why, and what I did about it.

> The project in question is a research/education pipeline that interprets somatic variants from public cancer-genomics data. It is not a clinical tool, and all data is public TCGA and public knowledge bases. This post is not about the research *findings* — it's about the way I built that research *together with AI*.

## Agents, but no team

The project's `.claude` folder had twelve role-specific agents: analysis, writing, figures, literature search, adversarial review, presentation. Each one was well made on its own. But whenever I asked for something — "rerun the analysis," "update the manuscript with the latest results" — I had to decide by hand which agent to call, and in what order.

Comparing it to econ-radar made the gap obvious. econ-radar had an **entry point**: a runsheet that managed the collect → analyze → edit → review → publish order, a contract for which file each stage leaves behind and which file the next stage reads, and a branch for re-running just one part. The research project had none of that connective tissue. I had assembled twelve experts and given them no lead, no division of labor, no shared format.

Looking back, "having agents" and "having a harness" are two different things. An agent is a capable teammate; a harness is the entry point, contracts, checks, and records that make them actually collaborate. I had hired the people and never built the team.

## Agent, Skill, and Orchestrator are not the same thing

So I started with the entry point: a single runsheet that takes a plain request — "run the full paper pipeline," "just redo the figures" — and calls the teammates in the right order.

One distinction turned out to matter. Even inside the same `.claude` folder, the *kinds* of roles differ. An **agent** is a teammate who does the work; a **skill** is the manual a teammate follows; an **orchestrator** is the runsheet that manages order and handoffs. The runsheet has to live where it can actually call the teammates.

I learned this the moment I got it wrong. I tried to call a "figures agent," and got back "no such agent." It turned out figures were a *skill*, not an agent — the actual figure work is done by the writing agent using that skill. Mistake the kind of role and nothing runs. It sounds trivial, but it was the first thing the harness needed straightened out.

## A harness gets tested

When I first ran the new entry point, I didn't run the whole pipeline at once. I tested it with the lightest possible partial run — "just redo the figures." A dry run, basically.

And that dry run is exactly what caught the "figures are a skill, not an agent" problem. One light test surfaced a design flaw on the spot.

That shifted how I think about it. A harness isn't one long prompt you write well and throw over the wall — it's closer to **software you run small and fix where it breaks.** It needs tests, and not just the happy path: the ambiguous case and the likely-to-fail case, run on purpose. With econ-radar I did this naturally by running it every day. For one-off research work, I had to deliberately build the dry run in.

## Honesty in the process

Partway through, I needed one more comparison tool. I wanted its per-variant predictions to put next to ours — but the tool only released data behind a registration token, and without one, I was blocked.

The part I liked most: the AI agent **refused to make up the data.** When access was blocked, instead of filling the gap with plausible-looking predictions, it saved the rejection responses (the auth-failure codes) as evidence, reported "blocked here," and stopped. Fabricating missing data is fatal in research — one convincing-looking cell can poison an entire conclusion.

Fittingly, the very thing this project studies is keeping an LLM from fabricating its sources — faithfulness. The principle I was *researching* was one the AI *building* the research held to in its own process. How we measure faithfulness with numbers and enforce it by construction is covered in two separate faithfulness posts on this blog, so I won't repeat it here. <!-- TODO(at publish): replace with permalinks to the faithfulness easy/numbers posts -->

## What I learned building it

Different from the five lessons in the last post — these are what was new this time.

**1. The entry point comes before more teammates.** Adding a single runsheet to bind the scattered agents mattered more than building another specialist. I wasn't short on teammates; I was short on a lead.

**2. Connective tissue pays off more than another agent.** The urge to add new roles was constant, but what actually helped was *joining what already existed* — routing rules, output contracts, an entry point.

**3. Verify a harness with a dry run.** Run the lightest partial first, before the whole thing, and flaws show up cheaply.

**4. For a research harness, "stop when you don't know" is the top priority.** In content automation, filling the blank is sometimes a virtue; in research, stopping when the data isn't there — and recording that — is the safety line that matters most.

## Where it started

At the end of the last post I noted that the agent-harness idea first came from research work. If econ-radar took that idea out of research, this was bringing it back in, in earnest. The interesting part: the same philosophy — split the roles, leave outputs as files, keep judgment for the human — produced different lessons once the domain changed. With news, the question was *what to automate*. With research, the question was *how to make it trustworthy*.

## Next

The research itself is being written up separately, with a proper paper. Once that's out, I'd like to follow up on how this harness actually ran the work end to end — analysis to manuscript to figures to review — and what else I fixed along the way. If you're sitting on a pile of scattered agents wondering why it doesn't quite work, I hope some of this is useful.
