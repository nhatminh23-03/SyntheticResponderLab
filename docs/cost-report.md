# Measured interview cost

Prepared for Dr. Wang. Updated 2026-09-10. Dollar amounts are USD.

> **Status: P3.4 is complete.** Sixty complete eight-turn interviews have been recorded and
> metered, thirty on each of the two models Dr. Lin recommended. Every figure below is read from
> the application's own cost ledger, `apps/api/local-dev.db`, table `interview_turn`, column
> `cost_usd`, which stores the cost the provider reported for that call. Nothing here is
> extrapolated from token counts.

## Bottom line

A complete eight-turn interview costs about **three cents**.

| Model | Interviews | Per interview | Range | Input tokens | Output tokens | Total |
|---|---:|---:|---|---:|---:|---:|
| DeepSeek V4 Pro | 30 | $0.0313 | $0.016 – $0.047 | 541,582 | 205,177 | $0.9387 |
| Qwen3.7 Plus | 30 | $0.0281 | $0.023 – $0.034 | 1,229,627 | 436,270 | $0.8422 |

Everything recorded so far, both models and all retries, cost **$1.78**.

The figures are all-in. They include the retries and the one batch that failed partway and was
re-run, so they are an upper bound on what a clean run costs rather than a best case.

## What a class actually costs

Two numbers apply and they are far apart.

The **measured** number: thirty students each running one live interview is about **$0.95** on
either model. Most students will spend less than that, because complete interviews on both
models are already recorded and cached. Replaying a recorded interview costs nothing. Only a
genuinely new question reaches the provider.

The **enforced** number: the application refuses to spend more than $0.75 on one interview
session and more than thirty sessions per class cohort, a hard ceiling of **$22.50**. The ceiling
is enforced in code and halts the run rather than warning. It is the most a cohort can cost if
something goes wrong, not the expected bill.

## Why the two models cost nearly the same

Dr. Lin recommended these two as the expensive and the cheap end of a comparison. Measured, they
are within ten percent of each other, and the cheaper-looking one is not reliably cheaper per
interview.

The reason is in the token counts above. Qwen3.7 Plus is a reasoning model: it writes out private
reasoning before each answer, so it produces more than twice the output tokens of DeepSeek for
the same eight questions, and its lower per-token price is spent on thinking the reader never
sees. Its reasoning is capped at 400 tokens per call; uncapped it consumed the entire response
budget and returned nothing at all.

If the study wants a genuine cost contrast between tiers, the cheap end has to be a genuinely
small non-reasoning model. Two single-turn calls on that tier are in the ledger for reference,
$0.0001 each on GPT-4o mini and Gemini 2.5 Flash Lite, roughly two orders of magnitude below the
two models above, though single-turn calls understate an eight-turn interview because the
interviewer carries the conversation forward and the prompt grows with each question.

## How to reproduce these numbers

```
sqlite3 apps/api/local-dev.db "
select model,
       count(distinct persona_id) interviews,
       round(sum(cost_usd)/count(distinct persona_id),4) per_interview,
       round(sum(cost_usd),4) total
from interview_turn where cost_usd > 0 group by model;"
```

Recording a fresh set, which reuses the cache and so costs nothing for interviews already held:

```
apps/api/.venv/bin/python scripts/prerecord_interviews.py --personas 30 --max-usd 2.50
```
