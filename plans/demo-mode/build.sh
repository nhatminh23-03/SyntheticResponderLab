#!/bin/bash
set -euo pipefail
cd /Users/andersonedmond/SyntheticResponderLab-lin-fixes-demo-mode
export HARNESS_ROOT=/Users/andersonedmond/ai-harness
export HARNESS_BOARD_DIR=/Users/andersonedmond/ai-harness/vault/board
export HARNESS_VAULT_DIR=/Users/andersonedmond/ai-harness/vault
export HARNESS_AGENT=builder
# PYTHONPATH/PYTHONSTARTUP could inject builder-reachable code into wrapper python (B1-r7).
unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT PYTHONPATH PYTHONSTARTUP
CODEX=${CODEX:-codex}
# Bill the builder to the SAME Codex account the refuter already uses for this
# repo (repo->account map in .run/verify-codex/accounts.json, keyed by remote).
# Without this the builder spends whatever ambient ~/.codex login happens to
# hold — so LBL builds were charged to the personal plan while only the cheap
# review half billed LBL. Unmapped repos resolve to None and keep the ambient
# login, which is the correct default; a mapped-but-missing root is loud, not
# silent, but still non-fatal here (the refuter itself fails closed on it).
if [ -z "${CODEX_HOME:-}" ]; then
  # stderr passes straight through: an unresolvable mapped account must be
  # visible in the build log, never swallowed. $LOG does not exist yet here.
  _codex_home=$(python3 -I -c '
import sys
import os
sys.path.insert(0, os.path.join(os.environ["HARNESS_ROOT"], ".claude/skills/verify-codex"))
import refute
home, label, err = refute.resolve_codex_home()
if err:
    sys.stderr.write("== codex account UNRESOLVED (%s): %s\n" % (label, err))
elif home:
    print(home)
') || _codex_home=
  if [ -n "$_codex_home" ]; then
    export CODEX_HOME="$_codex_home"
    echo "== codex account: $CODEX_HOME"
  else
    echo "== codex account: ambient default (~/.codex)"
  fi
fi
REFUTE=${REFUTE:-python3 /Users/andersonedmond/ai-harness/.claude/skills/verify-codex/refute.py}
CHECK=${CHECK:-python3 /Users/andersonedmond/ai-harness/.claude/skills/done/done.py check}
DEFINITION=${DEFINITION:-python3 /Users/andersonedmond/ai-harness/.claude/skills/done/done.py refute}
FPRINT=${FPRINT:-python3 /Users/andersonedmond/ai-harness/.claude/skills/done/done.py fingerprint}
NAME=demo-mode
PLAN=plans/$NAME
LOG=$(mktemp -d "${TMPDIR:-/tmp}/$NAME-build.XXXXXX")
# C1-r13: the log dir feeds the verdict parse — done.py check deny-lists it so no
# builder-authored check (or detached leftover) can rewrite the refuter's report.
export DONE_LOG_DIR=$LOG
# Refuter B1-r4: builder-authored checks can plant git hooks in the repo's git dir;
# every git command this wrapper (and anything it spawns) runs must ignore repo-local
# hooks, or a planted pre-commit executes outside the check fence at snapshot time.
# Refuter B1-r5: the redirect target itself must not be check-writable — prefer the
# root-owned /var/empty; a mktemp fallback is additionally deny-listed by done.py check.
_hooks_off=/var/empty
{ [ -d "$_hooks_off" ] && [ ! -w "$_hooks_off" ]; } || _hooks_off=$(mktemp -d)
# Refuter B1-r6/B1-r8: STRUCTURAL closure of the config-plant class — wrapper git
# reads NO ambient global/system config at all (a --global clean-filter, alias,
# pager, or any other exec-bearing key a check plants is inert here), executes no
# repo hooks or fsmonitor, and carries the operator's identity captured BEFORE the
# blinding so snapshot commits stay correctly attributed.
_gname=$(git config user.name 2>/dev/null || echo done-wrapper)
_gmail=$(git config user.email 2>/dev/null || echo done-wrapper@localhost)
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_CONFIG_COUNT=4 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=$_hooks_off \
       GIT_CONFIG_KEY_1=core.fsmonitor GIT_CONFIG_VALUE_1=false \
       GIT_CONFIG_KEY_2=user.name GIT_CONFIG_VALUE_2="$_gname" \
       GIT_CONFIG_KEY_3=user.email GIT_CONFIG_VALUE_3="$_gmail"
# Refuter B1-r10: pin the repo's identity BEFORE any builder-authored code runs —
# done.py's check fence trusts these over post-hoc git discovery, which a swapped
# .git pointer or a decoy .git planted at the plan dir could otherwise hijack.
export DONE_GIT_DIR=$(git rev-parse --path-format=absolute --git-dir) \
       DONE_GIT_COMMON=$(git rev-parse --path-format=absolute --git-common-dir) \
       DONE_GIT_TOPLEVEL=$(git rev-parse --show-toplevel)
# Refuter B1-r11: dispatch shape is asserted by the WRAPPER, not inferred from
# where the builder-controlled DONE.md happens to resolve.
export DONE_DISPATCH=1
export DONE_UI_REQUIRED=0
ui_feedback_excludes=()
if [ "$DONE_UI_REQUIRED" = 1 ]; then ui_feedback_excludes=(":(exclude)$PLAN/ui-feedback.md"); fi
board() {
  # The live runtime's board.py, not the worktree copy: a builder must not be able to rewrite how its claim or verdict is recorded.
  HARNESS_BOARD_DIR=/Users/andersonedmond/ai-harness/vault/board HARNESS_AGENT="$1" python3 /Users/andersonedmond/ai-harness/scripts/board.py "${@:2}"
}
# ponytail: failed stages point to local logs; SIGKILL and failed board writes require bgjob logs.
stage=definition
BUILD_START=$(git rev-parse HEAD) || BUILD_START=unresolved
report_blocker=true
build_exit() {
  rc=$?
  trap - EXIT
  python3 -I /Users/andersonedmond/ai-harness/.claude/skills/done/done.py decisions-tail "$PLAN/DECISIONS.md" "$BUILD_START" || true
  if [ "$rc" -ne 0 ] && [ "$report_blocker" = true ]; then
    board builder post "$NAME" blocker "build $NAME failed at $stage (exit $rc); logs: $LOG" --agent builder || true
  fi
  exit "$rc"
}
trap build_exit EXIT
snapshot() {
  if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -qm "$NAME: build round $round"
  fi
}
# Convergence circuit breaker. build.sh is ONE round; the outer loop is a human or
# agent re-dispatching it, so nothing here ever counted how many rounds a plan had
# burned. stockout-roas-attribution reached round 34 on 2026-09-09 — every round
# passing all of its own checks (99/99 ALL DONE) and every round refuted with one
# NEW blocker derived from the previous round's fix. That is the documented failure
# mode of review loops, not evidence of real defects: reviewing already-correct code
# makes the defect count go UP, because the reviewer's standards drift and its scope
# expands. So the loop needs a stop it cannot argue with.
#
# ponytail: a flat count of consecutive non-GO rounds, no derivative-blocker
# detection. Cheap and unfoolable; if it stops a plan that was genuinely converging,
# raise DONE_MAX_REFUTE_ROUNDS for that run.
#
# Refute mode (Anderson 2026-09-11, after sigmas ate ~64% of 24h bgjob runtime in
# refute cycles): 'end' keeps Codex out of the per-round loop — the DoD is refuted
# once when the arc opens, not on every invocation, and the ceilings drop so an arc
# is build -> final refute -> one fix pass on what it found -> receipt, then a
# human. 'end' is the dispatch default everywhere; DONE_REFUTE_MODE=loop opts a
# trust-boundary arc (auth, migrations, money paths) back into the original
# refute-every-round behavior.
DONE_REFUTE_MODE=${DONE_REFUTE_MODE:-end}
if [ "$DONE_REFUTE_MODE" = end ]; then
  DONE_MAX_REFUTE_ROUNDS=${DONE_MAX_REFUTE_ROUNDS:-2}
  DONE_MAX_TOTAL_ROUNDS=${DONE_MAX_TOTAL_ROUNDS:-3}
fi
ROUNDS_FILE=${DONE_ROUNDS_FILE:-$(git rev-parse --git-dir)/done-rounds-$NAME}
DONE_MAX_REFUTE_ROUNDS=${DONE_MAX_REFUTE_ROUNDS:-5}
mkdir -p "$(dirname "$ROUNDS_FILE")"
rounds=$(cat "$ROUNDS_FILE" 2>/dev/null || echo 0)
case "$rounds" in ''|*[!0-9]*) rounds=0 ;; esac
# The streak above is not a spend ceiling: a GO clears it, so a loop that
# alternates GO and non-GO never reaches DONE_MAX_REFUTE_ROUNDS and runs forever.
# That is not hypothetical — on 2026-09-09 stockout-roas-attribution sat at build
# 36 with no streak file at all (a GO had deleted it) and tenant-brain-split read
# 1 at build 19, while both kept spending Codex rounds every few minutes. So the
# streak keeps its job (it pairs with BASE_FILE, which a GO must clear to close the
# review arc) and a second counter carries the ceiling: every round increments it,
# nothing but a human clears it.
TOTAL_FILE=${DONE_TOTAL_FILE:-$(git rev-parse --git-dir)/done-total-$NAME}
DONE_MAX_TOTAL_ROUNDS=${DONE_MAX_TOTAL_ROUNDS:-12}
total=$(cat "$TOTAL_FILE" 2>/dev/null || echo 0)
case "$total" in ''|*[!0-9]*) total=0 ;; esac
# Content identity of the last Sol-refuted DoD (recorded AFTER Sol's additions
# land, so the amended text is what the sha vouches for). A relaunch on unchanged
# text skips the re-refute: on 2026-09-12 brain-file-ingest bought three DoD
# refutes for one arc (crash + two plumbing relaunches), growing 8 outcomes to 44
# with zero code built — that is reviewer drift purchased at full price. Any edit
# to DONE.md changes the sha and forces a fresh refute; counters do not.
DOD_SHA_FILE=${DONE_DOD_SHA_FILE:-$(git rev-parse --git-dir)/done-dod-sha-$NAME}
# Refuter B1-r3: a retry must not re-baseline the review at its own HEAD — earlier
# invocations' refuted implementation would drop out of every later range, letting a
# narrow GO stand for the branch. Persist the FIRST invocation's base; every refute
# spans base..HEAD until a GO closes the arc (GO clears it with the rounds file, so
# the next dispatch baselines fresh at the GO'd HEAD).
# Refuter B2-r4: rounds recorded but base missing = someone deleted review state —
# refuse to silently adopt HEAD as a fresh baseline.
BASE_FILE=${DONE_BASE_FILE:-$(git rev-parse --git-dir)/done-base-$NAME}
if [ -s "$BASE_FILE" ] && git rev-parse -q --verify "$(cat "$BASE_FILE")^{commit}" >/dev/null; then
  BASE=$(cat "$BASE_FILE")
