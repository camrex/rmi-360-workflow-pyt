# =============================================================================
# 🔢 Corridor Stage 2 — Sequence (sub_order) (utils/corridor/calc_sub_order.py)
# -----------------------------------------------------------------------------
# Purpose:             Assign sub_order per (mp_pre, track) partition using mp_meas
#                      ascending with an oriented-FRAME tie/near-tie break.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Description:
#   Primary order : mp_meas ascending (position along route).
#   Tie/near-tie  : points whose mp_meas span < EPS_MILES are a group; ordered by
#                   FRAME, oriented to the local MP direction within their own
#                   capture run (reel + reel_start_ts parsed from Name). Frame is
#                   the clean, high-resolution sequence signal; this fixes
#                   quantization collapses that geometry projection can mis-order.
#   Orientation   : derived from nearest non-group same-run neighbors (does frame
#                   ascend or descend as mp_meas ascends).
#   Fallback      : geometry bracket-projection only when orientation is unknown.
#
#   Partition = (mp_pre, track). track NULL -> "_main" sentinel; parallel-track
#   overlaps stay INDEPENDENT threads so thinning does not collapse them.
#   sub_order is unique within (mp_pre, track), NOT within mp_pre alone.
#
# Ported from corridor thinning work/scripts/calc_sub_order.py — logic preserved.
# Int. Dependencies:    utils/corridor/units
# Ext. Dependencies:    arcpy, collections
# =============================================================================

from __future__ import annotations

from collections import defaultdict

import arcpy

from utils.corridor.units import (
    compile_identity_regex,
    parse_run_frame,
    resolve_logger,
    tkey,
)

__all__ = ["calc_sub_order"]


