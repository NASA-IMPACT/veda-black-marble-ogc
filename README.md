# veda-black-marble-ogc

Thin **OGC Application Package / MAAP DPS** layer around
[NASA-IMPACT/veda-black-marble](https://github.com/NASA-IMPACT/veda-black-marble).

This repo does **not** vendor science code. At build/run time it:

1. Resolves `EARTHDATA_TOKEN` from **MAAP Secrets** or a local env var  
2. Shallow-clones / `uv sync`s `https://github.com/NASA-IMPACT/veda-black-marble`  
3. Runs `uv run blackmarble …` and writes products under `output/`

## Layout

| File | Role |
|------|------|
| `build.sh` | Install `uv` + `maap-py`; shallow-clone upstream; `uv sync` |
| `run.sh` | Secrets → `uv run blackmarble` → `output/` |
| `resolve_earthdata_token.py` | Load token from env or MAAP Secrets (never CLI) |
| `environment.yml` | Minimal packaging deps only |
| `algorithm_config.yml` / `maap_dps_algorithm_config.yml` | Register metadata |
| `workflows/*.cwl` | OGC Application Package |
| `Dockerfile` | OGC container image |

## Earthdata auth (no CLI token)

```python
from maap.maap import MAAP
MAAP().secrets.add_secret("EARTHDATA_TOKEN", "<your-token>")
```

Local ADE testing can instead `export EARTHDATA_TOKEN=...`.

Optional job input `earthdata_secret_name` is only the **secret name** (default `EARTHDATA_TOKEN`), never the value.

## `basename` vs `--output-path`

DPS input `basename` → `output/<basename>.tif`, passed to upstream as
`--output-path output/<basename>.tif`.

## Local smoke test

```bash
export EARTHDATA_TOKEN="your-token"
chmod +x build.sh run.sh
./build.sh
./run.sh --bbox "-122.55,37.69,-122.32,37.81" --date 2023-06-15 --config fast --basename sf_smoke
ls output/
```

Latitude span must be **≥ 0.05°**.

## Register / submit (MAAP ADE)

```python
from maap.maap import MAAP
maap = MAAP()
maap.register_algorithm_from_yaml_file("maap_dps_algorithm_config.yml")

job = maap.submitJob(
    identifier="black-marble-smoke",
    algo_id="veda-black-marble",
    version="main",
    queue="maap-dps-worker-16gb",
    bbox="-122.55,37.69,-122.32,37.81",
    date="2023-06-15",
    config="fast",
    basename="san_francisco_lights",
    earthdata_secret_name="EARTHDATA_TOKEN",
)
print(job)
```

Use `maap-dps-worker-16gb` (not sandbox) for real runs.
