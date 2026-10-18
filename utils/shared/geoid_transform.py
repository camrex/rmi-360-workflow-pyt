# =============================================================================
# 🌐 Geoid Height Conversion (utils/shared/geoid_transform.py)
# -----------------------------------------------------------------------------
# Purpose:             Converts ITRF/NAD83 ellipsoidal heights to NAVD88 orthometric heights
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.0
# Author:              RMI Valuation, LLC
# Created:             2026-07-17
# Last Updated:        2026-10-01
#
# Description:
#   The XVN/Point One camera positions carry *ellipsoidal* heights (mount point
#   POLARIS = ITRF2014 at the current epoch), while the OID's vertical CRS
#   (EPSG:5703) and its elevation source (Esri Terrain3D) are NAVD88
#   *orthometric*. The conversion has two steps:
#     1. Reference frame (to_nad83_2011): GEOID18 is defined against NAD83(2011),
#        so heights in a global frame (ITRF2014/ITRF2020/WGS84) are first moved to
#        NAD83(2011) at the capture epoch with PROJ's time-dependent Helmert
#        (about +0.9 to +1.5 m in height across CONUS). NAD83(2011) input skips it.
#     2. Geoid (ellipsoidal_to_orthometric): NAD83(2011) ellipsoidal -> NAVD88 via
#        GEOID18 (EPSG:4979 -> EPSG:6349), pinned to the operation that actually
#        applies the GEOID18 grid so a missing grid can never silently pass
#        through unconverted values.
#   Only the Z is converted — horizontal coordinates are never modified.
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
    "SOURCE_FRAMES",
    "SUPPORTED_GEOID_MODELS",
    "decimal_year",
    "get_frame_transformer",
    "get_geoid_transformer",
    "to_nad83_2011",
    "ellipsoidal_to_orthometric",
]

from datetime import date, datetime
from functools import lru_cache

import numpy as np

# Geoid step: EPSG:4979 -> EPSG:6349 (NAD83(2011) + NAVD88 height). PROJ's pinned
# operation is a bare GEOID18 vgridshift — it treats the input as NAD83(2011)
# ellipsoidal height (PROJ's WGS 84 -> NAD83(2011) step is a null placeholder).
# to_nad83_2011 supplies the frame shift first. Only the transformed Z is used.
_SOURCE_CRS = 4979
_TARGET_CRS = 6349

# Reference frame of the input ellipsoidal heights -> geographic 3D EPSG code to
# transform from (None = already NAD83(2011), no shift). Point One mount point
# POLARIS is ITRF2014 @ current epoch; POLARIS_LOCAL is NAD83(2011) @ 2010.0.
# PROJ's WGS 84 -> NAD83(2011) operation is a zero-shift placeholder, so WGS84 is
# treated as ITRF2020, which current WGS84 realizations match to a few cm.
SOURCE_FRAMES = {
    "NAD83_2011": None,
    "ITRF2020": 9989,
    "ITRF2014": 7912,
    "WGS84": 9989,
}
_NAD83_2011_GEOG3D = 6319

# Plausible ITRF -> NAD83(2011) ellipsoidal height change across CONUS (roughly
# +0.9 m in the west to +1.5 m in the southeast). Near zero means a no-op or
# ballpark operation was used; outside the band means something else is wrong.
_MIN_FRAME_SHIFT_M = 0.1
_MAX_FRAME_SHIFT_M = 3.0

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


def decimal_year(value) -> float:
    """Decimal year (e.g. 2026.05) of a date/datetime, used as the capture epoch
    for the time-dependent frame transformation. Time zone is irrelevant at this
    precision (the shift changes by ~1 mm/year)."""
    if isinstance(value, datetime):
        dt = value.replace(tzinfo=None)
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        raise TypeError(f"Expected a date/datetime for the capture epoch, got {type(value).__name__}")
    start = datetime(dt.year, 1, 1)
    end = datetime(dt.year + 1, 1, 1)
    return dt.year + (dt - start).total_seconds() / (end - start).total_seconds()


