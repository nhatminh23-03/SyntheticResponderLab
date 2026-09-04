# Preliminary interview cost evidence

Prepared for Dr. Wang on 2026-09-04. Dollar amounts are USD.

> **Status: P3.4 is not complete.** The ledger contains two measured single-turn calls, both on the
> cheap tier. No complete eight-turn interview or full run has been measured, and neither the mid
> nor expensive tier has been called. The scenario totals below are extrapolations from those two
> calls, not the three-tier measured report required by P3.4.

## Bottom line

The completed single-turn P001 comparison cost **$0.00022265 measured** for two model answers: $0.00007430
on Gemini 2.5 Flash Lite and $0.00014835 on GPT-4o mini. At that observed workload, an uncached
eight-turn student session is **$0.00059440-$0.00118680** on the cheap tier. The default AI-to-AI
run (three personas, eight turns, two agents) is **$0.00534360** with the two cheap-tier models.

A complete 30-persona x 32-question sweep is 960 model answers. Its extrapolated cost is
**$0.071328-$0.142416 per cheap model**, **$0.326304-$1.101120 per mid-tier model**, or
**$1.323600-$3.303360 per expensive model**. These sweep figures are not bills from completed
sweeps; they apply the measured P001 token workloads to the catalog's per-token prices.

## What was measured

The source is `apps/api/local-dev.db`, table `interview_turn`. The paid assistant rows for session
`ses_bd0ab92183e3` are:

| Persona | Model | Input tokens | Output tokens | Provider-reported cost |
|---|---|---:|---:|---:|
| P001 | Gemini 2.5 Flash Lite | 383 | 90 | $0.00007430 |
| P001 | GPT-4o mini | 357 | 158 | $0.00014835 |
| **Two-model comparison total** | | **740** | **248** | **$0.00022265** |

The corresponding user rows have zero tokens and zero cost. A later exact cache replay also has
zero tokens and zero cost; it is not treated as another provider measurement.

The rows can be checked without making a provider call:

```sql
SELECT persona_id, model, tokens_in, tokens_out, cost_usd
FROM interview_turn
WHERE session_id = 'ses_bd0ab92183e3' AND role = 'assistant'
ORDER BY model;
```

The provider-reported charges also reproduce exactly from the catalog rates current on 2026-09-04:

```text
Gemini: (383 x $0.10 + 90 x $0.40) / 1,000,000 = $0.00007430
GPT-4o: (357 x $0.15 + 158 x $0.60) / 1,000,000 = $0.00014835
```

That agreement validates the input/output token rates used below. It does not turn the larger
scenarios into measurements.

## Extrapolated scenario cost table

Each cell with two values is `first model / second model` from the model-pair column. The two-model
columns use both models, assigning the observed 383-in/90-out workload to the first model and the
observed 357-in/158-out workload to the second.

| Tier | Model pair | One student turn (one answer) | Full student session (8 turns) | Default AI-to-AI run (3 personas x 8 turns x 2 agents) | Full 30 x 32 sweep (one model / both models) |
|---|---|---:|---:|---:|---:|
| Cheap | Gemini 2.5 Flash Lite / GPT-4o mini | $0.00007430 / $0.00014835 | $0.00059440 / $0.00118680 | $0.00534360 | $0.071328 / $0.142416 / **$0.213744** |
| Mid | Gemini 2.5 Flash / Claude Haiku 4.5 | $0.00033990 / $0.00114700 | $0.00271920 / $0.00917600 | $0.03568560 | $0.326304 / $1.101120 / **$1.427424** |
| Expensive | Gemini 2.5 Pro / Claude Sonnet 4.5 | $0.00137875 / $0.00344100 | $0.01103000 / $0.02752800 | $0.11567400 | $1.323600 / $3.303360 / **$4.626960** |

For reference, the cost of one controlled two-model comparison—one persona, one question, both
models—is:

| Tier | Two-model comparison cost | Status |
|---|---:|---|
| Cheap | $0.00022265 | **Measured** on P001 |
| Mid | $0.00148690 | Extrapolated from the two measured token workloads |
| Expensive | $0.00481975 | Extrapolated from the two measured token workloads |

The calculation definitions are:

- **Student turn:** one student question plus one model answer, so one paid provider call.
- **Full student session:** eight student turns, matching the application's interview turn limit.
- **Default AI-to-AI run:** three personas, eight turns per persona, and one interviewer plus one
  interviewee call per turn. This is 24 calls to each model in the pair, or 48 calls total.
- **Full sweep:** 30 personas x the frozen 32-question instrument = 960 answers per model. The bold
  amount is the cost of running both models in that tier.

## One-time cache pre-warm

The pre-warm covers four suggested questions for 30 personas on Gemini 2.5 Flash Lite: 120 cache
paths. Using the measured Gemini turn gives a **$0.008916 one-time cold-cache extrapolation**:

```text
30 personas x 4 questions x $0.00007430 = $0.008916
```

The 2026-09-04 dry run found one path already cached, leaving 119 potential provider calls, or
**$0.00884170 on the same measured-workload basis**. The script deliberately uses a much more
conservative safety preflight—10,000 input and 2,000 output tokens per path—which reports $0.216000
for a cold cache or $0.214200 for the current 119 misses. Those safety figures are planning limits,
not measured spend and not the expected warm-up bill. After a path is warm, an exact repeat for the
same persona, model, question, and prior-turn history incurs **$0 new provider usage**.

## Measured versus extrapolated

**Measured:** the two P001 token counts and provider-reported costs, their $0.00022265 sum, and the
zero-cost cache replay in `interview_turn`.

**Extrapolated:** every eight-turn session, AI-to-AI run, 30 x 32 sweep, mid-tier or expensive-tier
amount, and cache pre-warm amount. They use real measured token workloads and the catalog rates,
but actual costs can differ. Follow-up prompts accumulate conversation history, model output length
varies, and provider pricing can change. A future report should replace an extrapolated scenario
with its recorded `interview_turn` sum after that scenario is run.

The approximately $5 expensive-model and $0.50 cheap-model figures recalled on the call had no
token logs behind them, so they are not used in this report.
