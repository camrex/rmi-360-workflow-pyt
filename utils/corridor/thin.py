# =============================================================================
# ✂️ Corridor Stage 4 — Anchor-Reset Thinning (utils/corridor/thin.py)
# -----------------------------------------------------------------------------
# Purpose:             Thin each (mp_pre, track) partition to ~1 image per target
#                      interval by anchor-reset walk; write a non-destructive flag.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Description:
#   Walks each (mp_pre, track) partition by sub_order. Keeps an anchor point, then
#   drops every following point within THRESHOLD planar distance of that anchor;
#   the first point that clears the threshold becomes the new anchor (kept). Resets
#   the anchor at every partition boundary so each track / subdivision thins
#   INDEPENDENTLY and dual-track overlaps retain both tracks. Distance-based (not
#   count-based) so it self-corrects to ground distance regardless of density.
#
#   Threshold is WKID-aware: data are planar in the FC's linear unit (e.g. WKID
#   6455 = US survey feet), so 5 m -> 16.4042 ft via metersPerUnit. THRESHOLD_TRIM
#   pulls the interval in slightly (e.g. 1.5 m -> ~4.5 m) to avoid occasional >5 m
#   gaps where a frame lands just short and the next is well past.
#
#   Non-destructive: writes a SHORT flag field (1=keep, 0=drop). include=0 points
#   get NULL (not part of thinning). Select flag=1 for the manifest.
#
# Ported from corridor thinning work/scripts/thin_5m.py — logic preserved.
# Int. Dependencies:    utils/corridor/units
# Ext. Dependencies:    arcpy, math, collections
# =============================================================================

from __future__ import annotations

from collections import defaultdict

import arcpy

from utils.corridor.units import (
    anchor_reset_keep,
    resolve_logger,
    resolve_progressor,
    threshold_to_data_units,
    tkey,
)

__all__ = ["thin"]


def thin(
    fc: str,
    track_field: str = "track",
    flag_field: str = "flag_5m",
    sub_order_field: str = "sub_order",
    pre_field: str = "mp_pre",
    include_field: str = "include",
    include_value=1,
    threshold_m: float = 5.0,
    trim_m: float = 0.0,
    wkid: int | None = None,
    meters_per_unit_override: float | None = None,
    cfg=None,
    messages=None,
) -> dict:
    """Anchor-reset thin to a target interval; write ``flag_field`` (1 keep / 0 drop).

    Args:
        threshold_m: Target interval in METERS (converted to FC units via WKID).
        trim_m: Pull-in in METERS (e.g. 1.5 -> ~4.5 m effective). 0 = none.
        wkid: WKID of the data's projected CRS (for metersPerUnit conversion).
        meters_per_unit_override: Bypass WKID lookup (tests / explicit control).

    Returns a stats dict: kept, dropped, effective_threshold_units, per_partition.
    """
    logger = resolve_logger(cfg, messages)
    oid_field = arcpy.Describe(fc).OIDFieldName
    where = f"{include_field} = {include_value}"

    threshold_units = threshold_to_data_units(threshold_m, wkid, meters_per_unit_override)
    trim_units = threshold_to_data_units(trim_m, wkid, meters_per_unit_override) if trim_m else 0.0
    eff_threshold = threshold_units - trim_units
    mpu = threshold_units and (threshold_m / threshold_units)  # back out metersPerUnit for reporting

    have = {f.name for f in arcpy.ListFields(fc)}
    if flag_field not in have:
        arcpy.management.AddField(fc, flag_field, "SHORT")
        logger.info(f"Added field {flag_field} (SHORT).", indent=2)

    # Load in-scope rows with geometry + sub_order, grouped by partition.
    parts = defaultdict(list)
    with arcpy.da.SearchCursor(
        fc,
        [oid_field, pre_field, track_field, sub_order_field, "SHAPE@X", "SHAPE@Y"],
        where_clause=where,
    ) as cur:
        for oid, pre, track, so, x, y in cur:
            parts[(pre, tkey(track))].append({"oid": oid, "so": so, "x": x, "y": y})

    for p in parts:
        parts[p].sort(key=lambda r: (r["so"] if r["so"] is not None else 1e18))

    total = sum(len(v) for v in parts.values())
    logger.info(
        f"Loaded {total:,} {where} points across {len(parts)} partitions. "
        f"Effective threshold {eff_threshold:.4f} units "
        f"(~{eff_threshold * (mpu or 0):.3f} m).",
        indent=2,
    )

    # Anchor-reset walk per partition.
    keep = {}
    per_part = {}
    with resolve_progressor(cfg, total=len(parts), label="Thinning partitions") as progressor:
        for idx, p in enumerate(sorted(parts), 1):
            seq = parts[p]
            flags = anchor_reset_keep([(r["x"], r["y"]) for r in seq], eff_threshold)
            kept = dropped = 0
            for r, f in zip(seq, flags):
                keep[r["oid"]] = f
                if f:
                    kept += 1
                else:
                    dropped += 1
            per_part[p] = (kept, dropped)
            progressor.update(idx)

    # Write flag back. (include=0 points get flag = NULL — not part of thinning.)
    written = 0
    with arcpy.da.UpdateCursor(fc, [oid_field, flag_field], where_clause=where) as cur:
        for row in cur:
            if row[0] in keep:
                row[1] = keep[row[0]]
                written += 1
                cur.updateRow(row)

    tot_keep = sum(k for k, _ in per_part.values())
    tot_drop = sum(d for _, d in per_part.values())
    logger.info(f"Wrote {flag_field} for {written:,} points.", indent=2)
    per_partition = {}
    logger.info("Per-partition keep / drop:", indent=2)
    for p in sorted(per_part):
        k, d = per_part[p]
        npp = k + d
        per_partition[f"{p[0]}/{p[1]}"] = {"keep": k, "drop": d}
        logger.info(
            f"{p[0]} / {p[1]}: keep {k:,}  drop {d:,}  ({k/npp*100:.1f}% kept of {npp:,})",
            indent=3,
        )
    logger.success(
        f"TOTAL: keep {tot_keep:,}  drop {tot_drop:,}  "
        f"({(tot_keep/total*100) if total else 0:.1f}% kept). "
        f"Select {flag_field} = 1 for the manifest.",
        indent=1,
    )

    return {
        "kept": tot_keep,
        "dropped": tot_drop,
        "effective_threshold_units": eff_threshold,
        "per_partition": per_partition,
    }
