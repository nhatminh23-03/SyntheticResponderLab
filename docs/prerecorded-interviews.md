# Headless interview recordings (P3.5)

Run against the app's migrated database with the fixed personas already seeded:

```bash
apps/api/.venv/bin/python scripts/prerecord_interviews.py --dry-run
apps/api/.venv/bin/python scripts/prerecord_interviews.py --personas 3 --max-usd 0.50
```

Defaults are DeepSeek V4 Pro and Qwen3.7 Plus, each playing both roles for three
personas through the agent's eight-turn limit. `--models` accepts space-separated
catalog IDs; `--personas` accepts 3–30, matching the classroom limits. Explicitly
selecting an expensive catalog model opts this batch into that model.

The CLI prints the study ID and per-model session IDs, completed question/answer
turn counts, input/output tokens and measured dollars. Each model batch has its
own run budget; the existing class cap and `NEO_LLM_BUDGET_USD` still apply.
`--max-usd` additionally caps the whole command. Estimates cover both agents using
catalog token allowances and assume cache misses. A provider response can cost
more than its estimate: it is saved before stopping, with no further calls.

Questions and answers are persisted by the existing interview services. These
services log both the generated question and its zero-cost submission to the
interviewee, so database row count is not the completed-turn count. To replay,
submit the saved questions to the standalone interview service with the same
persona, model and prior messages, or rerun the CLI to reuse both agents' caches.
The service retains its existing history normalization, including the last-12-message
window for interviewee prompts. Cached replay records zero new tokens and cost.
Recording enables cache-first when caching is off; replay-only remains replay-only.
Cache-first reruns retain a full cache-miss estimate. Replay-only runs project zero
spend and work with `--max-usd 0` and `NEO_LLM_BUDGET_USD=0`, even after the
class budget is exhausted; a missing cache entry stops the command without a provider call.

Only fixed public-data persona profiles and a built-in product research brief
enter prompts. The command does not read real survey answers or accept a data file.

Implementation handoff: only P3.5 is changed, in `scripts/prerecord_interviews.py`,
`apps/api/tests/test_prerecord_interviews.py`, this note and `SPEC.md`. No existing
service behavior or protected files changed. Tests use a stubbed provider; no paid
recordings were generated during implementation. Verification is
`./scripts/verify.sh`; the focused suite is
`apps/api/.venv/bin/python -m pytest apps/api/tests/test_prerecord_interviews.py -q`.
Refutation found and fixed replay-only runs being rejected by paid-call preflight
and next-call estimates when spending was disabled. The regression test first failed,
then passed with zero batch/run allowances and existing class spend. Preserve these
uncommitted files.
