"""OGC/DPS override of upstream VIIRS download.

Keeps upstream product model (VJ146A2 / VNP46A2), but prefers maap-py +
MAAP_PGT on ADE/DPS so jobs do not depend on earthaccess → Launchpad/EDL.
Falls back to earthaccess (EARTHDATA_TOKEN / netrc) outside MAAP.

Applied by build.sh after the upstream shallow clone.
"""

from __future__ import annotations

import inspect
import logging
import os
import urllib.parse
import warnings
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import rasterio
from rasterio.errors import NotGeoreferencedWarning


logger = logging.getLogger(__name__)

ViirsProductName = Literal["VJ146A2", "VNP46A2"]


@dataclass(frozen=True)
class ViirsProduct:
    short_name: str
    version: str
    platform: str
    start_date: datetime
    end_date: datetime | None = None

    @property
    def sensor(self) -> str:
        return f"VIIRS ({self.platform})"


VIIRS_PRODUCTS: dict[str, ViirsProduct] = {
    "VJ146A2": ViirsProduct(
        short_name="VJ146A2",
        version="2",
        platform="NOAA-20",
        start_date=datetime(2018, 1, 19),
    ),
    "VNP46A2": ViirsProduct(
        short_name="VNP46A2",
        version="2",
        platform="Suomi NPP",
        start_date=datetime(2012, 1, 19),
        end_date=datetime(2026, 11, 1),
    ),
}

DEFAULT_VIIRS_PRODUCT: ViirsProductName = "VJ146A2"
BM_SHORT_NAME = VIIRS_PRODUCTS[DEFAULT_VIIRS_PRODUCT].short_name
BM_VERSION = VIIRS_PRODUCTS[DEFAULT_VIIRS_PRODUCT].version
BM_VERSION_CMR = "002"
CMR_GRANULES_UMM = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
NTL_DATASET_PATH = (
    "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data_Fields/Gap_Filled_DNB_BRDF-Corrected_NTL"
)


def convert_to_tiff(
    input_h5: str | Path, output_path: str | Path, dataset_path: str = NTL_DATASET_PATH
) -> Path:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        subdatasets = rasterio.open(input_h5).subdatasets
    dnb_sds = [sds for sds in subdatasets if dataset_path in sds][0]

    with rasterio.open(dnb_sds, "r") as src:
        profile = src.profile
        data = src.read(1)

    dst_profile = deepcopy(profile)
    dst_profile.update(
        driver="GTiff", predictor=3, compress="deflate", blockxsize=256, blockysize=256
    )
    with rasterio.open(output_path, mode="w", **dst_profile) as dst:
        dst.write(data, 1)
    return Path(output_path)


def get_viirs_product(name: str) -> ViirsProduct:
    try:
        return VIIRS_PRODUCTS[name.strip().upper()]
    except KeyError:
        supported = ", ".join(VIIRS_PRODUCTS)
        raise ValueError(f"Unsupported VIIRS product {name!r}. Use one of: {supported}") from None


def validate_viirs_date(dt: datetime, product: ViirsProduct) -> None:
    if dt.date() < product.start_date.date():
        raise ValueError(
            f"{product.short_name} ({product.platform}) has no data before "
            f"{product.start_date:%Y-%m-%d}; requested {dt:%Y-%m-%d}."
        )
    if product.end_date is not None and dt.date() >= product.end_date.date():
        logger.warning(
            "%s (%s) product delivery ceased on %s; %s may have no data. Consider %s instead.",
            product.short_name,
            product.platform,
            f"{product.end_date:%Y-%m-%d}",
            f"{dt:%Y-%m-%d}",
            DEFAULT_VIIRS_PRODUCT,
        )


def _bbox_str(bbox: tuple[float, float, float, float]) -> str:
    return ",".join(str(v) for v in bbox)


def _temporal_str(dt: datetime) -> str:
    return f"{dt:%Y-%m-%d}T00:00:00Z,{dt:%Y-%m-%d}T23:59:59Z"


