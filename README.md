# VEDA Black Marble OGC

Nighttime lights processing pipeline for NASA VEDA, packaged as a MAAP **OGC Application Package** / **DPS** algorithm.

Upstream science: [NASA-IMPACT/veda-black-marble](https://github.com/NASA-IMPACT/veda-black-marble).  
This repository: [NASA-IMPACT/veda-black-marble-ogc](https://github.com/NASA-IMPACT/veda-black-marble-ogc).

## Installation

Requires Python 3.11+.

```bash
git clone https://github.com/NASA-IMPACT/veda-black-marble-ogc.git
cd veda-black-marble-ogc
pip install -e .
# or with uv
uv pip install -e .
```

## Authentication

The science package (`blackmarble`) only speaks **earthaccess** (`EARTHDATA_TOKEN` or `~/.netrc`). MAAP-specific auth stays in the DPS adapter (`run.sh` + `resolve_earthdata_token.py`), so the same code runs locally and stays publishable to PyPI/conda without `maap-py`.

**Do not pass an Earthdata token as a DPS job or CLI argument** — it appears in job logs in plain text.

| Environment | How auth works |
|-------------|----------------|
| **Local / PyPI** | `export EARTHDATA_TOKEN=...` or `~/.netrc`, then run `blackmarble` |
| **MAAP ADE / DPS** | Store token once as a MAAP secret; `run.sh` loads it via `maap-py` and exports `EARTHDATA_TOKEN` before calling `blackmarble` |

```python
from maap.maap import MAAP
MAAP().secrets.add_secret("EARTHDATA_TOKEN", "<your-earthdata-token>")
```

Authorize needed Earthdata apps on your [URS profile](https://urs.earthdata.nasa.gov/) (e.g. LAADS for VNP46A2).

## Quick Start (local)

```bash
export EARTHDATA_TOKEN="your-token-here"

blackmarble \
  --bbox "-122.55,37.69,-122.32,37.81" \
  --date 2023-06-15 \
  --output-path san_francisco_lights.tif
```

Run `blackmarble --help` for full CLI options.

## MAAP DPS

Packaging files: `run.sh`, `resolve_earthdata_token.py`, `build.sh`, `environment.yml`, `algorithm_config.yml`, `maap_dps_algorithm_config.yml`.

### DPS inputs

| Name | Example | Notes |
|------|---------|--------|
| `bbox` | `-122.55,37.69,-122.32,37.81` | required; lat span ≥ 0.05° |
| `date` | `2023-06-15` | required |
| `config` | `fast` | `default` / `high_quality` / `fast` |
| `osm_source` | `overpass` | or `layercake` |
| `wgs84` | `false` | also write EPSG:4326 |
| `basename` | `san_francisco_lights` | see below |
| `earthdata_secret_name` | `EARTHDATA_TOKEN` | secret **name** only, never the token value |

There is **no** `earthdata_token` (or similar) job input.

### `basename` vs `--output-path`

| | Meaning |
|---|---------|
| `--output-path` / `-o` | Full COG path for the science CLI (e.g. `san_francisco_lights.tif`) |
| `basename` (DPS) | Filename **stem** only |

`run.sh` maps:

```text
basename=san_francisco_lights  →  --output-path output/san_francisco_lights.tif
```

### Example local DPS entrypoint

```bash
# Local ADE: export EARTHDATA_TOKEN, or rely on MAAP Secrets (default name)
./run.sh \
  --bbox "-122.55,37.69,-122.32,37.81" \
  --date 2023-06-15 \
  --config fast \
  --basename san_francisco_lights
```

### Submit a job (ADE)

```python
from maap.maap import MAAP

maap = MAAP()
job = maap.submitJob(
    identifier="black-marble-smoke",
    algo_id="veda-black-marble",
    version="main",
    queue="maap-dps-worker-16gb",
    bbox="-122.55,37.69,-122.32,37.81",
    date="2023-06-15",
    config="fast",
    osm_source="overpass",
    wgs84="false",
    basename="san_francisco_lights",
    earthdata_secret_name="EARTHDATA_TOKEN",
)
print(job)
```

## OSM Sources

Road data can be fetched from either:

- `overpass` (default): Overpass API queries via OSMnx
- `layercake`: OpenStreetMap US [Layercake parquet](https://openstreetmap.us/our-work/layercake/) source

Layercake can be faster over large or dense areas, but is experimental and may not be as fresh.

## Example

```bash
blackmarble \
  --bbox "2.08,48.80,2.42,48.92" \
  --date 2023-08-01 \
  --config high_quality \
  --wgs84 \
  --output-path paris_lights_hq.tif
```

## Documentation

For detailed algorithm documentation (QA masking, temporal compositing, urban field enhancement), see [`docs/pipeline-steps/`](docs/pipeline-steps/). Start with [`README.md`](docs/pipeline-steps/README.md).

## Python API

```python
from blackmarble.pipeline import pipeline
from datetime import datetime

result = pipeline(
    bbox=(-122.55, 37.69, -122.32, 37.81),  # (min_lon, min_lat, max_lon, max_lat)
    date=datetime(2023, 6, 15),
    output_path="san_francisco.tif",
)
```

## Module Organization

```
blackmarble/
├── acquire/          # Downloads: Landsat, VIIRS, OSM roads
│   ├── landsat.py
│   ├── viirs.py      # VNP46A2 via earthaccess (token from env / run.sh)
│   └── osm.py
├── prepare/          # QA and spatial prep
├── analyze/          # Indices, temporal composite, urban fields
├── enhance/          # Contrast / visualization
└── export/           # COG + metadata
```

## Output

- Cloud-Optimized GeoTIFF with embedded metadata
- RGB visualization (inferno colormap)
- Optional EPSG:4326 export (`--wgs84` / DPS `wgs84=true`)
- Optional diagnostics (`--save-diagnostics`)

## Requirements

- Python 3.11+
- NASA Earthdata account (free) for VIIRS (`EARTHDATA_TOKEN` or `~/.netrc`)
- ~8GB RAM for typical ~100×100 km regions
- On MAAP DPS only: `maap-py` in `environment.yml` (secrets → `EARTHDATA_TOKEN`; not a package dependency)

## License

[Apache License 2.0](LICENSE) — National Aeronautics and Space Administration (NASA)

Originally created by NASA Goddard Earth Sciences

## Contributing

Issues and pull requests welcome.
- OGC packaging: https://github.com/NASA-IMPACT/veda-black-marble-ogc/issues
- Upstream science: https://github.com/NASA-IMPACT/veda-black-marble/issues
