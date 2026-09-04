#!/usr/bin/env bash
# Deterministic driver around a non-deterministic implementer.
#
# Codex implements one SPEC.md checkbox at a time; scripts/verify.sh is the gate; Codex then acts as
# an adversarial refuter over its own diff; only then does the task commit. The loop, the ordering,
# the budget ceiling and the stop conditions are plain bash on purpose — the model never decides
# whether it is done.
#
# Usage: scripts/build-loop.sh [task-id ...]   (default: every task in ORDER)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO=$(pwd)
LOGDIR="$HOME/.neo-build-loop"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/run-$(date +%Y%m%d-%H%M%S).log"
BRANCH=anderson/interview-persona-loader

# --- budget guard ------------------------------------------------------------
# OpenRouter usage is cumulative across the account, so the ceiling is an absolute number, not a
# delta we have to track ourselves. Baseline at build start was 39.32 of 87 credits; Anderson
# authorised $20, so the loop dies at 59.32 no matter how it got there.
USAGE_CEILING=59.32
OR_KEY=$(grep '^OPENROUTER_API_KEY=' apps/api/.env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"'')

log() { printf '%s %s\n' "$(date '+%H:%M:%S')" "$*" | tee -a "$LOG"; }

budget_ok() {
  [ -z "$OR_KEY" ] && { log "[budget] no OpenRouter key readable — treating as no spend"; return 0; }
  local used
  used=$(curl -s --max-time 20 -H "Authorization: Bearer $OR_KEY" \
    https://openrouter.ai/api/v1/credits | python3 -c 'import sys,json
try: print(json.load(sys.stdin)["data"]["total_usage"])
except Exception: print("")' 2>/dev/null)
  if [ -z "$used" ]; then
    log "[budget] could not read usage — STOPPING rather than spending blind"
    return 1
  fi
  log "[budget] OpenRouter total_usage=\$$used (ceiling \$$USAGE_CEILING)"
  python3 -c "import sys; sys.exit(0 if float('$used') < float('$USAGE_CEILING') else 1)"
}

codex_run() {  # codex_run <prompt-file>
  codex exec -C "$REPO" -s workspace-write -c approval_policy='"never"' - < "$1" 2>&1 | tee -a "$LOG"
}

# --- task table --------------------------------------------------------------
# id|one-line goal. Order is dependency order; do not shuffle.
read -r -d '' TASKS <<'EOT'
P0.0|The API test suite is RED at baseline: 31 failed / 33 passed, e.g. tests/test_health.py::test_non_health_endpoints_require_deployment_secret_when_configured asserts 200 but gets 503 even in isolation. Diagnose the shared cause and fix it. Do not delete, skip or xfail tests to go green. If a test encodes a stale requirement, fix the code; if the fixture is wrong, fix the fixture and say so in the commit message.
P0.2|Fix the fit_tier judge bug in interview_prompt_builder.py around line 283: it falls back to fit_tier="unknown" when the column is blank and then scores fit_tier_alignment against that placeholder, so one of four grounding dimensions scores noise. Score the dimension only when a real tier exists, otherwise omit it from the score and mark it not-applicable. Never feed fit_tier into the interview prompt.
P0.3|Create analysis/screen_counts.R reporting N at every screen step over the PUMS frame used by research/neo_persona_set (raw, detached single-family, income >= 100k ADJINC-adjusted, householder age 30-65, final weighted draw). Read the screens from that pipeline, do not re-invent them. If the parquet priors are not on this branch, read personas-B.csv and report what is derivable, stating clearly what is missing.
P1.1|Promote the demo interview screen to a real standalone section at /interview in apps/web, added to the app nav. Keep it OUT of the gated study workflow: no audience/product/market/survey/experiment prerequisite. Reuse the existing components; do not redesign.
P1.2|Add GET /api/v1/personas serving the 30 fixed personas from the database, seeded from personas-B.csv via a migration or seed script. Point the /interview page at it. Remove the DEMO_PERSONA_CSV filesystem fallback from the production path.
P1.5|Add an interview_turn table (study_id, persona_id, session_id, role, text, model, tokens_in, tokens_out, cost_usd, created_at) with a migration, and persist every interview turn with its measured token counts and cost. This is the data the budget answer depends on, so cost_usd must be computed from real usage numbers returned by the provider, never estimated.
P3.1|Add apps/api/src/services/interview_cache.py: cache key = hash(persona_id, model, question, prior-turn-hash). A repeated question on a repeated persona returns the stored answer at zero cost; a genuinely new question calls the provider. Expose CACHE_MODE with values cache_first (default), replay_only and off. Wire it into the interview path.
P3.3|Add apps/api/src/services/llm_budget.py with RUN_BUDGET_USD (default 0.75) and a NEO_LLM_BUDGET_USD env override, enforced as a hard pre-flight check and a hard stop mid-run. A run that would exceed its budget must refuse to start and say what it would have cost. Include a per-class aggregate cap.
P2.1|Add apps/api/src/services/model_catalog.py with a MODEL_TIERS table (cheap/mid/expensive), each entry carrying a real price per 1M tokens, and expose interviewer-model and interviewee-model pickers in the /interview UI. Cheapest is the default; expensive is opt-in per run.
P2.2|Add a persona-count selector to the AI-to-AI run: floor 3, default 3, ceiling 30, with the pre-flight cost estimate updating as the count changes.
P2.6|Add a live cost meter to the interview UI plus a pre-flight estimate rendered before a run starts, both driven by the real per-token prices in model_catalog and the measured usage in interview_turn.
P2.3|Add the interviewer agent: given the research brief and the transcript so far, it asks the next question derived from the previous answer rather than replaying a fixed list. Cap the number of turns per run from the budget, not from a magic number.
P2.4|Add the side-by-side comparison view: one persona, one question, N models, answers rendered next to each other so the cheap-vs-expensive difference is visible. This is the pedagogical payload of the section.
P2.5|Add post-interview scoring (fit_tier and emotional classification) computed only after the transcript exists, displayed with the label "scored after the interview, never before". Depends on P0.2.
P1.6|Add transcript export to CSV and markdown from the /interview section.
P4.1|Create the analysis/ R project: renv lockfile, directory layout, and analysis/tests/test_all.R as a real (initially small) test suite that scripts/verify.sh will pick up.
P4.6|Implement the five non-LLM respondent baselines in R over the 32-question instrument: marginal sampler, multivariate normal, Gaussian copula, stratum mean, and k-NN lookup. CRITICAL: they must be fit on held-out data. Split the real 600, fit on one half, evaluate on the other. A baseline fit and evaluated on the same rows is a bug, not a result — assert against it in the test suite.
P4.2|Implement Arm A in R: apply the existing hard screens, randomly draw 600 synthetic respondents, compare to the real 600. Fixed seed.
P4.3|Implement Arm B in R: draw 600 matched to the observed demographic distribution of the real 600 using iterative proportional fitting against the PUMS frame. Fixed seed.
P4.5|Implement the test battery keyed to question type: t-test for continuous, Wald test, chi-square for categorical, plus TOST equivalence tests with a pre-registered margin. Report effect sizes and confidence intervals, never bare p-values.
P4.8|Add analysis/run_all.R producing one reproducible HTML report covering every arm and every test, with all seeds fixed, rebuildable from scratch.
P1.4|Route the /interview section through the FastAPI interview endpoints (POST /api/v1/studies/{id}/interview/chat) instead of the Next.js route calling OpenRouter directly. Keep the Next.js demo route working as a fallback until this passes.
P5.3|Add a no-login path for classroom use so a class of students can reach /interview without hitting an auth wall, gated behind an env flag that is off by default.
P5.4|Write docs/instructor-guide.md: what the section teaches, what to click, what students should notice, and what a run costs.
EOT

ORDER=$(printf '%s\n' "$TASKS" | cut -d'|' -f1)
[ $# -gt 0 ] && ORDER="$*"

log "=== build loop start on $(git rev-parse --abbrev-ref HEAD) ==="
git rev-parse --abbrev-ref HEAD | grep -qx "$BRANCH" || { log "REFUSING: not on $BRANCH"; exit 1; }

for id in $ORDER; do
  goal=$(printf '%s\n' "$TASKS" | grep "^$id|" | cut -d'|' -f2-)
  [ -z "$goal" ] && { log "!! unknown task $id"; continue; }
  git diff --quiet && git diff --cached --quiet || { log "!! working tree dirty before $id — stopping"; exit 1; }

  budget_ok || { log "!! BUDGET CEILING REACHED — stopping before $id"; exit 2; }
  log "--- $id ---"

  cat > /tmp/cx-impl.txt <<EOF
You are implementing exactly one checkbox from SPEC.md in this repository. Read SPEC.md first,
especially the "Do not touch" list and the "Assumptions this build runs on" table — both are binding.

TASK $id: $goal

Rules:
- Implement only this task. Do not start other checkboxes.
- Match the surrounding code's style, naming and structure. This is a shared academic repo.
- Every non-trivial branch or calculation leaves one runnable check behind (a pytest test, or an
  assertion in the R test suite). No new test frameworks.
- Never put anything from the real 600 survey answers into a model prompt.
- Do not run any command that spends provider credits beyond a single smoke call.
- When done, run ./scripts/verify.sh and fix what you broke.
EOF
  codex_run /tmp/cx-impl.txt

  ok=0
  for attempt in 1 2 3; do
    if ./scripts/verify.sh >/tmp/vg.log 2>&1; then ok=1; break; fi
    log "verify failed (attempt $attempt) — sending failures back to Codex"
    { echo "./scripts/verify.sh is failing after your change to task $id. Fix the cause, do not weaken or skip tests. Output:"; tail -60 /tmp/vg.log; } > /tmp/cx-fix.txt
    codex_run /tmp/cx-fix.txt
  done
  [ $ok -eq 1 ] || { log "!! $id could not be made green in 3 rounds — stopping for a human"; exit 3; }

  log "$id verify PASS — refuter round"
  cat > /tmp/cx-ref.txt <<EOF
Act as an adversarial REFUTER, not a reviewer. Your job is to find what is WRONG with the change
just made for task $id — run \`git diff HEAD\` to see it.

Hunt specifically for: logic that is correct on the happy path and wrong on an edge; a test that
cannot actually fail; an error path that is silently swallowed; a cost or budget check that can be
bypassed; a statistical routine fit and evaluated on the same rows; anything that contradicts
SPEC.md's stated intent for $id.

If you find a real defect, fix it and say what it was. If you find nothing, say NO FINDINGS and
change nothing. Do not invent findings to look thorough.
EOF
  codex_run /tmp/cx-ref.txt

  ./scripts/verify.sh >/tmp/vg2.log 2>&1 || { log "!! refuter fix broke the suite for $id — stopping"; tail -30 /tmp/vg2.log | tee -a "$LOG"; exit 4; }

  git add -A -- . ":(exclude).build-loop"
  git commit -q -m "$id: $(printf '%s' "$goal" | cut -c1-68)

Built by the SPEC.md build loop (scripts/build-loop.sh): Codex implemented,
scripts/verify.sh gated, Codex refuted its own diff.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" \
    && git tag -f "build/$id" >/dev/null 2>&1 \
    && log "$id COMMITTED $(git rev-parse --short HEAD)"

  python3 - "$id" <<'PY'
import re, sys, pathlib
tid = sys.argv[1]
p = pathlib.Path("SPEC.md"); s = p.read_text()
s2 = re.sub(r"- \[ \] \*\*%s\*\*" % re.escape(tid), "- [x] **%s**" % tid, s, count=1)
if s2 != s:
    p.write_text(s2)
PY
  git add SPEC.md && git commit -q -m "spec: tick $id" 2>/dev/null
done

log "=== build loop finished ==="
./scripts/verify.sh 2>&1 | tail -5 | tee -a "$LOG"
