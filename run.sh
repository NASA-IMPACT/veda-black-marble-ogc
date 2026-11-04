#!/usr/bin/env bash
set -euo pipefail

# Thin OGC/DPS entrypoint for VEDA Black Marble.
# 1) Resolve EARTHDATA_TOKEN (MAAP Secrets or local env) — never as a CLI arg
# 2) Call upstream via: uv run blackmarble ...
# Persistable products must land under ./output (DPS convention).

basedir=$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" && pwd)
VENDOR_DIR="${basedir}/vendor/veda-black-marble"

# Ensure uv on PATH (build.sh installs to ~/.local/bin)
export PATH="${HOME}/.local/bin:${PATH}"

mkdir -p output

BBOX="-122.55,37.69,-122.32,37.81"
DATE="2023-06-15"
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
  --bbox BBOX
  --date YYYY-MM-DD
  --config PRESET                default | high_quality | fast
  --osm_source SRC               overpass | layercake
  --wgs84 true|false
  --basename NAME                → output/NAME.tif (maps to --output-path)
  --earthdata_secret_name NAME   MAAP secret name (not the token value)
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
        echo "ERROR: do not pass the token on the CLI (leaks into DPS logs)." >&2
        echo "Use MAAP Secrets: MAAP().secrets.add_secret('EARTHDATA_TOKEN', '<token>')" >&2
        exit 2
        ;;
      -h|--help) usage; exit 0 ;;
      *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
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
  exit 1
fi

if [[ ! -d "${VENDOR_DIR}" ]]; then
  echo "ERROR: upstream checkout missing at ${VENDOR_DIR}. Run build.sh first." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv not found. Run build.sh first." >&2
  exit 127
fi

# 1) EARTHDATA_TOKEN from env or MAAP Secrets
export EARTHDATA_SECRET_NAME
TOKEN_FILE="$(mktemp)"
chmod 600 "${TOKEN_FILE}"
cleanup() { rm -f "${TOKEN_FILE}"; }
trap cleanup EXIT

if ! python3 "${basedir}/resolve_earthdata_token.py" >"${TOKEN_FILE}"; then
  echo "ERROR: could not resolve EARTHDATA_TOKEN from env or MAAP Secrets." >&2
  exit 1
fi
EARTHDATA_TOKEN="$(cat "${TOKEN_FILE}")"
export EARTHDATA_TOKEN
rm -f "${TOKEN_FILE}"
trap - EXIT

if [[ -z "${EARTHDATA_TOKEN}" ]]; then
  echo "ERROR: resolved EARTHDATA_TOKEN is empty." >&2
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
case "${WGS84}" in true|TRUE|1|yes|YES) ARGS+=(--wgs84) ;; esac

echo "Running Black Marble (uv run)"
echo "  upstream=${VENDOR_DIR}"
echo "  bbox=${BBOX} date=${DATE} config=${CONFIG}"
echo "  output=${OUTPUT_PATH}"
echo "  earthdata_secret_name=${EARTHDATA_SECRET_NAME}"

# 2) Call upstream science CLI
(
  cd "${VENDOR_DIR}"
  uv run blackmarble "${ARGS[@]}"
)

echo "Done."
ls -la output || true
