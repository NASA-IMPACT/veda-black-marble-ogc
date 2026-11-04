#!/usr/bin/env python3
"""Register veda-black-marble with the MAAP DPS API.

Run this inside a MAAP ADE notebook / terminal after pushing the packaging
repo to a public GitHub URL referenced in maap_dps_algorithm_config.yml.

  python register_algorithm.py
"""

from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    try:
        from maap.maap import MAAP
    except ImportError as exc:
        raise SystemExit("Install maap-py before registering DPS algorithms.") from exc

    api_url = os.environ.get("MAAP_API_URL")
    maap = MAAP(maap_host=api_url) if api_url else MAAP()

    # Prefer the Register-Algorithm-UI style YAML used by maap-py.
    config_path = Path(__file__).with_name("maap_dps_algorithm_config.yml")
    if not config_path.exists():
        config_path = Path(__file__).with_name("algorithm_config.yml")

    print(f"Registering {config_path} with MAAP DPS")
    result = maap.register_algorithm_from_yaml_file(str(config_path))
    print(result)


if __name__ == "__main__":
    main()
