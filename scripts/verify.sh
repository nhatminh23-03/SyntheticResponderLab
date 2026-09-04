#!/usr/bin/env bash
# Test gate for the build loop. Runs whatever exists; a suite that is absent is skipped loudly,
# never silently counted as a pass. Exit non-zero if anything that exists fails.
#
# The web build needs production-like env vars that live in apps/web/.env.local. `next build` runs
# with NODE_ENV=production, so the local-dev escape hatch in server-env.ts does not apply and the
# vars must be exported into the build's environment explicitly.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
rc=0

if [ -f apps/web/package.json ]; then
  echo "[verify] web build"
  # Sourced inside a subshell on purpose: these are web-only vars and leaking DEPLOYMENT_SHARED_SECRET
  # into the pytest process below makes 31 API tests fail with 503s.
  (
    if [ -f apps/web/.env.local ]; then set -a; . ./apps/web/.env.local; set +a; fi
    # A clean checkout has blank production-only values in .env.example. The build only validates
    # these strings; it does not contact the configured backend, so isolated verify-only values keep
    # the gate runnable without requiring developer or deployment secrets.
    export API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
    export DEPLOYMENT_SHARED_SECRET="${DEPLOYMENT_SHARED_SECRET:-verify-only-shared-secret}"
    export APP_ACCESS_PASSWORD="${APP_ACCESS_PASSWORD:-verify-only-access-password}"
    npm --prefix apps/web run build
  ) >/tmp/verify-web.log 2>&1 \
    || { echo "[verify] FAIL web"; grep -E "^Error|error TS|Failed to compile" /tmp/verify-web.log | head -20; rc=1; }
fi

PY=apps/api/.venv/bin/python
[ -x "$PY" ] || PY=$(command -v python3)
if [ -d apps/api/tests ]; then
  echo "[verify] api pytest"
  (cd apps/api && "../../$PY" -m pytest tests -q) >/tmp/verify-api.log 2>&1 \
    || { echo "[verify] FAIL api"; tail -25 /tmp/verify-api.log; rc=1; }
else
  echo "[verify] SKIP api (no apps/api/tests)"
fi

if [ -f analysis/tests/test_all.R ]; then
  echo "[verify] R suite"
  Rscript analysis/tests/test_all.R >/tmp/verify-r.log 2>&1 \
    || { echo "[verify] FAIL R"; tail -25 /tmp/verify-r.log; rc=1; }
else
  echo "[verify] SKIP R (no analysis/tests/test_all.R)"
fi

[ $rc -eq 0 ] && echo "[verify] PASS"
exit $rc
