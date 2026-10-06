#!/bin/bash
# One entry point for DONE.md checks. Runs from anywhere inside the worktree.
set -eo pipefail
ROOT=$(git rev-parse --show-toplevel)
PY=${PY:-/Users/andersonedmond/dev/SyntheticResponderLab/apps/api/.venv/bin/python}
TSC="$ROOT/apps/web/node_modules/.bin/tsc"
case "$1" in
  api) cd "$ROOT/apps/api" && out=$("$PY" -m pytest -q tests/test_demo_mode.py -k "$2" 2>&1) || { echo "$out" | tail -40; exit 1; }
       echo "$out" | tail -3; echo "$out" | grep -qE '[1-9][0-9]* passed' ;;
  # A name pattern that matches nothing still exits 0, so require at least one pass.
  web) cd "$ROOT/apps/web" && rm -rf .test-dist && "$TSC" -p tsconfig.test.json \
         && out=$(node --test --test-isolation=none --test-name-pattern="$2" '.test-dist/tests/**/*.js' 2>&1) \
         && echo "$out" | grep -E '^ℹ (pass|fail)' && grep -qE '^ℹ pass [1-9]' <<<"$out" && grep -qE '^ℹ fail 0' <<<"$out" ;;
  api-all) cd "$ROOT/apps/api" && "$PY" -m pytest -q ;;
  web-all) cd "$ROOT/apps/web" && npm run test:unit ;;
  typecheck) cd "$ROOT/apps/web" && "$TSC" --noEmit -p tsconfig.json ;;
  build) cd "$ROOT/apps/web" && API_BASE_URL=${API_BASE_URL:-https://api.example.invalid} DEPLOYMENT_SHARED_SECRET=${DEPLOYMENT_SHARED_SECRET:-build-placeholder} APP_ACCESS_PASSWORD=${APP_ACCESS_PASSWORD:-build-placeholder} npm run build ;;
  fixtures) cd "$ROOT/apps/api" && "$PY" - <<'PYEOF'
import json, pathlib, sys
d = pathlib.Path("seed_data/demo")
files = sorted(d.glob("*.json"))
assert len(files) >= 3, files
for f in files:
    data = json.loads(f.read_text())
    assert not data.get("provisional"), f"{f} is provisional: run make_demo_fixtures.py"
print("fixtures real:", [f.name for f in files])
PYEOF
  ;;
  *) echo "unknown case $1" >&2; exit 2 ;;
esac