def _filter_kwargs(fn: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return kwargs
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return kwargs
    allowed = set(sig.parameters)
    allowed.discard("self")
    return {k: v for k, v in kwargs.items() if k in allowed}


def _call_search_granule(maap: Any, **kwargs: Any) -> list[Any]:
    fn = maap.searchGranule
    filtered = _filter_kwargs(fn, kwargs)
    dropped = sorted(set(kwargs) - set(filtered))
    if dropped:
        logger.warning("maap.searchGranule ignoring unsupported kwargs: %s", dropped)
    return fn(**filtered)


def _resolve_path(result: Any, output_dir: Path) -> Path:
    path = Path(str(result))
    if not path.is_absolute():
        path = output_dir / path
    if not path.exists():
        alt = output_dir / Path(str(result)).name
        if alt.exists():
            return alt
    return path


def _granule_get_data(granule: Any, output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        sig = inspect.signature(granule.getData)
        if "destpath" in sig.parameters:
            return _resolve_path(granule.getData(destpath=str(output_dir)), output_dir)
    except (TypeError, ValueError):
        pass

    prev = Path.cwd()
    try:
        os.chdir(output_dir)
        return _resolve_path(granule.getData(), output_dir)
    finally:
        os.chdir(prev)


def _http_download_via_result(maap: Any, url: str, dest: Path) -> Path:
    from maap.Result import Result

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    proxy = Result({})
    proxy._dps = maap._DPS
    proxy._cmrFileUrl = getattr(getattr(maap, "config", None), "search_granule_url", "") or ""
    proxy._apiHeader = maap._get_api_header()
    return Path(proxy._getHttpData(url, True, str(dest)))


def _https_url_from_umm_item(item: dict[str, Any]) -> str | None:
    related = (item.get("umm") or {}).get("RelatedUrls") or []
    https_candidates: list[str] = []
    for entry in related:
        if not isinstance(entry, dict):
            continue
        url = entry.get("URL")
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        utype = str(entry.get("Type", "")).upper()
        if "GET DATA" in utype:
            return url
        https_candidates.append(url)
    return https_candidates[0] if https_candidates else None


def _versions_for(product: ViirsProduct) -> tuple[str, ...]:
    # CMR often wants 002; earthaccess uses 2
    return tuple(dict.fromkeys((BM_VERSION_CMR, product.version, "2")))


def _download_via_maap_search(
    maap: Any,
    dt: datetime,
    bbox: tuple[float, float, float, float],
    output_dir: Path,
    product: ViirsProduct,
) -> list[Path]:
    temporal = _temporal_str(dt)
    bbox_csv = _bbox_str(bbox)
    results: list[Any] = []
    for version in _versions_for(product):
        logger.info(
            "maap.searchGranule short_name=%s version=%s", product.short_name, version
        )
        results = _call_search_granule(
            maap,
            short_name=product.short_name,
            version=version,
            temporal=temporal,
            bounding_box=bbox_csv,
            limit=100,
            cmr_host="cmr.earthdata.nasa.gov",
        )
        if results:
            break

    if not results:
        raise RuntimeError(
            f"No {product.short_name} granules from maap.searchGranule "
            f"for date={dt:%Y-%m-%d} bbox={bbox_csv}"
        )

    logger.info("Downloading %d granule(s) via getData()...", len(results))
    filelist: list[Path] = []
    for granule in results:
        path = _granule_get_data(granule, output_dir)
        if path.exists():
            filelist.append(path)

    if not filelist:
        raise RuntimeError("searchGranule ok but no files downloaded via getData")
    return filelist


def _download_via_cmr_umm(
    maap: Any,
    dt: datetime,
    bbox: tuple[float, float, float, float],
    output_dir: Path,
    product: ViirsProduct,
) -> list[Path]:
    import requests

    bbox_csv = _bbox_str(bbox)
    temporal = _temporal_str(dt)
    items: list[dict[str, Any]] = []

    for version in _versions_for(product):
        params = {
            "short_name": product.short_name,
            "version": version,
            "temporal": temporal,
            "bounding_box": bbox_csv,
            "page_size": "100",
        }
        logger.info("CMR UMM-JSON search version=%s", version)
        resp = requests.get(CMR_GRANULES_UMM, params=params, timeout=120)
        resp.raise_for_status()
        items = list(resp.json().get("items") or [])
        if items:
            break

    if not items:
        raise RuntimeError(
            f"No {product.short_name} granules from CMR for date={dt:%Y-%m-%d} bbox={bbox_csv}"
        )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filelist: list[Path] = []

    for item in items:
        url = _https_url_from_umm_item(item)
        if not url:
            logger.warning("No HTTPS URL for granule meta=%s", item.get("meta"))
            continue
        name = Path(urllib.parse.urlparse(url).path).name or "viirs_granule.h5"
        dest = output_dir / name
        logger.info("Downloading via Result._getHttpData: %s", url)
        local = _http_download_via_result(maap, url, dest)
        if local.exists():
            filelist.append(local)

    if not filelist:
        raise RuntimeError("CMR UMM ok but no files downloaded")
    return filelist


def _download_via_maap(
    dt: datetime,
    bbox: tuple[float, float, float, float],
    output_dir: Path,
    product: ViirsProduct,
) -> list[Path]:
    from maap.maap import MAAP

    maap = MAAP()
    try:
        return _download_via_maap_search(maap, dt, bbox, output_dir, product)
    except Exception as search_exc:  # noqa: BLE001
        logger.warning(
            "searchGranule/getData failed (%s); trying CMR UMM + _getHttpData", search_exc
        )
        return _download_via_cmr_umm(maap, dt, bbox, output_dir, product)


def _download_via_earthaccess(
    dt: datetime,
    bbox: tuple[float, float, float, float],
    output_dir: Path,
    product: ViirsProduct,
) -> list[Path]:
    import earthaccess

    logger.info("earthaccess fallback for %s...", product.short_name)
    auth = earthaccess.login(strategy="environment") or earthaccess.login(strategy="netrc")
    if not auth:
        raise RuntimeError(
            "earthaccess login failed. Set EARTHDATA_TOKEN or ~/.netrc, "
            "or on MAAP rely on maap-py + MAAP_PGT."
        )

    results = earthaccess.search_data(
        short_name=product.short_name,
        version=product.version,
        temporal=(dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m-%dT23:59:59"), True),
        bounding_box=bbox,
    )
    if not results:
        raise RuntimeError(f"No {product.short_name} via earthaccess for {dt:%Y-%m-%d}")

    downloaded = earthaccess.download(results, local_path=output_dir, show_progress=False)
    return [Path(p) for p in downloaded]


def download_viirs(
    dt: datetime,
    bbox: tuple[float, float, float, float],
    output_dir: str | Path,
    product: str = DEFAULT_VIIRS_PRODUCT,
) -> dict[str, list[Path]]:
    viirs_product = get_viirs_product(product)
    validate_viirs_date(dt, viirs_product)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filelist: list[Path] | None = None
    maap_error: Exception | None = None

    try:
        filelist = _download_via_maap(dt, bbox, output_dir, viirs_product)
        logger.info("VIIRS via maap-py: %d file(s)", len(filelist))
    except ImportError:
        logger.info("maap-py missing; earthaccess fallback")
    except Exception as exc:  # noqa: BLE001
        maap_error = exc
        logger.warning("maap-py failed (%s); trying earthaccess", exc)

    if filelist is None:
        try:
            filelist = _download_via_earthaccess(dt, bbox, output_dir, viirs_product)
        except Exception as exc:
            if maap_error is not None:
                raise RuntimeError(
                    f"VIIRS download failed via maap-py ({maap_error}) "
                    f"and earthaccess ({exc})"
                ) from exc
            raise

    return {"gap_filled_ntl": [convert_to_tiff(f, f.with_suffix(".tif")) for f in filelist]}
