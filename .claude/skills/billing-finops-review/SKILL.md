---
name: billing-finops-review
description: Specialist review of payments, entitlements, billing idempotency and AI cost attribution/budgets in an evidence-driven assessment. Invoked by review-orchestrator.
---

# Billing and FinOps review

Follow **Specialist procedure** in `CLAUDE.md`. You are given an assessment dir `A` and an ID prefix.

## Invariants you own (guarantees to test)

| Invariant | Holds when |
|---|---|
| Billing idempotency | A payment event (webhook, redirect, retry, double-click) grants an entitlement exactly once. Webhooks are signature-verified and deduplicated by event/payment ID, enforced by a DB constraint, not only an app-side check. |
| Entitlement enforcement | Paid-tier data and features are gated server-side on a verified payment state. The free tier can't get paid output by changing request parameters or calling the API directly. |
| AI cost attribution | Every AI call's cost (tokens/model) can be attributed to a tenant/job, and there is a per-job or per-tenant budget or cap that stops runaway spend. Free-tier usage is bounded. |

## Where to look

Payment provider integration, webhook handlers, entitlement checks on result/export endpoints, pricing
modules, usage/metering tables, and the Metering and Budget columns of `A/ai-call-matrix.md`.

## Hand off

Generic retry behaviour → reliability-review. Authz on who can see paid results → backend-security-review
(you own the *entitlement* rule; they own *identity*). Payment provider dashboard settings,
webhook secret configuration → a `runtime/` item.
