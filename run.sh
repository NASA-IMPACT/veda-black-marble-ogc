#!/usr/bin/env bash
set -euo pipefail

# OGC / DPS entrypoint for NASA-IMPACT/veda-black-marble-ogc.
# Persistable products must land under ./output (DPS convention).
#
# Credential setup (packaging layer):
#   run.sh may export EARTHDATA_TOKEN from env or optional MAAP Secrets.
#   blackmarble tries maap-py + MAAP_PGT first, then earthaccess/env.
# Never pass the token as a DPS job / CLI argument (it appears in job logs).
#
# Named flags (OGC app pack / local):
#   ./run.sh --bbox "-122.55,37.69,-122.32,37.81" --date 2023-06-15
#
# Positional (MAAP Register Algorithm UI / DPS):
#   ./run.sh <bbox> <date> [config] [osm_source] [wgs84] [basename] [earthdata_secret_name]

basedir=$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" && pwd)

mkdir -p output

BBOX=""
DATE=""
CONFIG="fast"
OSM_SOURCE="overpass"
WGS84="false"
BASENAME="black_marble_output"
LOG_LEVEL="INFO"
EARTHDATA_SECRET_NAME="${EARTHDATA_SECRET_NAME:-EARTHDATA_TOKEN}"

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

usage() {
  cat <<EOF
Usage:
  $(basename "$0") --bbox MINX,MINY,MAXX,MAXY --date YYYY-MM-DD [options...]
  $(basename "$0") <bbox> <date> [config] [osm_source] [wgs84] [basename] [earthdata_secret_name]

Options:
  --bbox BBOX                    WGS84 bbox: min_lon,min_lat,max_lon,max_lat
  --date YYYY-MM-DD              Target date
  --config PRESET                default | high_quality | fast  [default: fast]
  --osm_source SRC               overpass | layercake           [default: overpass]
  --wgs84 true|false             Also export EPSG:4326          [default: false]
  --basename NAME                Output filename stem → output/NAME.tif
  --log_level LEVEL              DEBUG|INFO|WARNING|ERROR       [default: INFO]
  --earthdata_secret_name NAME   MAAP secret name holding the Earthdata token
                                 [default: EARTHDATA_TOKEN]
                                 Never pass the token value itself on the CLI.
EOF
}

if [[ $# -gt 0 && "${1}" != --* ]]; then
  BBOX="${1:-$BBOX}"
  DATE="${2:-$DATE}"
  CONFIG="${3:-$CONFIG}"
  OSM_SOURCE="${4:-$OSM_SOURCE}"
  WGS84="${5:-$WGS84}"
  BASENAME="${6:-$BASENAME}"
  EARTHDATA_SECRET_NAME="${7:-$EARTHDATA_SECRET_NAME}"
else
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --bbox) BBOX="$2"; shift 2 ;;
      --date) DATE="$2"; shift 2 ;;
      --config) CONFIG="$2"; shift 2 ;;
      --osm_source) OSM_SOURCE="$2"; shift 2 ;;
      --wgs84) WGS84="$2"; shift 2 ;;
      --basename) BASENAME="$2"; shift 2 ;;
      --log_level) LOG_LEVEL="$2"; shift 2 ;;
      --earthdata_secret_name) EARTHDATA_SECRET_NAME="$2"; shift 2 ;;
      --earthdata_token)
        echo "ERROR: --earthdata_token is not accepted (token would appear in DPS logs)." >&2
        echo "Store the token as a MAAP secret and pass --earthdata_secret_name if needed." >&2
        echo "  MAAP().secrets.add_secret('EARTHDATA_TOKEN', '<token>')" >&2
        exit 2
        ;;
      -h|--help) usage; exit 0 ;;
      *)
        echo "Unknown argument: $1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done
fi

BBOX="$(trim "$BBOX")"
DATE="$(trim "$DATE")"
CONFIG="$(trim "$CONFIG")"
OSM_SOURCE="$(trim "$OSM_SOURCE")"
WGS84="$(trim "$WGS84")"
BASENAME="$(trim "$BASENAME")"
EARTHDATA_SECRET_NAME="$(trim "$EARTHDATA_SECRET_NAME")"
LOG_LEVEL="$(trim "$LOG_LEVEL")"