def calc_sub_order(
    fc: str,
    track_field: str = "track",
    meas_field: str = "mp_meas",
    sub_order_field: str = "sub_order",
    key_field: str = "Name",
    pre_field: str = "mp_pre",
    include_field: str = "include",
    include_value=1,
    eps_miles: float = 0.0003,
    filename_regex: str | None = None,
    cfg=None,
    messages=None,
) -> dict:
    """Compute and write ``sub_order_field`` for the in-scope points.

    EPS_MILES default 0.0003 mi (~1.6 ft): below normal spacing (~0.00065),
    above the artifact floor (0.0002). Tune per dataset from min-step/p05 stats.

    Returns a stats dict with assigned count, group counts, and per-partition counts.
    """
    logger = resolve_logger(cfg, messages)
    oid_field = arcpy.Describe(fc).OIDFieldName
    regex = compile_identity_regex(filename_regex)
    where = f"{include_field} = {include_value}"

    have = {f.name for f in arcpy.ListFields(fc)}
    if sub_order_field not in have:
        arcpy.management.AddField(fc, sub_order_field, "LONG")
        logger.info(f"Added field {sub_order_field} (LONG).", indent=2)

    # Load in-scope rows with geometry + parsed run/frame.
    rows = []
    with arcpy.da.SearchCursor(
        fc,
        [oid_field, pre_field, track_field, meas_field, "SHAPE@X", "SHAPE@Y", key_field],
        where_clause=where,
    ) as cur:
        for oid, pre, track, meas, x, y, name in cur:
            run, frame = parse_run_frame(name, regex)
            rows.append({
                "oid": oid, "pre": pre, "tk": tkey(track), "meas": meas,
                "x": x, "y": y, "run": run, "frame": frame,
            })

    # Sort by partition then measure (None measures sort last).
    rows.sort(key=lambda r: (r["pre"], r["tk"], r["meas"] if r["meas"] is not None else 1e18))
    n = len(rows)
    logger.info(f"Loaded {n:,} {where} points.", indent=2)

    # Build near-tie groups: within a partition, consecutive points whose mp_meas
    # gap to the running group anchor is < EPS_MILES belong to one group.
    groups = []
    i = 0
    while i < n:
        j = i + 1
        anchor = rows[i]["meas"]
        while (j < n
               and rows[j]["pre"] == rows[i]["pre"]
               and rows[j]["tk"] == rows[i]["tk"]
               and rows[j]["meas"] is not None
               and anchor is not None
               and (rows[j]["meas"] - anchor) < eps_miles):
            j += 1
        if j - i > 1:
            groups.append(list(range(i, j)))
        i = j
    logger.info(f"Tie/near-tie groups (size>1): {len(groups):,}", indent=2)

    def run_orientation(group_idxs):
        """+1 frame ascends with mp, -1 descends, 0 unknown."""
        g0, g1 = group_idxs[0], group_idxs[-1]
        run_counts = defaultdict(int)
        for k in group_idxs:
            run_counts[rows[k]["run"]] += 1
        grp_run = max(run_counts, key=run_counts.get) if run_counts else None
        if grp_run is None:
            return 0
        before = None
        for k in range(g0 - 1, -1, -1):
            if rows[k]["pre"] != rows[g0]["pre"] or rows[k]["tk"] != rows[g0]["tk"]:
                break
            if rows[k]["run"] == grp_run and rows[k]["frame"] is not None:
                before = rows[k]; break
        after = None
        for k in range(g1 + 1, n):
            if rows[k]["pre"] != rows[g1]["pre"] or rows[k]["tk"] != rows[g1]["tk"]:
                break
            if rows[k]["run"] == grp_run and rows[k]["frame"] is not None:
                after = rows[k]; break
        ref_frame = ref_meas = None
        for k in group_idxs:
            if rows[k]["run"] == grp_run and rows[k]["frame"] is not None:
                ref_frame = rows[k]["frame"]; ref_meas = rows[k]["meas"]; break
        if ref_frame is None:
            return 0
        for nb in (after, before):
            if nb is not None and nb["meas"] is not None and nb["meas"] != ref_meas:
                dmeas = nb["meas"] - ref_meas
                dframe = nb["frame"] - ref_frame
                if dframe == 0:
                    continue
                return 1 if (dframe > 0) == (dmeas > 0) else -1
        return 0

    def geom_fallback_order(group_idxs):
        """Bracket-projection ordering, used only when orientation unknown."""
        g = group_idxs
        pre, tk = rows[g[0]]["pre"], rows[g[0]]["tk"]
        gset = set(g)
        before = None
        for k in range(g[0] - 1, -1, -1):
            if rows[k]["pre"] != pre or rows[k]["tk"] != tk:
                break
            if k not in gset:
                before = rows[k]; break
        after = None
        for k in range(g[-1] + 1, n):
            if rows[k]["pre"] != pre or rows[k]["tk"] != tk:
                break
            if k not in gset:
                after = rows[k]; break
        if before is None:
            before = rows[g[0]]
        if after is None:
            after = rows[g[-1]]
        dx, dy = after["x"] - before["x"], after["y"] - before["y"]
        mag = (dx * dx + dy * dy) ** 0.5
        if mag == 0:
            return g
        ux, uy = dx / mag, dy / mag
        return sorted(
            g, key=lambda k: (rows[k]["x"] - before["x"]) * ux + (rows[k]["y"] - before["y"]) * uy
        )

    # Order each group and write its members back into the sequence positions.
    final = list(range(n))
    n_frame_ordered = n_fallback = 0
    for g in groups:
        ori = run_orientation(g)
        have_frames = all(rows[k]["frame"] is not None for k in g)
        if ori != 0 and have_frames:
            ordered = sorted(g, key=lambda k: rows[k]["frame"], reverse=(ori < 0))
            n_frame_ordered += 1
        else:
            ordered = geom_fallback_order(g)
            n_fallback += 1
        for slot, idx in zip(g, ordered):
            final[slot] = idx

    logger.info(
        f"Groups frame-ordered: {n_frame_ordered:,}; geometry fallback: {n_fallback:,}",
        indent=2,
    )

    # Assign sub_order per (pre, track).
    sub = {}
    counter = defaultdict(int)
    for pos in final:
        r = rows[pos]
        part = (r["pre"], r["tk"])
        counter[part] += 1
        sub[r["oid"]] = counter[part]

    with arcpy.da.UpdateCursor(fc, [oid_field, sub_order_field], where_clause=where) as cur:
        for row in cur:
            if row[0] in sub:
                row[1] = sub[row[0]]
                cur.updateRow(row)

    logger.info(f"Assigned {sub_order_field} to {len(sub):,} points.", indent=2)
    per_partition = {}
    logger.info("Per-partition counts (mp_pre, track):", indent=2)
    for part in sorted(counter):
        per_partition[f"{part[0]}/{part[1]}"] = counter[part]
        logger.info(f"{part[0]} / {part[1]}: {counter[part]:,}", indent=3)

    logger.success("Corridor sub_order complete.", indent=1)
    return {
        "assigned": len(sub),
        "groups": len(groups),
        "frame_ordered": n_frame_ordered,
        "geometry_fallback": n_fallback,
        "per_partition": per_partition,
    }
