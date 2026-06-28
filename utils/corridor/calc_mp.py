# =============================================================================
# 📍 Corridor Stage 1 — Calculate Mileposts, PER-ROUTE (utils/corridor/calc_mp.py)
# -----------------------------------------------------------------------------
# Purpose:             Write mp_meas (along-route measure) for every panorama point
#                      using a PER-ROUTE Locate Features Along Routes.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Description:
#   For each subdivision (mp_pre), locate ONLY that subdivision's points against
#   ONLY that subdivision's route. Cross-route snapping at adjacent / parallel
#   subdivisions is therefore structurally impossible: a Harvard point near the
#   Geneva line cannot take a Geneva measure because Geneva is not in the route
#   input for the Harvard pass. This was REQUIRED (not optional) — a single global
#   Locate snapped junction points to the wrong route and produced huge mp jumps.
#
#   Writes mp_meas at full precision for ALL points (regardless of include).
#   Matches located results back by Name (unique id). NULL mp_meas is expected for
#   points genuinely beyond the search radius of their own route.
#
# Ported from corridor thinning work/scripts/calc_mp.py — logic preserved.
# Int. Dependencies:    utils/corridor/units
# Ext. Dependencies:    arcpy, time, collections
# =============================================================================

from __future__ import annotations

import time
from collections import defaultdict

import arcpy

from utils.corridor.units import resolve_logger, resolve_progressor

__all__ = ["calc_mp"]