if [[ -z "${BBOX}" || -z "${DATE}" ]]; then
  echo "ERROR: --bbox and --date are required" >&2
  usage >&2
  exit 1
fi

OUTPUT_PATH="output/${BASENAME}.tif"
DATA_DIR="output/data"
mkdir -p "${DATA_DIR}"

ARGS=(
  --bbox "${BBOX}"
  --date "${DATE}"
  --config "${CONFIG}"
  --osm-source "${OSM_SOURCE}"
  --output-path "${OUTPUT_PATH}"
  --data-dir "${DATA_DIR}"
  --log-level "${LOG_LEVEL}"
)

case "${WGS84}" in
  true|TRUE|1|yes|YES)
    ARGS+=(--wgs84)
    ;;
esac

CONDA_ENV_NAME="${CONDA_ENV_NAME:-notebook}"

if ! command -v conda >/dev/null 2>&1; then
  for candidate in \
    "${CONDA_EXE:-}" \
    /opt/conda/etc/profile.d/conda.sh \
    /opt/conda/bin/conda \
    /usr/local/etc/profile.d/conda.sh \
    "${HOME}/.conda/etc/profile.d/conda.sh" \
    /srv/conda/etc/profile.d/conda.sh \
    /srv/conda/bin/conda
  do
    [[ -z "${candidate}" ]] && continue
    if [[ -f "${candidate}" && "${candidate}" == *.sh ]]; then
      # shellcheck disable=SC1090
      source "${candidate}"
      break
    elif [[ -x "${candidate}" ]]; then
      export PATH="$(dirname "${candidate}"):${PATH}"
      break
    fi
  done
fi

if ! command -v conda >/dev/null 2>&1; then
  echo "ERROR: conda not found in PATH. Checked common MAAP locations." >&2
  echo "PATH=${PATH}" >&2
  exit 127
fi

# Soft credential setup (packaging layer):
#   prefer existing EARTHDATA_TOKEN, else optional MAAP Secrets.
# Do not hard-fail if missing — blackmarble may use maap-py + MAAP_PGT.
export EARTHDATA_SECRET_NAME
PY_BIN="$(conda run --name "${CONDA_ENV_NAME}" python -c 'import sys; print(sys.executable)')"
TOKEN_FILE="$(mktemp)"
chmod 600 "${TOKEN_FILE}"
cleanup_token_file() { rm -f "${TOKEN_FILE}"; }
trap cleanup_token_file EXIT

set +e
"${PY_BIN}" "${basedir}/resolve_earthdata_token.py" >"${TOKEN_FILE}"
resolve_rc=$?
set -e

case "${resolve_rc}" in
  0)
    EARTHDATA_TOKEN="$(cat "${TOKEN_FILE}")"
    export EARTHDATA_TOKEN
    if [[ -z "${EARTHDATA_TOKEN}" ]]; then
      echo "ERROR: resolve_earthdata_token.py returned success but token is empty." >&2
      exit 1
    fi
    echo "Exported EARTHDATA_TOKEN for earthaccess fallback"
    ;;
  2)
    echo "No EARTHDATA_TOKEN from env/secrets; continuing."
    echo "  blackmarble will try maap-py + MAAP_PGT, then earthaccess/netrc."
    if [[ -n "${MAAP_PGT:-}" ]]; then
      echo "  MAAP_PGT is present in the environment."
    else
      echo "  MAAP_PGT is not set; ensure EARTHDATA_TOKEN or ~/.netrc if not on MAAP."
    fi
    ;;
  *)
    echo "ERROR: resolve_earthdata_token.py failed (exit ${resolve_rc})." >&2
    exit 1
    ;;
esac
rm -f "${TOKEN_FILE}"
trap - EXIT

echo "Running Black Marble pipeline"
echo "  bbox=${BBOX}"
echo "  date=${DATE}"
echo "  config=${CONFIG}"
echo "  osm_source=${OSM_SOURCE}"
echo "  output=${OUTPUT_PATH}"
echo "  earthdata_secret_name=${EARTHDATA_SECRET_NAME}"
echo "  conda=$(command -v conda) env=${CONDA_ENV_NAME}"

conda run --live-stream --name "${CONDA_ENV_NAME}" \
  blackmarble "${ARGS[@]}"

echo "Done. Products in ./output"
ls -la output || true
