---
name: review-orchestrator
description: Coordinates an evidence-driven code review of an assessment target end to end — architecture discovery, trust boundaries, specialist reviews, adversarial validation, classification and report. Use when the user starts or resumes an assessment (e.g. "start the SPIN review", "resume the assessment").
---

# Review orchestrator

You coordinate. You do not decide findings. Read `CLAUDE.md` first; its rules bind every step.
`A` below means the assessment dir, e.g. `assessments/spin`.

## Start or resume

1. `python3 harness.py verify A`. FAIL → stop and tell the user.
2. Read `A/progress.md` (you are its **only writer**). Resume from its `Phase` and `Current area`.
   The record files are the truth: `ls A/findings A/controls A/runtime` shows the last ID per prefix
   and every hypothesis's status. Don't copy those into progress.md.
3. Do only what the user's stated mode allows. Update progress.md at the end of every phase.

## Phases

| # | Phase | Output |
|---|---|---|
| 1 | DISCOVERY: components, entry points, data stores, external calls, deployment files | `A/architecture.md` |
| 2 | TRUST_BOUNDARIES: where untrusted input enters (HTTP, uploads, webhooks, AI output, queue messages); who is trusted on each side | section in `A/architecture.md` |
| 3 | INVARIANTS: turn the target's own claims (README, docs, contracts) into guarantees to test | `A/invariants.md` (project-specific; generic ones live in the specialist skills) |
| 4 | SPECIALIST_REVIEW: run each specialist (below) | hypotheses, controls, runtime items |
| 5 | VALIDATION: send **every** hypothesis to `finding-validator` | validated records |
| 6 | CLASSIFICATION: resolve DOWNGRADE/REWRITE, merge duplicate root causes (keep one, reject the rest as duplicates), `harness.py check A` passes | |
| 7 | HISTORICAL_COMPARISON: only now may historical material be read (see CLAUDE.md) | `A/historical-comparison.md` |
| 8 | REPORT: `python3 harness.py report A -o A/reports/<name>.md` | retained report |

Invariants are guarantees to **test**, never findings in themselves.

## Running specialists

Specialists are, in order of trust-boundary risk:
`backend-security-review`, `ai-security-review`, `ai-grounding-review`, `reliability-review`,
`data-lifecycle-review`, `billing-finops-review`.

- Assign each run a unique ID prefix (`BSEC`, `AISEC`, `AIGR`, `REL`, `DATA`, `BILL`; a second
  parallel run of the same specialist gets `BSEC2`...). Record the assignment in progress.md **before**
  starting the run. That is the whole concurrency scheme: one prefix per writer and one writer per file.
- Give each specialist: the assessment dir, its prefix, `A/architecture.md`, `A/invariants.md`, and the
  area it covers. Don't pass other specialists' conclusions as facts.
- Specialists may run in parallel (separate agents), because they never write the same files.

## Validation

- Every hypothesis goes to `finding-validator` as a **separate agent** with its own prefix (`VAL`, `VAL2`...). Give it the record path only,
  not the specialist's reasoning beyond what's in the record.
- Never set a finding's status yourself, and never accept a specialist's severity or conclusion unchecked.
- `RUNTIME_VALIDATION` outcome: the validator creates the `runtime/` item. It is not a finding.

## Behavioral validation (only if the user approves)

Never run anything in the baselined target. Make a disposable copy and verify it:

```bash
D=local-targets/<project>-$(date -u +%Y%m%dT%H%M%SZ)   # gitignored
cp -a <target>/. "$D"/ && (cd "$D" && sha256sum --quiet -c "$OLDPWD/A/baseline/manifest.sha256")
```

Run tests or probes only in `$D`, record the results in the relevant record (`test` field, evidence level 5),
and delete `$D` afterwards. `harness.py verify A` must still PASS.