elif [ "$rounds" -gt 0 ]; then
  board builder post "$NAME" blocker "review-state inconsistent: $rounds refuted round(s) recorded but the base file is missing — refusing to re-baseline at HEAD. Restore $BASE_FILE or rm $ROUNDS_FILE after a human review." --agent builder || true
  echo "build $NAME: review-state inconsistent (rounds=$rounds, base missing) — refusing to adopt HEAD as baseline."
  report_blocker=false
  exit 2
else
  BASE=$(git rev-parse HEAD)
  echo "$BASE" >"$BASE_FILE"
fi
# Checked BEFORE the builder runs: the point is to not spend the tokens at all.
if [ "$rounds" -ge "$DONE_MAX_REFUTE_ROUNDS" ]; then
  board builder post "$NAME" blocker "converged: $rounds consecutive non-GO refuter rounds (BLOCKERS or INCONCLUSIVE). Needs a human decision on whether to keep building. Reset with: rm $ROUNDS_FILE" --agent builder || true
  echo "build $NAME: CONVERGED after $rounds non-GO rounds — stopping instead of spending another round."
  echo "  reset with: rm $ROUNDS_FILE   (or DONE_MAX_REFUTE_ROUNDS=$((rounds + 3)) to allow more)"
  report_blocker=false
  exit 2
