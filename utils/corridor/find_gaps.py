# =============================================================================
# 📏 Corridor Stage 5b — Find Gaps (utils/corridor/find_gaps.py)
# -----------------------------------------------------------------------------
# Purpose:             Read-only: list large gaps in the sub_order sequence per
#                      (mp_pre, track), classified reel-boundary vs within-run.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Description:
#   Walks each partition by sub_order and reports every consecutive step larger
#   than a threshold, with location, milepost, and the image names on each side.
#   Same reel = gap WITHIN a continuous run (lift-off / pause); different reel =
#   boundary between two capture runs (expected gap).
#
# Ported from corridor thinning work/scripts/find_gaps.py — logic preserved.
# Int. Dependencies:    utils/corridor/units
# Ext. Dependencies:    arcpy, math, collections
# =============================================================================

from __future__ import annotations

import math
from collections import defaultdict

import arcpy

from utils.corridor.units import resolve_logger, tkey

__all__ = ["find_gaps"]


def find_gaps(
    fc: str,
    track_field: str = "track",
    meas_field: str = "mp_meas",
    sub_order_field: str = "sub_order",
    pre_field: str = "mp_pre",
    include_field: str = "include",
    include_value=1,
    gap_threshold_ft: float = 15.0,
    reel_field: str = "reel",
    frame_field: str = "frame",
    cfg=None,
    messages=None,
) -> dict:
    """Read-only: report sub_order steps over ``gap_threshold_ft``. Returns a dict."""
    logger = resolve_logger(cfg, messages)
    oid_field = arcpy.Describe(fc).OIDFieldName
    where = f"{include_field} = {include_value}"

    rows = []
    with arcpy.da.SearchCursor(
        fc,
        [oid_field, pre_field, track_field, meas_field, sub_order_field,
         "SHAPE@X", "SHAPE@Y", "Name", reel_field, frame_field],
        where_clause=where,
    ) as cur:
        for oid, pre, track, meas, so, x, y, name, reel, frame in cur:
            rows.append({"oid": oid, "pre": pre, "tk": tkey(track), "meas": meas,
                         "so": so, "x": x, "y": y, "name": name, "reel": reel, "frame": frame})

    parts = defaultdict(list)
    for r in rows:
        parts[(r["pre"], r["tk"])].append(r)
    for p in parts:
        parts[p].sort(key=lambda r: (r["so"] if r["so"] is not None else 1e18))

    gaps = []
    for p in sorted(parts):
        seq = parts[p]
        for i in range(1, len(seq)):
            a, b = seq[i-1], seq[i]
            d = math.hypot(b["x"]-a["x"], b["y"]-a["y"])
            if d > gap_threshold_ft:
                dmp_ft = None
                if a["meas"] is not None and b["meas"] is not None:
                    dmp_ft = abs(b["meas"] - a["meas"]) * 5280.0
                gaps.append({
                    "pre": p[0], "tk": p[1], "dist": d, "so1": a["so"], "so2": b["so"],
                    "oid1": a["oid"], "oid2": b["oid"], "reel1": a["reel"], "frame1": a["frame"],
                    "reel2": b["reel"], "frame2": b["frame"], "mp1": a["meas"], "mp2": b["meas"],
                    "dmp_ft": dmp_ft, "same_reel": a["reel"] == b["reel"],
                })
    gaps.sort(key=lambda g: g["dist"], reverse=True)

    logger.info(f"Gaps over {gap_threshold_ft:.1f}: {len(gaps)}", indent=1)
    for g in gaps:
        mp1 = f"{g['mp1']:.4f}" if g["mp1"] is not None else "—"
        mp2 = f"{g['mp2']:.4f}" if g["mp2"] is not None else "—"
        dmp = f"{g['dmp_ft']:,.1f}" if g["dmp_ft"] is not None else "—"
        kind = ("within one reel (capture pause / lift-off)" if g["same_reel"]
                else "reel boundary (separate capture runs)")
        logger.info(
            f"{g['pre']}/{g['tk']} planar={g['dist']:,.1f} sub_order {g['so1']}->{g['so2']} "
            f"OID {g['oid1']}->{g['oid2']} reel/frame {g['reel1']}/{g['frame1']}->"
            f"{g['reel2']}/{g['frame2']} mp {mp1}->{mp2} (along-route {dmp}) [{kind}]",
            indent=2,
        )

    by_part = defaultdict(list)
    for g in gaps:
        by_part[(g["pre"], g["tk"])].append(g["dist"])
    logger.info("Gap count by partition:", indent=1)
    for p in sorted(by_part):
        ds = by_part[p]
        logger.info(f"{p[0]}/{p[1]}: {len(ds)} gaps, largest {max(ds):,.1f}", indent=2)

    within_run = sum(1 for g in gaps if g["same_reel"])
    logger.success(
        f"Find Gaps complete (read-only): {len(gaps)} gaps "
        f"({within_run} within-run, {len(gaps)-within_run} reel-boundary).",
        indent=1,
    )
    return {"gaps": len(gaps), "within_run": within_run, "reel_boundary": len(gaps) - within_run}
