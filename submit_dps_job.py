#!/usr/bin/env python3
"""Submit a single Black Marble DPS job on MAAP.

Auth: store the Earthdata token as a MAAP secret; pass only the secret name.
Do not pass Earthdata tokens as job inputs.

  from maap.maap import MAAP
  MAAP().secrets.add_secret("EARTHDATA_TOKEN", "<your-token>")

  python submit_dps_job.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path


ALGO_ID = os.environ.get("BM_ALGO_ID", "veda-black-marble")
ALGO_VERSION = os.environ.get("BM_ALGO_VERSION", "main")
QUEUE = os.environ.get("BM_QUEUE", "maap-dps-worker-16gb")
IDENTIFIER = os.environ.get("BM_JOB_TAG", "black-marble-smoke")

PARAMS = {
    "bbox": os.environ.get("BM_BBOX", "-122.55,37.69,-122.32,37.81"),
    "date": os.environ.get("BM_DATE", "2023-06-15"),
    "config": os.environ.get("BM_CONFIG", "fast"),
    "osm_source": os.environ.get("BM_OSM_SOURCE", "overpass"),
    "wgs84": os.environ.get("BM_WGS84", "false"),
    "basename": os.environ.get("BM_BASENAME", "san_francisco_lights"),
    "earthdata_secret_name": os.environ.get("BM_EARTHDATA_SECRET_NAME", "EARTHDATA_TOKEN"),
}


def main() -> None:
    try:
        from maap.maap import MAAP
    except ImportError as exc:
        raise SystemExit("Install maap-py (available on MAAP ADE).") from exc

    api_url = os.environ.get("MAAP_API_URL")
    maap = MAAP(maap_host=api_url) if api_url else MAAP()

    secret_name = PARAMS["earthdata_secret_name"]
    secret_check = maap.secrets.get_secret(secret_name)
    if isinstance(secret_check, dict) and secret_check.get("code") == 404:
        raise SystemExit(
            f"MAAP secret '{secret_name}' not found. Create it first:\n"
            f"  MAAP().secrets.add_secret('{secret_name}', '<your-earthdata-token>')"
        )

    print(f"Submitting {ALGO_ID}:{ALGO_VERSION} on {QUEUE}")
    print(f"  params={PARAMS}")

    result = maap.submitJob(
        identifier=IDENTIFIER,
        algo_id=ALGO_ID,
        version=ALGO_VERSION,
        queue=QUEUE,
        **PARAMS,
    )

    job_id = getattr(result, "id", None) or getattr(result, "job_id", None) or result
    print(f"Submitted job: {job_id}")
    print(result)

    if os.environ.get("BM_WAIT", "0") == "1" and hasattr(maap, "getJobStatus"):
        for _ in range(60):
            status = maap.getJobStatus(job_id)
            print(f"status={status}")
            if str(status).lower() in {"succeeded", "failed", "deleted"}:
                break
            time.sleep(30)

    out = Path("dps_submit_result.txt")
    out.write_text(str(result))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
