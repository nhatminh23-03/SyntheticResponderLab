# Phase 2 — headless survey run over the persona set

`run_survey.py` sends every persona in a phase-1 CSV through the bundled 32-question Tahoe Mini
survey (39 answer items once the barrier matrix expands), one OpenRouter call per persona, and
writes an answer file per run. It reuses the app's own live-run function unchanged; only the
prompt budget, the HTTP client, and likert label handling are wrapped. Nothing under
`apps/` is modified.

## Run

From the repository root, with `OPENROUTER_API_KEY` in `apps/api/.env`:

```bash
# print the prompt for persona 1 and the projected cost; no network
apps/api/.venv/bin/python research/neo_persona_set/phase2/run_survey.py --dry-run

# smoke test: 5 personas, one model, one repeat
apps/api/.venv/bin/python research/neo_persona_set/phase2/run_survey.py \
  --models deepseek/deepseek-v4-pro-0813 --repeats 1 --limit 5

# the agreed run set: 2 repeats on each model
apps/api/.venv/bin/python research/neo_persona_set/phase2/run_survey.py \
  --models deepseek/deepseek-v4-pro-0813 qwen/qwen3.7-plus --repeats 2 --concurrency 12

# compare finished runs (repeat agreement, Q1 shares, attention check)
apps/api/.venv/bin/python research/neo_persona_set/phase2/run_survey.py --summary <run_id> <run_id> ...
```

Hidden reasoning is disabled by default (`--reasoning-effort off`). Both suggested models otherwise
think for roughly 3,000 tokens per persona, which quadruples cost, multiplies latency, and truncated
answers at 4,000 tokens in the smoke test; with it off they answer in 650 to 1,050 tokens with no
fabricated answers. Pass `--reasoning-effort default` to leave the provider default in place.

Defaults: personas `SyntheticResponderLab-Assets/600_persona/phase1_interview_survey600owners.csv`,
survey `apps/api/legacy_runtime/Provided Info/Neo Smart Living — Survey_HighMedPriority.md`,
output `SyntheticResponderLab-Assets/600_persona/survey_runs/`, temperature 0.2, max_tokens 6000,
seed `seed_base*10 + repeat`, prompt variant `full` (exact Census record + story). Results are
written to the shared folder and are not committed.

Useful flags: `--prompt-variant census|buckets`, `--provider-order together,fireworks`
`--no-provider-fallbacks` (pin DeepSeek to US hosts, ~2x price), `--price-in/--price-out`,
`--reasoning-effort off|low|medium|high`, `--json-mode`, `--no-likert-label-map`,
`--fallback-threshold`, `--run-tag`, `--continue-on-failure`.

## Output per run: `survey_runs/<run_id>/`

| File | Contents |
| --- | --- |
| `answers_long.csv` | one row per persona x question: run_id, model, repeat, seed, persona_id, respondent_id, question_id, question_type, answer, answer_json, is_fallback |
| `answers_wide.csv` | one row per persona, one column per question id, plus n_fallback and all_live |
| `questions.csv` | question id, type, scale bounds, options, text |
| `raw_responses.jsonl` | per persona: raw model text, provider, model served, generation id, tokens, cost, attempts, finish_reason |
| `generation_debug.json` | the adapter's counters verbatim |
| `prompt_sample.txt` | the prompt sent for persona 1 |
| `summary.md` | Q1/Q2/Q6/Q14 shares, Q30 attention-check pass rate, Q21/Q22 consistency with the Census record |
| `manifest.json` | everything needed to reproduce: hashes of inputs, settings, counts, tokens, cost, guardrail result, git commit |

`survey_runs/index.csv` gets one row per run. A run that fails a guardrail is kept under
`<run_id>_failed/` and is never indexed as completed.

## Guardrails

- Any path containing `aytm`, `survey-760085`, or the raw-dataset folder name is refused (exit 3),
  and a persona CSV with survey-answer columns is refused. The real 600 never enter a prompt.
- Terminal provider errors (400/401/402/403/404) stop the run immediately, as in the app.
- After the run: `request_errors > 0`, `provider_error_count > 0`, fabricated-answer share above
  1% (default), or a respondent count that does not match the persona count marks the run failed.
- Retries apply only to timeouts, connection errors, 408/429/5xx, unparseable JSON, and truncated
  output; every retry is counted in the manifest.

## Cost (list prices, 2026-09-09; ~6,200 input and ~900 output tokens per persona)

| Model | Input / output per M | Per 600 run |
| --- | --- | --- |
| deepseek/deepseek-v4-pro-0813 | $0.66 / $1.98 | ~$3.50 at list price; the smoke test billed ~$0.011 per persona (~$6.50 per 600) because OpenRouter spread calls over pricier hosts |
| qwen/qwen3.7-plus | $0.32 / $1.28 | ~$1.90 (smoke test billed ~$0.0034 per persona, ~$2.10 per 600) |

## Tests

```bash
apps/api/.venv/bin/python -m pytest research/neo_persona_set/phase2 -q
```

The tests stub OpenRouter; they never call the network.