fi
budget_rc=0
budget=$(python3 -I "$HARNESS_ROOT/.claude/skills/done/done.py" budget-reserve "$TOTAL_FILE" "$DONE_MAX_TOTAL_ROUNDS" "$NAME") || budget_rc=$?
read -r total effective_ceiling <<< "$budget"
if [ "$budget_rc" -eq 2 ]; then
  board builder post "$NAME" blocker "spent: $total refuter rounds on this goal, GO rounds included. Extend with: python3 done.py extend plans/$NAME --rounds N --reason TEXT" --agent builder || true
  echo "build $NAME: SPENT $total rounds on this goal — stopping instead of spending another round."
  echo "  extend with: python3 done.py extend plans/$NAME --rounds N --reason TEXT"
  report_blocker=false
  exit 2
fi
# Refuter B1-r13: the ceiling counts SPEND, so reserve it BEFORE the first model
# call — an invocation that dies mid-build (checks never pass, builder crash)
# must still advance the counter, or repeated relaunches spend forever under it.
[ "$budget_rc" -eq 0 ] || exit "$budget_rc"
total=$((total + 1))
if [ "$DONE_REFUTE_MODE" = end ] && [ "$rounds" -gt 0 ]; then
  # Mid-arc (streak > 0): the DoD was refuted when the arc opened; re-refuting it
  # every invocation spends a Codex call and grows scope while the fix is pending.
  echo "== refute DONE.md: skipped (end mode, mid-arc streak $rounds)"
