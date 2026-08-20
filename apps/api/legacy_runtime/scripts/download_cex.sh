#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEST_DIR="${PROJECT_ROOT}/data/raw/cex"

mkdir -p "${DEST_DIR}"

# Official source-of-truth page for these files:
# https://www.bls.gov/cex/pumd_data.htm
#
# URLs below are aligned to the official BLS CEX PUMD CSV page for 2024.
# Keep env-var overrides so we can switch quickly if BLS updates paths.
CEX_YEAR="${CEX_YEAR:-2024}"
CEX_INTERVIEW_URL_DEFAULT="https://www.bls.gov/cex/pumd/data/comma/intrvw24.zip"
CEX_DIARY_URL_DEFAULT="https://www.bls.gov/cex/pumd/data/comma/diary24.zip"

CEX_INTERVIEW_URL="${CEX_INTERVIEW_URL:-${CEX_INTERVIEW_URL_DEFAULT}}"
CEX_DIARY_URL="${CEX_DIARY_URL:-${CEX_DIARY_URL_DEFAULT}}"

# Normalized output names used by downstream project scripts.
INTERVIEW_FILE="cex_interview_${CEX_YEAR}.zip"
DIARY_FILE="cex_diary_${CEX_YEAR}.zip"

INTERVIEW_DEST="${DEST_DIR}/${INTERVIEW_FILE}"
DIARY_DEST="${DEST_DIR}/${DIARY_FILE}"

# Optional local-file fallback inputs.
CEX_INTERVIEW_LOCAL="${CEX_INTERVIEW_LOCAL:-}"
CEX_DIARY_LOCAL="${CEX_DIARY_LOCAL:-}"

download_file() {
	local url="$1"
	local dest="$2"

	if [[ -f "${dest}" ]]; then
		echo "Skipping existing file: ${dest}"
		return 0
	fi

	echo "Downloading: ${url}"
	if ! curl \
		--fail \
		--location \
		--retry 3 \
		--retry-delay 2 \
		--connect-timeout 20 \
		--max-time 600 \
		--user-agent "Mozilla/5.0" \
		--referer "https://www.bls.gov/cex/pumd_data.htm" \
		--output "${dest}" \
		"${url}"; then
		echo "Failed to download: ${url}"
		echo "Tip: BLS may block scripted downloads (HTTP 403)."
		return 1
	fi

	return 0
}

copy_local_file_if_set() {
	local source_path="$1"
	local dest_path="$2"
	local label="$3"

	if [[ -z "${source_path}" ]]; then
		return 0
	fi

	if [[ ! -f "${source_path}" ]]; then
		echo "Local ${label} file not found: ${source_path}"
		return 1
	fi

	echo "Copying local ${label} file: ${source_path} -> ${dest_path}"
	cp -f "${source_path}" "${dest_path}"
	return 0
}

print_manual_fallback_instructions() {
	echo ""
	echo "Manual fallback required."
	echo "Download official 2024 CSV Interview and Diary ZIP files from:"
	echo "  https://www.bls.gov/cex/pumd_data.htm"
	echo ""
	echo "Then either:"
	echo "  A) Place them directly at:"
	echo "     ${INTERVIEW_DEST}"
	echo "     ${DIARY_DEST}"
	echo "  B) Or rerun script with local source paths:"
	echo "     CEX_INTERVIEW_LOCAL=/path/to/interview.zip CEX_DIARY_LOCAL=/path/to/diary.zip bash scripts/download_cex.sh"
	echo ""
}

verify_expected_files() {
	local missing=0

	if [[ ! -f "${INTERVIEW_DEST}" ]]; then
		echo "Missing expected file: ${INTERVIEW_DEST}"
		missing=1
	fi

	if [[ ! -f "${DIARY_DEST}" ]]; then
		echo "Missing expected file: ${DIARY_DEST}"
		missing=1
	fi

	if [[ ${missing} -ne 0 ]]; then
		return 1
	fi

	echo "Verification passed. Found required CEX ZIP files:"
	ls -lh "${INTERVIEW_DEST}" "${DIARY_DEST}"
	return 0
}

# Mode B (manual-local shortcut): copy local files first when provided.
copy_local_file_if_set "${CEX_INTERVIEW_LOCAL}" "${INTERVIEW_DEST}" "interview"
copy_local_file_if_set "${CEX_DIARY_LOCAL}" "${DIARY_DEST}" "diary"

# Mode A (normal download): attempt network fetch for any missing file.
download_failed=0
fallback_notice_printed=0
if [[ ! -f "${INTERVIEW_DEST}" ]]; then
	if ! download_file "${CEX_INTERVIEW_URL}" "${INTERVIEW_DEST}"; then
		download_failed=1
	fi
fi

if [[ ! -f "${DIARY_DEST}" ]]; then
	if ! download_file "${CEX_DIARY_URL}" "${DIARY_DEST}"; then
		download_failed=1
	fi
fi

# Mode B (manual fallback): if download failed, guide user and then verify.
if [[ ${download_failed} -ne 0 ]]; then
	print_manual_fallback_instructions
	fallback_notice_printed=1
fi

if verify_expected_files; then
	echo "CEX setup complete."
	echo "Saved files in: ${DEST_DIR}"
	exit 0
fi

if [[ ${fallback_notice_printed} -eq 0 ]]; then
	print_manual_fallback_instructions
fi
exit 1
