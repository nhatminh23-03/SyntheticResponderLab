#!/usr/bin/env bash

set -euo pipefail

patterns=(
  '-----BEGIN PRIVATE KEY-----'
  '"type"[[:space:]]*:[[:space:]]*"service_account"'
  '"private_key"[[:space:]]*:'
  'GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON=.*\{'
)

blocked_path_patterns=(
  '(^|/)[^/]*service-account[^/]*\.json$'
  '(^|/)[^/]*google-credentials[^/]*\.json$'
  '(^|/)apps/api/cra-applying-sql-[^/]*\.json$'
)

staged_files=()
while IFS= read -r path; do
  staged_files+=("$path")
done < <(git diff --cached --name-only --diff-filter=ACMR)

if [ ${#staged_files[@]} -eq 0 ]; then
  exit 0
fi

failed=0

for path in "${staged_files[@]}"; do
  for path_pattern in "${blocked_path_patterns[@]}"; do
    if [[ "$path" =~ $path_pattern ]]; then
      echo "Secret check failed: blocked credential-like path staged: $path" >&2
      failed=1
      break
    fi
  done

  if ! git cat-file -e ":$path" 2>/dev/null; then
    continue
  fi

  staged_content="$(git show ":$path" 2>/dev/null || true)"
  if [ -z "$staged_content" ]; then
    continue
  fi

  for pattern in "${patterns[@]}"; do
    if printf '%s' "$staged_content" | grep -E -q -- "$pattern"; then
      echo "Secret check failed: staged content in $path matches a blocked secret pattern." >&2
      failed=1
      break
    fi
  done
done

if [ "$failed" -ne 0 ]; then
  cat >&2 <<'EOF'
Commit blocked.

If this file is intentional test data, remove the real secret material first.
If you need to bypass locally, use --no-verify, but rotate any exposed credential.
EOF
  exit 1
fi