elif [ -s "$DOD_SHA_FILE" ] && [ "$($FPRINT "$PLAN/DONE.md")" = "$(cat "$DOD_SHA_FILE")" ]; then
  # These exact outcomes already survived a Sol refute; a relaunch re-buying the
  # same review is spend, not defect-finding. The fingerprint ignores checkbox
  # flips and check-command repairs (builder-routine), so only outcome/goal edits
  # re-refute (see DOD_SHA_FILE note above and done.py fingerprint).
  echo "== refute DONE.md: skipped (unchanged since last refute, sha $(cat "$DOD_SHA_FILE" | cut -c1-12))"
else
  echo "== refute DONE.md (Astra)"
  rc=0
  $DEFINITION "$PLAN/DONE.md" >"$LOG/definition" 2>&1 || rc=$?
  tail -20 "$LOG/definition"
  # A traceback also exits 1; require the review's own completion marker.
  case "$rc" in
    0) grep -qx 'done refute: Sol found nothing missing' "$LOG/definition" ;;
    1) grep -Eq '^done refute: Sol added [1-9][0-9]* missing outcome\(s\) — write a check for each:$' "$LOG/definition" ;;
    *) false ;;
  esac
  # Record the amended DoD's content identity only after the refute completed.
  $FPRINT "$PLAN/DONE.md" >"$DOD_SHA_FILE"
