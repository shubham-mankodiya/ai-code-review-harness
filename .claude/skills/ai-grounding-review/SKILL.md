---
name: ai-grounding-review
description: Specialist review of whether AI-produced answers and numbers are grounded in authoritative data and whether business calculations are deterministic code rather than model output. Invoked by review-orchestrator.
---

# AI grounding review

Follow **Specialist procedure** in `CLAUDE.md`. You are given an assessment dir `A` and an ID prefix.
Use `A/ai-call-matrix.md` (read-only for you) to find the AI call sites.

## Invariants you own (guarantees to test)

| Invariant | Holds when |
|---|---|
| AI authoritative grounding | Every figure, entity or claim that the AI shows to a user comes from, or is checked against, the authoritative data (DB / computed results) for *that* tenant and job. The system can say which source backs it, and shows "unknown" rather than inventing. |
| Deterministic business calculations | Money, savings, totals, rankings, classifications that drive decisions and anything billed are computed by deterministic code with tests. The model never computes them. Where AI classifies, the result is validated/constrained (allowed values, confidence thresholds, human review) before it's used. |

## Where to look

Prompt construction (what context is injected), structured-output schemas and their validation,
post-processing that turns model output into stored or displayed values, and the calculation modules and their tests.
Compare what the docs claim ("every number tied back to the analysis") with the code that enforces it.

## Hand off

Prompt injection / data leakage → ai-security-review. Cost → billing-finops-review.
