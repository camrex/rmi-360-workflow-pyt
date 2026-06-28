# =============================================================================
# 📐 Corridor Thinning Shared Helpers (utils/corridor/units.py)
# -----------------------------------------------------------------------------
# Purpose:             Shared, mostly arcpy-free helpers for the corridor thinning
#                      pipeline: WKID-aware linear-unit conversion, panorama
#                      filename identity parsing, partition key, and lightweight
#                      logger / progressor fallbacks so each stage can run with or
#                      without a ConfigManager.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Description:
#   The corridor thinning stages were ported from validated standalone ArcGIS Pro
#   scripts. This module centralizes the cross-cutting bits so the per-stage logic
#   stays faithful to the originals while being parameterized for the toolbox.
#
#   Correctness rules preserved from PIPELINE.md:
#     - Reel identity = (reel, reel_start_ts) parsed from the FILENAME, never the
#       reel number alone (a battery/power-cycle bug can inject out-of-sequence
#       reels). The filename embeds the reel START timestamp, the reliable key.
#     - Threshold math is WKID-aware. WKID 6455 is US survey FEET; 5 m = 16.4042 ft
#       (metersPerUnit = 0.3048006096). Never hard-code "5".
#
# File Location:        /utils/corridor/units.py
# Int. Dependencies:    None (arcpy imported lazily, only when a WKID lookup needs it)
# Ext. Dependencies:    re
# =============================================================================

from __future__ import annotations

import re
from typing import Callable, Optional, Tuple

__all__ = [
    "DEFAULT_PANO_REGEX",
    "compile_identity_regex",
    "parse_run_frame",
    "parse_reel_frame",
    "tkey",
    "meters_per_unit",
    "linear_unit_to_meters",
    "threshold_to_data_units",
    "anchor_reset_keep",
    "resolve_logger",
    "resolve_progressor",
]

# Default panorama filename pattern. The project tag is a free wildcard.
#   pano_reel_0023_20260619-160716_26-150_000037.jpg
#     -> reel=0023, reel_start_ts=20260619-160716, frame=000037
DEFAULT_PANO_REGEX = r"reel_(\d+)_(\d{8}-\d{6})_.*_(\d+)\.jpg$"

# Linear-unit name -> meters per unit, for parsing GPLinearUnit strings ("5 Meters",
# "16.4042 Feet") without arcpy. US survey foot is distinct from the international
# foot and matters for WKID 6455 math.
_UNIT_TO_METERS = {
    "meter": 1.0,
    "meters": 1.0,
    "metre": 1.0,
    "metres": 1.0,
    "m": 1.0,
    "foot": 0.3048,
    "feet": 0.3048,
    "ft": 0.3048,
    "internationalfoot": 0.3048,
    "internationalfeet": 0.3048,
    "ussurveyfoot": 0.3048006096012192,
    "ussurveyfeet": 0.3048006096012192,
    "surveyfoot": 0.3048006096012192,
    "surveyfeet": 0.3048006096012192,
    "kilometer": 1000.0,
    "kilometers": 1000.0,
    "km": 1000.0,
    "mile": 1609.344,
    "miles": 1609.344,
    "yard": 0.9144,
    "yards": 0.9144,
}


def compile_identity_regex(pattern: Optional[str] = None) -> "re.Pattern":
    """Compile the panorama-identity regex (case-insensitive). Falls back to the
    default pattern when ``pattern`` is empty/None."""
    return re.compile(pattern or DEFAULT_PANO_REGEX, re.IGNORECASE)


def parse_run_frame(name: Optional[str], regex: "re.Pattern") -> Tuple[Optional[tuple], Optional[int]]:
    """Return ``((reel, reel_start_ts), frame)`` parsed from ``name``.

    The capture run key is ``(reel, reel_start_ts)`` — the reliable cross-reel
    ordering key per PIPELINE.md. Returns ``(None, None)`` when ``name`` does not
    match the pattern.
    """
    m = regex.search(name or "")
    if not m:
        return None, None
    return (m.group(1), m.group(2)), int(m.group(3))


def parse_reel_frame(name: Optional[str], regex: "re.Pattern"):
    """Return ``(reel, reel_start_ts, frame)`` parsed from ``name`` or ``None``."""
    m = regex.search(name or "")
    if not m:
        return None
    return m.group(1), m.group(2), int(m.group(3))


def tkey(track) -> str:
    """Partition track key. NULL/empty track -> '_main' sentinel; otherwise the
    track coerced to string (avoids mixed-type sort with SHORT track values)."""
    return "_main" if track in (None, "") else str(track)