fi
cat "$PLAN/DONE.md"
passed=false
for round in 1 2 3; do
  # Only round 1 checks before the builder. Rounds 2-3 reuse the previous round's
  # post-builder check below: same committed tree, so a re-run only repeats a
  # 15-23 min suite (Anderson 2026-09-26: remove redundant check runs).
  # The pre-builder pass is opt-in (DONE_PRECHECK=1): it only matters when the tree
  # may already pass (a re-check after merging a prerequisite). On a fresh dispatch the
  # guard has just run every check red, and on a relaunch the builder is going to run
  # anyway, so the pass re-ran a 20-25 min suite for nothing (Anderson 2026-09-29: "We
  # should only be doing tests thatre necessary").
  if [ "$round" = 1 ] && [ "${DONE_PRECHECK:-0}" != 1 ]; then
    snapshot
    echo "== check before builder: skipped (DONE_PRECHECK=1 runs it)"
    echo "(no check run before round 1: the planner's checks start red. Run the focused check for each outcome you change.)" >"$LOG/check"
  fi
  if [ "$round" = 1 ] && [ "${DONE_PRECHECK:-0}" = 1 ]; then
    stage="check before builder"
    echo "== check before builder ($(date '+%H:%M'))"
    # Commit leftovers (e.g. a stopped build's edits) first, as the builder pass's
    # snapshot used to, so the guards below see only what the check itself changed.
    snapshot
    # The skip needs a closed review arc too (rounds = 0): after a non-GO verdict
    # the refuter's findings are the builder's work even when every check passes,
    # and re-refuting unchanged code only burns a round (refute of 60d37f8, B1).
    if $CHECK "$PLAN/DONE.md" >"$LOG/check" 2>&1 && grep -q ' — ALL DONE$' "$LOG/check" \
       && [ "$rounds" -eq 0 ]; then
      # Already done (e.g. a re-check after merging a prerequisite branch): no
      # builder pass. Same guards as a post-builder pass.
      git diff --quiet HEAD -- . ":(exclude)$PLAN/DONE.md" ${ui_feedback_excludes[@]+"${ui_feedback_excludes[@]}"}
      [ -z "$(git ls-files --others --exclude-standard -- . ${ui_feedback_excludes[@]+"${ui_feedback_excludes[@]}"})" ]
      snapshot
      echo "== all checks already pass; no builder pass needed"
      passed=true
      break
    fi
  fi
  stage="builder round $round"
  echo "== codex build round $round ($(date '+%H:%M'))"
  brief=$(board builder brief "$NAME" --agent builder)
  ui_images=()
  if [ "$DONE_UI_REQUIRED" = 1 ]; then
    while IFS= read -r image; do ui_images+=(-i "$image"); done < <(python3 /Users/andersonedmond/ai-harness/.claude/skills/done/done.py ui-images "$PLAN")
  fi
  $CODEX exec ${ui_images[@]+"${ui_images[@]}"} --cd /Users/andersonedmond/SyntheticResponderLab-lin-fixes-demo-mode --sandbox workspace-write --skip-git-repo-check -m gpt-6-astra \
    "$brief

Board protocol override for this sandboxed run: the Agent Board directory is wrapper-owned and NOT writable from your sandbox — expected, not an error. The planner intent covering plans/$NAME is already posted; this wrapper posts your claim on ALL DONE, any blocker, and the refuter finding. Never attempt a board write and never block the build on one — report a genuine blocker by printing BLOCKER: <text> and stopping.

$(cat "$PLAN/BRIEF.md")

$(if [ "$DONE_UI_REQUIRED" = 1 ] && [ -f "$PLAN/ui-feedback.md" ]; then cat "$PLAN/ui-feedback.md"; fi)

The wrapper re-runs every check in DONE.md right after this pass, including whole-suite regression and mutation checks, and gives you that output next round. Run the focused check for each outcome you change as you go; run whole-suite regression or mutation scripts at most once, as your last step.

Record every design choice the plan did not dictate in plans/$NAME/DECISIONS.md.
Add a table row with Where as file:line and a concrete To change / revert instruction.
Keep its columns exactly | # | Decision | Why | Where | To change / revert | Status |, rows numbered 1, 2, 3.

