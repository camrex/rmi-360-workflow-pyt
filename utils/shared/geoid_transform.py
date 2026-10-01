# =============================================================================
# 🌐 Geoid Height Conversion (utils/shared/geoid_transform.py)
# -----------------------------------------------------------------------------
# Purpose:             Converts WGS84/ITRF ellipsoidal heights to NAVD88 orthometric heights
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2026-07-17
# Last Updated:        2026-07-17
#
# Description:
#   The XVN/Point One camera positions carry WGS84/ITRF2014 *ellipsoidal* heights,
#   while the OID's vertical CRS (EPSG:5703) and its elevation source (Esri
#   Terrain3D) are NAVD88 *orthometric*. This module converts camera Z values from
#   ellipsoidal to NAVD88 via the GEOID18 geoid model using pyproj
#   (EPSG:4979 -> EPSG:6349), pinned to the operation that actually applies the
#   GEOID18 grid so a missing grid can never silently pass through unconverted
#   values. Only the Z is converted — horizontal coordinates are never modified.
#
# File Location:        /utils/shared/geoid_transform.py
# Called By:            utils/calculate_oid_attributes.py
# Int. Dependencies:    None (arcpy-free; raises GeoidTransformError, caller logs)
# Ext. Dependencies:    pyproj (ships with ArcGIS Pro's Python), numpy
#
# Documentation:
#   See: docs/geoid_conversion.md
#
# Notes:
#   - GEOID18 covers CONUS only. Points outside the grid produce non-finite
#     results and raise; they are never returned unconverted or extrapolated.
#   - The GEOID18 grid (us_noaa_g2018u0.tif) is bundled with ArcGIS Pro's PROJ
#     data directory. For other environments see docs/geoid_conversion.md.
# =============================================================================

__all__ = [
    "GeoidTransformError",
    "get_geoid_transformer",
    "ellipsoidal_to_orthometric",
]

from functools import lru_cache

import numpy as np

# Source: WGS84 geographic 3D with ellipsoidal height (XVN/POLARIS is ITRF2014,
# aligned with WGS84 to ~cm). Target: NAD83(2011) + NAVD88 height (compound).
# Only the transformed Z is ever used; the horizontal stays WGS84.
_SOURCE_CRS = 4979
_TARGET_CRS = 6349

# Geoid models supported per region, keyed by the PROJ grid file that must be
# present for the conversion to be real. GEOID18 covers CONUS only; other NGS
# models (e.g. GEOID12B for AK/HI territories) can be added here when needed.
SUPPORTED_GEOID_MODELS = {
    "GEOID18": "us_noaa_g2018u0",
}

# Plausible GEOID18 separation band for CONUS (published range is roughly
# -8 m to -33 m; margin added). A separation outside this band means the wrong
# grid applied, the input was not ellipsoidal, or the point is outside coverage.
_MIN_SEPARATION_M = -50.0
_MAX_SEPARATION_M = -2.0


class GeoidTransformError(RuntimeError):
    """Raised when the geoid conversion cannot be performed safely (unsupported
    model, missing grid, out-of-coverage points, or implausible separations)."""


@lru_cache(maxsize=4)
def get_geoid_transformer(model: str = "GEOID18"):
    """Return a pyproj Transformer pinned to the operation that applies ``model``.

    Selects, from all candidate EPSG:4979 -> EPSG:6349 operations, the one whose
    pipeline references the model's grid file (e.g. us_noaa_g2018u0.tif for
    GEOID18). This guarantees the geoid grid is both installed and actually used
    — PROJ's default operation ranking may otherwise silently fall back to a
    ballpark or no-op transform when grids are missing.

    Raises:
        GeoidTransformError: If the model is unsupported or no operation using
            its grid is available (grid not installed in the PROJ data dir).
    """
    grid = SUPPORTED_GEOID_MODELS.get(str(model).upper())
    if grid is None:
        raise GeoidTransformError(
            f"Unsupported geoid model '{model}'. Supported models: "
            f"{', '.join(sorted(SUPPORTED_GEOID_MODELS))}. GEOID18 covers CONUS only; "
            "operation outside CONUS requires adding the appropriate NGS model."
        )

    from pyproj.transformer import TransformerGroup

    group = TransformerGroup(_SOURCE_CRS, _TARGET_CRS, always_xy=True)
    for transformer in group.transformers:
        if grid in (transformer.definition or ""):
            return transformer

    import pyproj

    raise GeoidTransformError(
        f"The {model} geoid grid ({grid}.tif) is not available to PROJ "
        f"(data dir: {pyproj.datadir.get_data_dir()}). Refusing to write "
        "unconverted ellipsoidal heights. Install the grid (bundled with ArcGIS "
        "Pro; otherwise run `projsync --file " + grid + "` or copy the .tif into "
        "the PROJ data dir) — see docs/geoid_conversion.md."
    )


def ellipsoidal_to_orthometric(lon, lat, h_ellipsoid, model: str = "GEOID18"):
    """Convert WGS84/ITRF ellipsoidal heights (m) to NAVD88 orthometric heights (m).

    Accepts scalars or array-likes and transforms the whole batch in one call.
    Only the Z is converted; the caller must keep its original lon/lat.

    Args:
        lon: Longitude(s), WGS84 decimal degrees.
        lat: Latitude(s), WGS84 decimal degrees.
        h_ellipsoid: Ellipsoidal height(s) in meters.
        model: Geoid model key from SUPPORTED_GEOID_MODELS.

    Returns:
        Tuple ``(h_orthometric, separation)`` of numpy arrays, where
        ``separation`` is the applied geoid separation N = h_ellipsoid − H.

    Raises:
        GeoidTransformError: If any point falls outside the geoid model's
            coverage, or any applied separation is outside the plausible band
            (which indicates the grid did not actually apply).
    """
    lon = np.atleast_1d(np.asarray(lon, dtype=float))
    lat = np.atleast_1d(np.asarray(lat, dtype=float))
    h_in = np.atleast_1d(np.asarray(h_ellipsoid, dtype=float))

    transformer = get_geoid_transformer(model)
    # Target CRS 6349 also shifts horizontal to NAD83(2011); only the Z is kept.
    _, _, h_out = transformer.transform(lon, lat, h_in)
    h_out = np.asarray(h_out, dtype=float)

    non_finite = ~np.isfinite(h_out)
    if non_finite.any():
        bad = int(non_finite.sum())
        i = int(np.argmax(non_finite))
        raise GeoidTransformError(
            f"{bad} point(s) fall outside {model} coverage (first at "
            f"lon={lon[i]:.6f}, lat={lat[i]:.6f}). {model} covers CONUS only — "
            "refusing to return unconverted or extrapolated heights."
        )

    separation = h_in - h_out
    implausible = (separation < _MIN_SEPARATION_M) | (separation > _MAX_SEPARATION_M)
    if implausible.any():
        bad = int(implausible.sum())
        i = int(np.argmax(implausible))
        raise GeoidTransformError(
            f"{bad} point(s) produced an implausible geoid separation for {model} "
            f"(first: N={separation[i]:.2f} m at lon={lon[i]:.6f}, lat={lat[i]:.6f}; "
            f"expected {_MIN_SEPARATION_M} m .. {_MAX_SEPARATION_M} m). The geoid "
            "grid likely did not apply, or the input heights are not ellipsoidal."
        )

    return h_out, separation
