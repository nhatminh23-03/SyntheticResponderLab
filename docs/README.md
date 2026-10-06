# Documentation

Everything written about the project lives here. Code-adjacent build folders stay in [`../plans/`](../plans/) (one folder per feature: brief, done checks, handoff), and the build checklist stays in [`../SPEC.md`](../SPEC.md).

## Operating the app

| Doc | What it covers |
| --- | --- |
| [`deploy/invite-only-deployment-runbook.md`](deploy/invite-only-deployment-runbook.md) | Operator runbook for an invite-only beta: the platform-neutral release checklist |
| [`deploy/vercel-render-deployment.md`](deploy/vercel-render-deployment.md) | Recommended hosting: Vercel (web) + Render (API) architecture, environment variables, deploy steps |
| [`instructor-guide.md`](instructor-guide.md) | Teaching with the Student Interview section |
| [`prerecorded-interviews.md`](prerecorded-interviews.md) | Recording headless interviews (P3.5) against the app database |
| [`cost-report.md`](cost-report.md) | Measured interview cost, prepared for Dr. Wang (read by `apps/api/tests/test_cost_report.py`; keep it at this path) |

## Design and specs

| Folder | What is in it |
| --- | --- |
| [`superpowers/specs/`](superpowers/specs/), [`superpowers/plans/`](superpowers/plans/) | Design spec and implementation plan for the Oct 7 class app (survey demo, Jev, student questions) |
| [`design/ui-prototype/`](design/ui-prototype/) | The original landing-screen prototype (HTML, notes, screenshot) |

## History (read-only record)

| Folder | Period | Contents |
| --- | --- | --- |
| [`history/2026-03-migration/`](history/2026-03-migration/) | March 2026 | Streamlit → Next.js + FastAPI migration plan, frontend review, Phase 0–3 specs |
| [`history/2026-04-release-readiness/`](history/2026-04-release-readiness/) | April 2026 | Audits, pre-deploy and public-deploy plans, codebase index |
| [`history/2026-08-handoff/`](history/2026-08-handoff/) | August 2026 | Aug 20 handoff (written by Yaza) |
| [`qa/2026-08-17/`](qa/2026-08-17/) | August 2026 | QA pass: baseline, browser end-to-end runs, bugs, fix log, final verification, with evidence in `artifacts/` |

Mentions of old paths inside these historical documents were left as written; use the table below to find the files.

## Where things moved (October 2026)

| Old path | New path |
| --- | --- |
| `Documentation/invite-only-deployment-runbook.md` | `docs/deploy/invite-only-deployment-runbook.md` |
| `Documentation/vercel-render-deployment.md` | `docs/deploy/vercel-render-deployment.md` |
| `Documentation/frontend_migration_first_pass_2026-03-26.md` | `docs/history/2026-03-migration/frontend_migration_first_pass_2026-03-26.md` |
| `Documentation/nextjs_python_migration_plan_2026-03-26.md` | `docs/history/2026-03-migration/nextjs_python_migration_plan_2026-03-26.md` |
| `Documentation/phase0_thin_slice_backend_spec_2026-03-28.md` | `docs/history/2026-03-migration/phase0_thin_slice_backend_spec_2026-03-28.md` |
| `Documentation/phase1_backend_implementation_2026-03-28.md` | `docs/history/2026-03-migration/phase1_backend_implementation_2026-03-28.md` |
| `Documentation/phase2_setup_flow_audit_and_hardening_2026-03-28.md` | `docs/history/2026-03-migration/phase2_setup_flow_audit_and_hardening_2026-03-28.md` |
| `Documentation/phase3_insights_chart_system_plan_2026-03-28.md` | `docs/history/2026-03-migration/phase3_insights_chart_system_plan_2026-03-28.md` |
| `Documentation/audit.md`, `audit-edit.md`, `Audit-PredeploymentPLAN.md`, `public-deployPLAN.md`, `codebase_index_2026-04-13.md` | `docs/history/2026-04-release-readiness/` (same file names) |
| `Documentation/handoff-2026-08-20.md` | `docs/history/2026-08-handoff/handoff-2026-08-20.md` |
| `QA August 17/` | `docs/qa/2026-08-17/` (same structure) |
| `UI Prototype/` | `docs/design/ui-prototype/` |
