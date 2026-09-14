#!/usr/bin/env bash
set -euo pipefail

basedir=$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" && pwd)
CONDA_ENV_NAME="${CONDA_ENV_NAME:-notebook}"
conda=${CONDA_EXE:-conda}

if ! command -v conda >/dev/null 2>&1; then
  for candidate in /opt/conda/etc/profile.d/conda.sh /srv/conda/etc/profile.d/conda.sh; do
    [[ -f "$candidate" ]] && source "$candidate" && break
  done
fi

ENV_FILE="${basedir}/environment.yml"
echo "Updating conda env '${CONDA_ENV_NAME}' from environment.yml"
PIP_REQUIRE_VENV=0 "${conda}" env update --quiet --file "${ENV_FILE}" --name "${CONDA_ENV_NAME}"

echo "Installing blackmarble"
PIP_REQUIRE_VENV=0 "${conda}" run --name "${CONDA_ENV_NAME}" \
  python -m pip install --no-cache-dir -e "${basedir}"

"${conda}" run --name "${CONDA_ENV_NAME}" blackmarble --help >/dev/null
echo "Verifying maap-py import (for MAAP secrets in run.sh)"
"${conda}" run --name "${CONDA_ENV_NAME}" python -c "from maap.maap import MAAP; print('maap-py OK')"
chmod +x "${basedir}/run.sh" "${basedir}/build.sh" "${basedir}/resolve_earthdata_token.py" 2>/dev/null || true
echo "Build complete"