def calc_mp(
    points_fc: str,
    routes_fc: str,
    route_id_field: str = "mp_pre",
    point_pre_field: str = "mp_pre",
    meas_field: str = "mp_meas",
    key_field: str = "Name",
    search_radius: str = "200 Feet",
    scratch_table: str | None = None,
    cfg=None,
    messages=None,
) -> dict:
    """Calculate per-route mileposts and write ``meas_field`` back to ``points_fc``.

    Args:
        points_fc: Photo point feature class.
        routes_fc: M-enabled centerline feature class.
        route_id_field: Route identifier field on the routes FC (RID).
        point_pre_field: Subdivision-prefix field on the points FC.
        meas_field: Destination DOUBLE measure field (created if missing).
        key_field: Unique image id present on both tables (matched back by this).
        search_radius: Locate search radius, e.g. "200 Feet".
        scratch_table: Per-pass Locate output table; defaults to a real FGDB table
            in ``arcpy.env.scratchGDB`` (in_memory can fail for Locate events).
        cfg: Optional ConfigManager (for logger / progressor).
        messages: Optional ArcPy messages sink.

    Returns:
        dict with keys: written, nulled, located, per_subdivision (dict).
    """
    logger = resolve_logger(cfg, messages)
    arcpy.env.overwriteOutput = True

    if scratch_table is None:
        scratch_table = arcpy.env.scratchGDB + r"\corridor_located_tmp"

    t0 = time.time()
    logger.info("=== Corridor MP calculation started ===", indent=1)
    logger.info(f"Points : {points_fc}", indent=2)
    logger.info(f"Routes : {routes_fc}", indent=2)
    logger.info(f"Radius : {search_radius}", indent=2)

    # 0. Ensure destination measure field exists as DOUBLE (precision matters).
    existing = {f.name: f for f in arcpy.ListFields(points_fc)}
    if meas_field not in existing:
        arcpy.management.AddField(points_fc, meas_field, "DOUBLE")
        logger.info(f"Added field {meas_field} (DOUBLE).", indent=2)
    elif existing[meas_field].type not in ("Double", "Single"):
        logger.error(
            f"{meas_field} exists but is {existing[meas_field].type}; make it DOUBLE "
            "to preserve precision.",
            error_type=RuntimeError, indent=1,
        )
        return {}

    # 1. Discover subdivision prefixes from the points.
    total_pts = int(arcpy.management.GetCount(points_fc)[0])
    prefixes = set()
    with arcpy.da.SearchCursor(points_fc, [point_pre_field]) as cur:
        for (pre,) in cur:
            if pre is not None:
                prefixes.add(pre)
    prefixes = sorted(prefixes)
    logger.info(f"Total points: {total_pts:,}. Subdivisions: {prefixes}", indent=2)

    # 2. Per-subdivision Locate.
    measures = {}  # Name -> measure (full precision)
    pts_lyr, rte_lyr = "corridor_pts_lyr", "corridor_rte_lyr"

    with resolve_progressor(cfg, total=len(prefixes), label="Per-route Locate") as progressor:
        for i, pre in enumerate(prefixes, 1):
            logger.info(f"--- [{i}/{len(prefixes)}] subdivision '{pre}' ---", indent=2)

            where_pts = f"{point_pre_field} = '{pre}'"
            where_rte = f"{route_id_field} = '{pre}'"

            arcpy.management.MakeFeatureLayer(points_fc, pts_lyr, where_pts)
            arcpy.management.MakeFeatureLayer(routes_fc, rte_lyr, where_rte)

            n_pts = int(arcpy.management.GetCount(pts_lyr)[0])
            n_rte = int(arcpy.management.GetCount(rte_lyr)[0])
            logger.info(f"points={n_pts:,}, route features={n_rte}", indent=3)

            if n_rte == 0:
                logger.warning(
                    f"No route with {route_id_field}='{pre}'. Skipping.", indent=3
                )
                arcpy.management.Delete(pts_lyr)
                arcpy.management.Delete(rte_lyr)
                progressor.update(i)
                continue

            t_pass = time.time()
            arcpy.lr.LocateFeaturesAlongRoutes(
                in_features=pts_lyr,
                in_routes=rte_lyr,
                route_id_field=route_id_field,
                radius_or_tolerance=search_radius,
                out_table=scratch_table,
                out_event_properties=f"{route_id_field} POINT MEAS",
            )

            got, dup = 0, 0
            with arcpy.da.SearchCursor(scratch_table, [key_field, "MEAS"]) as cur:
                for name, meas in cur:
                    if meas is None:
                        continue
                    if name in measures:
                        dup += 1
                        if meas < measures[name]:
                            measures[name] = meas
                    else:
                        measures[name] = meas
                    got += 1

            pass_secs = time.time() - t_pass
            logger.info(
                f"located {got:,} of {n_pts:,} points "
                f"({n_pts - got:,} beyond radius) in {pass_secs:.1f}s",
                indent=3,
            )
            if dup:
                logger.info(f"note: {dup:,} duplicate-name rows (kept smallest measure)", indent=3)

            arcpy.management.Delete(pts_lyr)
            arcpy.management.Delete(rte_lyr)
            progressor.update(i)

    logger.info(f"All passes complete. Images with a measure: {len(measures):,}", indent=2)

    # 3. Write mp_meas back by Name (full precision). NULL if no measure.
    written, nulled = 0, 0
    with arcpy.da.UpdateCursor(points_fc, [key_field, meas_field]) as cur:
        for row in cur:
            name = row[0]
            if name in measures:
                row[1] = measures[name]
                written += 1
            else:
                row[1] = None
                nulled += 1
            cur.updateRow(row)

    logger.info(
        f"Wrote {meas_field} for {written:,} points; {nulled:,} NULL "
        f"(expected: points beyond {search_radius} of their own route).",
        indent=2,
    )

    # 4. Per-subdivision diagnostics.
    counts = defaultdict(lambda: [0, 0])
    with arcpy.da.SearchCursor(points_fc, [point_pre_field, meas_field]) as cur:
        for pre, m in cur:
            counts[pre][0 if m is not None else 1] += 1

    per_subdivision = {}
    logger.info("Per-subdivision results (written / null):", indent=2)
    for pre in sorted(counts):
        w, n = counts[pre]
        pct = (n / (w + n) * 100) if (w + n) else 0
        per_subdivision[pre] = {"written": w, "null": n}
        logger.info(f"{pre}: {w:,} written, {n:,} null ({pct:.1f}% null)", indent=3)

    # cleanup (guarded against edit-session lock)
    try:
        arcpy.management.Delete(scratch_table)
    except Exception as e:  # noqa: BLE001 - cleanup best-effort
        logger.warning(f"Could not delete {scratch_table} ({e}). Delete manually if needed.", indent=2)

    logger.success(f"=== Corridor MP done in {time.time() - t0:.1f}s ===", indent=1)
    return {
        "written": written,
        "nulled": nulled,
        "located": len(measures),
        "per_subdivision": per_subdivision,
    }
