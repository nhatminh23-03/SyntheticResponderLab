#!/bin/bash
set -euo pipefail
cd /Users/andersonedmond/SyntheticResponderLab-lin-classroom-feedback
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
NAME=lin-classroom-feedback
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
board() {
  # The live runtime's board.py, not the worktree copy: a builder must not be able to rewrite how its claim or verdict is recorded.
  HARNESS_BOARD_DIR=/Users/andersonedmond/ai-harness/vault/board HARNESS_AGENT="$1" python3 /Users/andersonedmond/ai-harness/scripts/board.py "${@:2}"
}
# ponytail: failed stages point to local logs; SIGKILL and failed board writes require bgjob logs.
stage=definition
trap 'rc=$?; if [ "$rc" -ne 0 ]; then board builder post "$NAME" blocker "build $NAME failed at $stage (exit $rc); logs: $LOG" --agent builder || true; fi' EXIT
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
  trap - EXIT
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
  trap - EXIT
  exit 2
fi
if [ "$total" -ge "$DONE_MAX_TOTAL_ROUNDS" ]; then
  board builder post "$NAME" blocker "spent: $total refuter rounds on this goal, GO rounds included. Needs a human decision on whether it is still converging. Reset with: rm $TOTAL_FILE" --agent builder || true
  echo "build $NAME: SPENT $total rounds on this goal — stopping instead of spending another round."
  echo "  reset with: rm $TOTAL_FILE   (or DONE_MAX_TOTAL_ROUNDS=$((total + 3)) to allow more)"
  trap - EXIT
  exit 2
fi
# Refuter B1-r13: the ceiling counts SPEND, so reserve it BEFORE the first model
# call — an invocation that dies mid-build (checks never pass, builder crash)
# must still advance the counter, or repeated relaunches spend forever under it.
total=$((total + 1))
echo "$total" >"$TOTAL_FILE"
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
cat "$PLAN/DONE.md"
passed=false
for round in 1 2 3; do
  stage="builder round $round"
  echo "== codex build round $round ($(date '+%H:%M'))"
  $CHECK "$PLAN/DONE.md" >"$LOG/check" 2>&1 || true
  brief=$(board builder brief "$NAME" --agent builder)
  $CODEX exec --cd /Users/andersonedmond/SyntheticResponderLab-lin-classroom-feedback --sandbox workspace-write --skip-git-repo-check -m gpt-6-astra \
    "$brief

Board protocol override for this sandboxed run: the Agent Board directory is wrapper-owned and NOT writable from your sandbox — expected, not an error. The planner intent covering plans/$NAME is already posted; this wrapper posts your claim on ALL DONE, any blocker, and the refuter finding. Never attempt a board write and never block the build on one — report a genuine blocker by printing BLOCKER: <text> and stopping.

$(cat "$PLAN/BRIEF.md")

Round $round. Current done.py check output:
$(tail -30 "$LOG/check")" </dev/null >"$LOG/codex-$round" 2>&1
  tail -40 "$LOG/codex-$round"
  stage="commit round $round"
  snapshot
  stage="check round $round"
  if $CHECK "$PLAN/DONE.md" >"$LOG/check" 2>&1 && grep -q ' — ALL DONE$' "$LOG/check"; then
    # check may update DONE's boxes, but must not silently mutate checked implementation.
    git diff --quiet HEAD -- . ":(exclude)$PLAN/DONE.md"
    [ -z "$(git ls-files --others --exclude-standard)" ]
    snapshot
    passed=true
    break
  fi
  tail -25 "$LOG/check"
done
if [ "$passed" != true ]; then
  board builder post "$NAME" blocker "three rounds without ALL DONE; logs: $LOG
$(tail -10 "$LOG/check")" --agent builder
  trap - EXIT
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
echo "== round $total of $DONE_MAX_TOTAL_ROUNDS spent on $NAME"
echo "build $NAME: $verdict; claim #$claim; logs: $LOG"
trap - EXIT
[ "$verdict" = GO ]