Round $round. Current done.py check output:
$(tail -30 "$LOG/check")" </dev/null >"$LOG/codex-$round" 2>&1
  tail -40 "$LOG/codex-$round"
  stage="commit round $round"
  snapshot
  stage="check round $round"
  if $CHECK "$PLAN/DONE.md" >"$LOG/check" 2>&1 && grep -q ' — ALL DONE$' "$LOG/check"; then
    # check may update DONE's boxes, but must not silently mutate checked implementation.
    git diff --quiet HEAD -- . ":(exclude)$PLAN/DONE.md" ${ui_feedback_excludes[@]+"${ui_feedback_excludes[@]}"}
    [ -z "$(git ls-files --others --exclude-standard -- . ${ui_feedback_excludes[@]+"${ui_feedback_excludes[@]}"})" ]
    snapshot
    passed=true
    break
  fi
  tail -25 "$LOG/check"
  if grep -q 'UI evidence remains blocking — needs-eyeball' "$LOG/check"; then
    echo "needs-eyeball: awaiting recorded human acceptance; build stopped without ALL DONE"
    exit 3
  fi
done
if [ "$passed" != true ]; then
  board builder post "$NAME" blocker "three rounds without ALL DONE; logs: $LOG
$(tail -10 "$LOG/check")" --agent builder
  report_blocker=false
  exit 1
fi
stage=claim
claim=$(board builder post "$NAME" claim "ALL DONE at $(git rev-parse --short HEAD)" --agent builder)
claim=${claim##*/#}
[[ "$claim" =~ ^[0-9]+$ ]]
stage=refuter
echo "== diff refuter (Astra) on $BASE..HEAD"
rc=0
$REFUTE --range "$BASE..HEAD" --timeout 600 >"$LOG/refute" 2>&1 || rc=$?
tail -40 "$LOG/refute"
# Only this invocation's exact authoritative heading counts; keep the full coverage report.
# -I: isolated mode — cwd is the WORKTREE, and a builder-committed pathlib.py/re.py
# must never shadow the stdlib in this unfenced parser (refuter B1-r7).
verdict=$(python3 -I - "$LOG/refute" "$rc" <<'VERDICT'
import pathlib, re, sys
text = pathlib.Path(sys.argv[1]).read_text()
heads = re.findall(r'^# verify-codex refuter — (GO|BLOCKERS|INCONCLUSIVE)$', text, re.M)
print(heads[0] if sys.argv[2] == '0' and len(heads) == 1 else 'INCONCLUSIVE')
VERDICT
)
report=$(cat "$LOG/refute")
stage=finding
case "$verdict" in
  GO) board refuter post "$NAME" finding "Confirmed #$claim: $report" --agent refuter ;;
  BLOCKERS) board refuter post "$NAME" finding "Refuted #$claim: $report" --agent refuter ;;
  *) board refuter post "$NAME" finding "Inconclusive #$claim: refuter exit $rc; $report" --agent refuter ;;
esac
git diff --stat "$BASE..HEAD" | tail -15
tail -15 "$LOG/check"
# GO clears the streak; anything else advances it toward the circuit breaker above.
# INCONCLUSIVE counts too — a refuter that cannot answer must not buy free rounds.
# (The total was already reserved before the first model call — B1-r13.)
if [ "$verdict" = GO ]; then
  rm -f "$ROUNDS_FILE" "$BASE_FILE"
else
  echo "$((rounds + 1))" >"$ROUNDS_FILE"
  echo "== non-GO round $((rounds + 1)) of $DONE_MAX_REFUTE_ROUNDS before the loop stops for a human"
fi
echo "== round $total of $effective_ceiling spent on $NAME"
echo "build $NAME: $verdict; claim #$claim; logs: $LOG"
report_blocker=false
[ "$verdict" = GO ]
