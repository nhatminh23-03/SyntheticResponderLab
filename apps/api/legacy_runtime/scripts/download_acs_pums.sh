#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEST_DIR="${PROJECT_ROOT}/data/raw/acs_pums"

mkdir -p "${DEST_DIR}"

ACS_BASE_URL="https://www2.census.gov/programs-surveys/acs/data/pums/2024/5-Year"
ACS_PERSON_FILE="csv_pca.zip"
ACS_HOUSING_FILE="csv_hca.zip"

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

download_file "${ACS_BASE_URL}/${ACS_PERSON_FILE}" "${DEST_DIR}/${ACS_PERSON_FILE}"
download_file "${ACS_BASE_URL}/${ACS_HOUSING_FILE}" "${DEST_DIR}/${ACS_HOUSING_FILE}"

echo "ACS PUMS download complete."
echo "Saved files in: ${DEST_DIR}"
