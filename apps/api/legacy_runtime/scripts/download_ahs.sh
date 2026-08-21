#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEST_DIR="${PROJECT_ROOT}/data/raw/ahs"

mkdir -p "${DEST_DIR}"

AHS_FILE="AHS 2023 National PUF v1.1 Flat CSV.zip"
AHS_URL_DEFAULT="https://www2.census.gov/programs-surveys/ahs/2023/AHS%202023%20National%20PUF%20v1.1%20Flat%20CSV.zip"
AHS_URL="${AHS_URL:-${AHS_URL_DEFAULT}}"

download_file() {
	local url="$1"
	local dest="$2"

	if [[ -f "${dest}" ]]; then
		echo "Skipping existing file: ${dest}"
		return 0
	fi

	echo "Downloading: ${url}"
	curl --fail --location --retry 3 --retry-delay 2 --output "${dest}" "${url}"
}

download_file "${AHS_URL}" "${DEST_DIR}/${AHS_FILE}"

echo "AHS download complete."
echo "Saved file in: ${DEST_DIR}"
