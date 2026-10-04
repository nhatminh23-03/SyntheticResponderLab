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

Defaults: personas `SyntheticResponderLab-Assets/4_persona_sets/plain_600_2026-08-25/phase1_interview_survey600owners.csv`,
survey `apps/api/legacy_runtime/Provided Info/Neo Smart Living — Survey_HighMedPriority.md`,
output `SyntheticResponderLab-Assets/5_experiments/new_runs/survey_runs/`, temperature 0.2, max_tokens 6000,
seed `seed_base*10 + repeat`, prompt variant `full` (exact Census record + story). Results are
written to the shared folder and are not committed.

The `age_bucket` and `income_bucket` labels are derived from `exact_age` and
`exact_household_income` before the prompt is built, because the phase-1 exporter labels them
with the bands of the screened pool (a matched draw with a $31,980 income arrives labeled
"$100k-$150k"). The manifest counts how many rows changed; `--keep-file-buckets` sends the
file's labels unchanged.

Give every experiment round its own dated folder under `5_experiments/` (the Assets folder layout
is described in its START_HERE.md), e.g.
`--personas ../SyntheticResponderLab-Assets/4_persona_sets/matched_600_v2_S1-S6_2026-09-16/phase1_interview_matched600_s1.csv
--out-dir ../SyntheticResponderLab-Assets/5_experiments/2026-10-10_<what>/survey_runs --run-tag s1-<what>`.

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
- Retries apply only to timeouts, connection errors, 408/429/5xx, unparseable JSON, and truncated
  output; every retry is counted in the manifest.
- Repair rounds (`--repair-rounds`, default 2): after the batch, personas that ended up with any
  fabricated answer are asked again, and the attempt with the fewest fabricated answers is kept.
  The manifest lists which personas were repaired and how many improved.
- The host `DigitalOcean` is excluded by default (`--provider-ignore`): in the first 600-persona
  run it served 5 calls and produced every garbage response (nonsense tokens, invented question
  ids, invented options). Pass `--provider-ignore ''` to allow every host.
- After repairs: a run is marked failed if more than 0.5% of personas (`--max-failed-respondent-share`)
  still have no usable model answer, if fabricated answers exceed 1% (`--fallback-threshold`), or if
  the respondent count does not match the persona count. Answers that were fabricated are always
  flagged `is_fallback=true` in the data; exclude them in analysis as the app does.
- `summary.md` and the manifest break fabricated answers down by question and by serving host.

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

## Experiment switches (added 2026-09-12; all default to off, so earlier runs stay reproducible)

| Flag | What it changes | Recorded in the manifest as |
| --- | --- | --- |
| `--survey-description keep\|drop` | whether the "Survey Setup" block before the first question (target population, what was cut) is sent; default `drop` | `survey_description_sent` |
| `--persona-ids FILE` | run exactly the personas listed in FILE (one id per line, from `phase3/select_panel.py`); run id gets `_p<N>` | `personas.persona_ids_file`, `personas.persona_ids_sha256` |
| `--temperature-jitter F` | a different temperature per persona, uniform in ±F around `--temperature`, deterministic per seed | `temperature_jitter`; each capture carries `temperature` |
| `--no-sponsor-context` | drops the sponsor's goal, pain points, barriers and objections from the prompt | `context.sponsor_context_removed` |
| `--trait-mix skeptical:0.3,...` | gives a seeded share of personas a response style (`skeptical`, `enthusiastic`, `indifferent`, `pragmatic`); `answers_wide.csv` gains a `trait` column | `trait_mix`, `trait_counts` |
| `--reason-per-answer` | asks for a one-sentence reason with every answer (max_tokens raised to 9000); `answers_long.csv` gains a `reason` column | `reason_per_answer`, `counts.answers_with_reason` |
| `--questions-per-call N` | sends the survey in slices of N questions per call; answers are stitched back per persona, `raw_responses.jsonl` keeps every slice under `chunks` | `questions_per_call`, `calls_per_persona` |
| `--answer-mode distribution` | likert items are answered as odds over the scale points and one answer is drawn at those odds, seeded by run seed, persona and question (Dr. Lin's arm B); the engine sees the drawn number, so answers files look as usual; `probabilities.csv` keeps the stated odds, the drawn answer and a status per item (invalid odds become a flagged fallback and go to the repair rounds) | `answer_mode`, `counts.distributions` (drawn / renormalized / label_keys / invalid / plain / missing) |
| `--hybrid` | runs a hybrid persona file: Dr. Lin's four driver columns (`prior_consideration_of_backyard_unit`, `outdoor_recreation_frequency`, `member_of_outdoor_club`, `most_likely_use_for_a_backyard_unit`) are answers copied from real respondents in the calibration half (his `personas_S*_drv.csv`, labelled hybrid 2026-09-30) and reach the model as `customer_facts`; his `driver_donor_id` and any other extra column never do. A file with driver columns is refused without the flag, the flag is refused without all four, and the run tag must contain `hybrid`. Score these runs only on the validation respondents and never on the driver items (compare_real.py enforces both) | `persona_kind` (`hybrid` / `synthetic`) |

Each question's `preamble` (the product stimulus before Q1, the concept copy before Q9A..Q13A, the
value-driver text before Q15) travels with its question, so with `--questions-per-call` later slices
still carry their own stimulus; the product facts otherwise reach them only through the product
context. `questions.csv` has a `preamble` column; `--dry-run` prints the Q1 and Q9A preambles.