@lru_cache(maxsize=8)
def get_frame_transformer(source_frame: str):
    """Transformer from ``source_frame`` to NAD83(2011) geographic 3D, pinned to
    PROJ's time-dependent Helmert operation; None for NAD83_2011 (no shift).

    Raises:
        GeoidTransformError: For an unknown frame, or when no time-dependent
            (``helmert`` + ``t_epoch``) operation is available — never falls back
            to a ballpark/no-op operation.
    """
    frame = str(source_frame).upper()
    if frame not in SOURCE_FRAMES:
        raise GeoidTransformError(
            f"Unsupported source_frame '{source_frame}'. Supported: {', '.join(SOURCE_FRAMES)}."
        )
    epsg = SOURCE_FRAMES[frame]
    if epsg is None:
        return None

    from pyproj.transformer import TransformerGroup

    group = TransformerGroup(epsg, _NAD83_2011_GEOG3D, always_xy=True)
    for transformer in group.transformers:
        definition = transformer.definition or ""
        if "helmert" in definition and "t_epoch" in definition:
            return transformer
    raise GeoidTransformError(
        f"No time-dependent {frame} -> NAD83(2011) transformation is available in PROJ. "
        "Refusing to convert heights without the reference-frame shift."
    )


def to_nad83_2011(lon, lat, h_ellipsoid, source_frame: str, epoch):
    """Move ellipsoidal heights (m) from ``source_frame`` to NAD83(2011).

    Args:
        lon, lat: Decimal degrees (scalars or array-likes).
        h_ellipsoid: Ellipsoidal height(s) in meters, in ``source_frame``.
        source_frame: Key of SOURCE_FRAMES.
        epoch: Capture epoch(s) as decimal year — a scalar or one per point.

    Returns:
        Tuple ``(h_nad83, shift)`` of numpy arrays (``shift = h_nad83 - h_in``).
        For NAD83_2011 the heights come back unchanged with zero shift.

    Raises:
        GeoidTransformError: If any shift is non-finite or its magnitude falls
            outside the plausible band (a near-zero shift means a no-op was used).
    """
    lon = np.atleast_1d(np.asarray(lon, dtype=float))
    lat = np.atleast_1d(np.asarray(lat, dtype=float))
    h_in = np.atleast_1d(np.asarray(h_ellipsoid, dtype=float))

    transformer = get_frame_transformer(source_frame)
    if transformer is None:
        return h_in, np.zeros_like(h_in)

    epochs = np.array(np.broadcast_to(np.asarray(epoch, dtype=float), h_in.shape))
    _, _, h_out, _ = transformer.transform(lon, lat, h_in, epochs)
    h_out = np.asarray(h_out, dtype=float)
    shift = h_out - h_in

    magnitude = np.abs(shift)
    implausible = (~np.isfinite(shift) | (magnitude < _MIN_FRAME_SHIFT_M)
                   | (magnitude > _MAX_FRAME_SHIFT_M))
    if implausible.any():
        bad = int(implausible.sum())
        i = int(np.argmax(implausible))
        raise GeoidTransformError(
            f"{bad} point(s) produced an implausible {source_frame} -> NAD83(2011) height "
            f"change (first: {shift[i]:.3f} m at lon={lon[i]:.6f}, lat={lat[i]:.6f}; expected "
            f"{_MIN_FRAME_SHIFT_M} m .. {_MAX_FRAME_SHIFT_M} m in magnitude). A near-zero "
            "shift means a no-op transformation was used."
        )
    return h_out, shift


def ellipsoidal_to_orthometric(lon, lat, h_ellipsoid, model: str = "GEOID18"):
    """Convert NAD83(2011) ellipsoidal heights (m) to NAVD88 orthometric heights (m).

    Heights in another frame (ITRF2014 from POLARIS, ITRF2020, WGS84) must go
    through ``to_nad83_2011`` first — this step alone treats its input as
    NAD83(2011). Accepts scalars or array-likes and transforms the whole batch in
    one call. Only the Z is converted; the caller must keep its original lon/lat.

    Args:
        lon: Longitude(s), decimal degrees.
        lat: Latitude(s), decimal degrees.
        h_ellipsoid: NAD83(2011) ellipsoidal height(s) in meters.
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