def meters_per_unit(wkid: Optional[int] = None, override: Optional[float] = None) -> float:
    """Meters-per-linear-unit for a projected coordinate system.

    Resolution order:
      1. ``override`` if provided (used by tests and to avoid arcpy).
      2. ``arcpy.SpatialReference(wkid).metersPerUnit`` when arcpy is available.
      3. A small built-in table for common project WKIDs.

    For WKID 6455 (US survey feet) this returns 0.3048006096012192 so that
    5 m -> 16.4042 ft exactly.
    """
    if override is not None:
        return float(override)

    if wkid is not None:
        try:  # arcpy is the authoritative source when running inside ArcGIS Pro
            import arcpy  # type: ignore
            sr = arcpy.SpatialReference(int(wkid))
            mpu = getattr(sr, "metersPerUnit", None)
            if mpu:
                return float(mpu)
        except Exception:
            pass

        # arcpy-free fallback for the WKIDs this workflow commonly uses.
        known = {
            6455: 0.3048006096012192,  # NAD83(2011) IL SP East, US survey ft
            2229: 0.3048006096012192,  # NAD83 CA Zone 5, US ft
            6492: 0.3048006096012192,  # NAD83 MA Mainland, US ft
            26914: 1.0,                # NAD83 UTM 14N, meters
        }
        if int(wkid) in known:
            return known[int(wkid)]

    raise ValueError(
        f"Could not determine metersPerUnit for WKID {wkid!r}. "
        "Pass an explicit override or run where arcpy is available."
    )


def linear_unit_to_meters(linear_unit: str) -> float:
    """Parse a GPLinearUnit string like '5 Meters' or '16.4042 Feet' to meters.

    A bare number (no unit) is treated as already-in-meters.
    """
    if linear_unit is None:
        raise ValueError("linear_unit is None")
    parts = str(linear_unit).strip().split()
    value = float(parts[0])
    if len(parts) == 1:
        return value
    unit = parts[1].lower().replace("_", "").replace("-", "")
    if unit not in _UNIT_TO_METERS:
        raise ValueError(f"Unrecognized linear unit '{parts[1]}' in '{linear_unit}'.")
    return value * _UNIT_TO_METERS[unit]


def threshold_to_data_units(
    threshold_m: float,
    wkid: Optional[int] = None,
    meters_per_unit_override: Optional[float] = None,
) -> float:
    """Convert a distance in METERS to the feature class's linear units.

    ``data_units = meters / metersPerUnit``. For 5 m at WKID 6455 this yields
    16.4042 (US survey feet).
    """
    mpu = meters_per_unit(wkid=wkid, override=meters_per_unit_override)
    if mpu <= 0:
        raise ValueError(f"metersPerUnit must be positive, got {mpu}.")
    return float(threshold_m) / mpu


def anchor_reset_keep(points, eff_threshold: float):
    """Anchor-reset thinning of one already-ordered partition (arcpy-free core).

    ``points`` is a sequence of (x, y) tuples in the FC's planar units, ordered by
    sub_order. Keeps an anchor, drops every following point within ``eff_threshold``
    of it; the first point to clear becomes the new anchor (kept). Returns a list of
    ints (1 keep / 0 drop) aligned with ``points``.
    """
    import math
    keep = []
    anchor = None
    for x, y in points:
        if anchor is None:
            keep.append(1)
            anchor = (x, y)
            continue
        if math.hypot(x - anchor[0], y - anchor[1]) >= eff_threshold:
            keep.append(1)
            anchor = (x, y)
        else:
            keep.append(0)
    return keep


# ---------------------------------------------------------------------------
# Logger / progressor fallbacks so stages run standalone (no ConfigManager).
# ---------------------------------------------------------------------------
class _FallbackLogger:
    """Minimal logger mirroring LogManager's surface (info/warning/error/success/
    debug/custom). Writes to arcpy GP messages when available and to stdout.
    ``error`` raises when an ``error_type`` is supplied, matching LogManager."""

    def __init__(self):
        try:
            import arcpy  # type: ignore
            self._arcpy = arcpy
        except Exception:
            self._arcpy = None

    def _emit(self, msg, channel="message", indent=0):
        line = ("  " * int(indent or 0)) + str(msg)
        print(line)
        if self._arcpy is not None:
            try:
                if channel == "warning":
                    self._arcpy.AddWarning(line)
                elif channel == "error":
                    self._arcpy.AddError(line)
                else:
                    self._arcpy.AddMessage(line)
            except Exception:
                pass

    def info(self, msg, indent=0, **kw):
        self._emit(msg, "message", indent)

    def success(self, msg, indent=0, **kw):
        self._emit(msg, "message", indent)

    def debug(self, msg, indent=0, **kw):
        self._emit(msg, "message", indent)

    def warning(self, msg, indent=0, **kw):
        self._emit(msg, "warning", indent)

    def custom(self, msg, emoji="", indent=0, **kw):
        self._emit(f"{emoji} {msg}".strip(), "message", indent)

    def error(self, msg, error_type=None, indent=0, **kw):
        self._emit(msg, "error", indent)
        if error_type is not None:
            raise error_type(str(msg))


class _NoopProgressor:
    """Context-manager progressor with an ``update`` method; used when no
    ConfigManager is available."""

    def __init__(self, total=0, label="", **kw):
        self.total = total
        self.label = label

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def update(self, *_a, **_k):
        return None


def resolve_logger(cfg=None, messages=None):
    """Return ``cfg.get_logger()`` when a ConfigManager is supplied, else a
    lightweight fallback logger (so stages are runnable independently)."""
    if cfg is not None:
        return cfg.get_logger(messages) if messages is not None else cfg.get_logger()
    return _FallbackLogger()


def resolve_progressor(cfg, total: int, label: str = "Processing..."):
    """Return a context-manager progressor from ``cfg`` when available, else a
    no-op progressor."""
    if cfg is not None:
        return cfg.get_progressor(total=total, label=label)
    return _NoopProgressor(total=total, label=label)
