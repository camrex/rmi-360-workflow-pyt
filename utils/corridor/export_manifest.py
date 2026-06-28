# =============================================================================
# 📤 Corridor Stage 6 — Export Manifest (utils/corridor/export_manifest.py)
# -----------------------------------------------------------------------------
# Purpose:             Export the kept set (include=1 AND flag=1) as a single
#                      combined manifest CSV for manifest-driven Add Images To OID.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Description:
#   One row per kept panorama, ordered by mp_pre then sub_order (corridor
#   sequence). Path is the operative key for Add Images To OID (which reads X/Y/Z
#   + orientation from EXIF); other columns are traceability / QC.
#
#   Field formatting is controlled at source so the CSV is clean:
#     - track : '4' for tagged points, '' (empty) for main (not 4.0)
#     - reel / frame : zero-padding preserved
#     - mp_meas / X / Y / Z : full precision, no literal "NaN"
#
#   Storage folders do NOT map 1:1 to subdivisions; Path carries the true location
#   regardless. AWS staging must follow actual Path, not assume subdivision=folder.
#
# Ported from corridor thinning work/scripts/export_manifest.py — logic preserved.
# Int. Dependencies:    utils/corridor/units
# Ext. Dependencies:    arcpy, csv, os, collections
# =============================================================================

from __future__ import annotations

import csv
import os
from collections import defaultdict

import arcpy

from utils.corridor.units import resolve_logger

__all__ = ["export_manifest", "DEFAULT_MANIFEST_FIELDS"]

DEFAULT_MANIFEST_FIELDS = [
    "Path", "Name", "mp_pre", "track", "mp_meas", "sub_order", "reel", "frame", "X", "Y", "Z",
]


def _fmt_track(v):
    if v is None or v == "":
        return ""
    try:
        return str(int(v))
    except (ValueError, TypeError):
        return str(v)


def _fmt_padded(v, width):
    if v is None:
        return ""
    s = str(v)
    return s.zfill(width) if s.isdigit() else s


def export_manifest(
    fc: str,
    out_csv: str,
    fields: list | None = None,
    track_field: str = "track",
    flag_field: str = "flag_5m",
    pre_field: str = "mp_pre",
    sub_order_field: str = "sub_order",
    reel_field: str = "reel",
    frame_field: str = "frame",
    include_field: str = "include",
    include_value=1,
    path_sanity_sample: int = 200,
    cfg=None,
    messages=None,
) -> dict:
    """Write the kept-set manifest CSV. Returns a stats dict (count, per_subdivision)."""
    logger = resolve_logger(cfg, messages)
    fields = fields or list(DEFAULT_MANIFEST_FIELDS)
    where = f"{include_field} = {include_value} AND {flag_field} = 1"

    rows = []
    with arcpy.da.SearchCursor(fc, fields, where_clause=where) as cur:
        for r in cur:
            rows.append(list(r))

    pre_i = fields.index(pre_field)
    so_i = fields.index(sub_order_field)
    tk_i = fields.index(track_field) if track_field in fields else None
    reel_i = fields.index(reel_field) if reel_field in fields else None
    frame_i = fields.index(frame_field) if frame_field in fields else None

    reel_w = max((len(str(r[reel_i])) for r in rows if reel_i is not None and r[reel_i] is not None), default=4)
    frame_w = max((len(str(r[frame_i])) for r in rows if frame_i is not None and r[frame_i] is not None), default=6)

    rows.sort(key=lambda r: (r[pre_i] if r[pre_i] is not None else "",
                             r[so_i] if r[so_i] is not None else 1e18))

    for r in rows:
        if tk_i is not None:
            r[tk_i] = _fmt_track(r[tk_i])
        if reel_i is not None:
            r[reel_i] = _fmt_padded(r[reel_i], reel_w)
        if frame_i is not None:
            r[frame_i] = _fmt_padded(r[frame_i], frame_w)

    out_dir = os.path.dirname(out_csv)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(fields)
        w.writerows(rows)

    by_pre = defaultdict(int)
    for r in rows:
        by_pre[r[pre_i]] += 1

    logger.info(f"Manifest written: {out_csv}", indent=1)
    logger.info(f"Total kept images: {len(rows):,}", indent=2)
    logger.info("Per-subdivision:", indent=2)
    for pre in sorted(by_pre):
        logger.info(f"{pre}: {by_pre[pre]:,}", indent=3)

    # Path sanity (sample) — Path is column 0 by convention.
    missing = checked = 0
    path_i = fields.index("Path") if "Path" in fields else 0
    for r in rows[:path_sanity_sample]:
        p = r[path_i]
        checked += 1
        if p and not os.path.exists(p):
            missing += 1
    if missing:
        logger.warning(
            f"Path sanity (first {checked} sampled): {missing} not found on disk — "
            "check drive mapping / staging.",
            indent=2,
        )
    else:
        logger.info(f"Path sanity (first {checked} sampled): all resolve OK.", indent=2)

    logger.success(f"Export manifest complete: {len(rows):,} rows.", indent=1)
    return {"count": len(rows), "per_subdivision": dict(by_pre), "out_csv": out_csv,
            "path_missing_sampled": missing}
