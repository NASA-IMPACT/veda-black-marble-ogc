#!/usr/bin/env python3
"""Optionally resolve EARTHDATA_TOKEN for DPS without putting the secret on the CLI.

Priority:
  1) Existing EARTHDATA_TOKEN environment variable (local / already injected)
  2) MAAP Secrets Manager via maap-py (optional soft path)

Exit codes:
  0 — token written to stdout (caller should export EARTHDATA_TOKEN)
  2 — soft miss: no env token and no usable secret; caller may continue and
      rely on maap-py + MAAP_PGT (or ~/.netrc) inside blackmarble
  1 — hard failure (unexpected secret API response, etc.)

Never log the token value.

Create an optional secret in ADE:
  from maap.maap import MAAP
  MAAP().secrets.add_secret("EARTHDATA_TOKEN", "<your-token>")

Optional: set EARTHDATA_SECRET_NAME if you stored the token under another name.
"""

from __future__ import annotations

import os
import sys


def _emit_token(token: str) -> int:
    token = token.strip()
    if not token:
        print("ERROR: Earthdata token is empty", file=sys.stderr)
        return 1
    # Token only on stdout — do not print elsewhere.
    sys.stdout.write(token)
    return 0


def main() -> int:
    secret_name = (os.environ.get("EARTHDATA_SECRET_NAME") or "EARTHDATA_TOKEN").strip()
    if not secret_name:
        secret_name = "EARTHDATA_TOKEN"

    existing = (os.environ.get("EARTHDATA_TOKEN") or "").strip()
    if existing:
        print("Using EARTHDATA_TOKEN from environment (secret name unused)", file=sys.stderr)
        return _emit_token(existing)

    try:
        from maap.maap import MAAP
    except ImportError:
        print(
            "No EARTHDATA_TOKEN in env and maap-py is not installed; "
            "continuing without exporting a token (earthaccess/netrc or "
            "maap-py+MAAP_PGT may still work depending on the runtime).",
            file=sys.stderr,
        )
        return 2

    try:
        maap = MAAP()
        value = maap.secrets.get_secret(secret_name)
    except Exception as exc:  # noqa: BLE001 — soft miss; DPS may still use MAAP_PGT
        print(
            f"Could not read MAAP secret '{secret_name}' ({exc}); "
            "continuing without EARTHDATA_TOKEN "
            "(maap-py + MAAP_PGT may still authenticate downloads).",
            file=sys.stderr,
        )
        return 2

    if isinstance(value, dict) and value.get("code") == 404:
        print(
            f"MAAP secret '{secret_name}' not found; continuing without "
            "EARTHDATA_TOKEN (maap-py + MAAP_PGT may still authenticate). "
            "Optional: MAAP().secrets.add_secret("
            f"'{secret_name}', '<your-earthdata-token>').",
            file=sys.stderr,
        )
        return 2

    if isinstance(value, dict) and ("message" in value or "code" in value):
        print(
            f"ERROR: unexpected response reading MAAP secret '{secret_name}': "
            f"code={value.get('code')} message={value.get('message')}",
            file=sys.stderr,
        )
        return 1

    print(f"Loaded Earthdata token from MAAP secret '{secret_name}'", file=sys.stderr)
    return _emit_token(str(value))


if __name__ == "__main__":
    raise SystemExit(main())
