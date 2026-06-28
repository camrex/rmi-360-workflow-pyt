# =============================================================================
# 🔁 Corridor Stage 3 — Detect Reversals (utils/corridor/detect_reversals.py)
# -----------------------------------------------------------------------------
# Purpose:             Detect and REPORT capture back-ups (reversals) within each
#                      capture run. Detection/report only — nothing is excluded.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Description:
#   A reversal = within a capture run (walking by frame) the planar BEARING flips
#   to oppose the run's prevailing direction AND the span retraces at least
#   MIN_BACKTRACK_FT of actual backward displacement. The displacement floor (not
#   just bearing) guards against heading spin at near-zero speed (the real
#   false-positive risk with RTK).
#
#   Detect on ALL points (full back-and-forth geometry intact), then report each
#   reversal's include=1 (LIVE, pollutes working set) vs include=0 (HANDLED,
#   already excluded) breakdown, flagging only LIVE reversals. include=0 is a MIXED
#   bag (reversals + off-track + redundant + unneeded), so detect-on-all /
#   act-on-include=1.
#
#   Reversal RESOLUTION (keep-F2, drop R + F1-overlap) is DESIGNED but NOT built —
#   no live reversals have needed it. See PIPELINE.md "Reversal resolution".
#
# Ported from corridor thinning work/scripts/detect_reversals.py — logic preserved.
# Int. Dependencies:    utils/corridor/units
# Ext. Dependencies:    arcpy, math, collections
# =============================================================================

from __future__ import annotations

import math
from collections import defaultdict

import arcpy

from utils.corridor.units import compile_identity_regex, parse_reel_frame, resolve_logger

__all__ = ["detect_reversals"]


def _bearing(ax, ay, bx, by):
    return math.degrees(math.atan2(by - ay, bx - ax))


def _ang_diff(a, b):
    """Smallest absolute difference between two bearings, 0..180."""
    return abs((a - b + 180) % 360 - 180)


def detect_reversals(
    fc: str,
    pre_field: str = "mp_pre",
    meas_field: str = "mp_meas",
    include_field: str = "include",
    datetime_field: str = "DateTime",
    min_backtrack_ft: float = 15.0,
    oppose_deg: float = 120.0,
    prevail_window: int = 7,
    min_reversal_frames: int = 2,
    only_report_live: bool = True,
    write_reversal_id: bool = False,
    reversal_id_field: str = "reversal_id",
    include_scope: str | None = None,
    filename_regex: str | None = None,
    cfg=None,
    messages=None,
) -> dict:
    """Detect and report capture reversals. Returns a stats dict.

    Args:
        min_backtrack_ft: Minimum actual backward displacement (planar, in the FC's
            linear units) for a back-up to count.
        oppose_deg: A step bearing >= this many degrees off prevailing is "opposing".
        write_reversal_id: If True and the field exists, stamp reversal_id on points
            inside a detected reversal (None elsewhere). Detection only.
    """
    logger = resolve_logger(cfg, messages)
    oid_field = arcpy.Describe(fc).OIDFieldName
    regex = compile_identity_regex(filename_regex)

    flds = [oid_field, "Name", pre_field, meas_field, "SHAPE@X", "SHAPE@Y", datetime_field, include_field]
    kwargs = {}
    if include_scope:
        kwargs["where_clause"] = include_scope

    pts = []
    with arcpy.da.SearchCursor(fc, flds, **kwargs) as cur:
        for oid, name, pre, meas, x, y, dt, inc in cur:
            parsed = parse_reel_frame(name, regex)
            if parsed is None:
                continue
            reel, rts, frame = parsed
            pts.append({
                "oid": oid, "name": name, "pre": pre, "meas": meas,
                "x": x, "y": y, "dt": dt, "inc": inc,
                "reel": reel, "rts": rts, "frame": frame,
            })
    logger.info(f"Parsed {len(pts):,} points.", indent=2)

    runs = defaultdict(list)
    for p in pts:
        runs[(p["reel"], p["rts"])].append(p)
    for k in runs:
        runs[k].sort(key=lambda p: p["frame"])
    logger.info(f"Capture runs: {len(runs):,}", indent=2)

    reversals = []
    rev_counter = 0
    for key, seq in sorted(runs.items(), key=lambda kv: kv[0][1]):  # by reel_start_ts
        n = len(seq)
        if n < 3:
            continue

        step_brg = [None] * n
        for i in range(1, n):
            step_brg[i] = _bearing(seq[i-1]["x"], seq[i-1]["y"], seq[i]["x"], seq[i]["y"])

        def prevailing(i, _seq_n=n, _brg=step_brg):
            lo = max(1, i - prevail_window)
            hi = min(_seq_n, i + prevail_window)
            vals = [_brg[j] for j in range(lo, hi) if _brg[j] is not None]
            if not vals:
                return None
            vals.sort()
            return vals[len(vals) // 2]

        opposing = [False] * n
        for i in range(1, n):
            if step_brg[i] is None:
                continue
            pv = prevailing(i)
            if pv is None:
                continue
            if _ang_diff(step_brg[i], pv) >= oppose_deg:
                opposing[i] = True

        i = 1
        while i < n:
            if not opposing[i]:
                i += 1
                continue
            j = i
            while j < n and opposing[j]:
                j += 1
            span_pts = seq[i-1:j]
            if (j - i) >= min_reversal_frames and len(span_pts) >= 2:
                sx, sy = span_pts[0]["x"], span_pts[0]["y"]
                backtrack = max(math.hypot(p["x"]-sx, p["y"]-sy) for p in span_pts)
                if backtrack >= min_backtrack_ft:
                    rev_counter += 1
                    mps = [p["meas"] for p in span_pts if p["meas"] is not None]
                    n_inc1 = sum(1 for p in span_pts if p["inc"] == 1)
                    n_inc0 = sum(1 for p in span_pts if p["inc"] != 1)
                    reversals.append({
                        "id": rev_counter, "run": key, "pre": span_pts[0]["pre"],
                        "start_frame": span_pts[0]["frame"], "end_frame": span_pts[-1]["frame"],
                        "n_pts": len(span_pts), "n_inc1": n_inc1, "n_inc0": n_inc0,
                        "backtrack_ft": backtrack,
                        "outer_mp": max(mps) if mps else None,
                        "inner_mp": min(mps) if mps else None,
                        "oids": [p["oid"] for p in span_pts],
                        "live_oids": [p["oid"] for p in span_pts if p["inc"] == 1],
                        "start_oid": span_pts[0]["oid"], "end_oid": span_pts[-1]["oid"],
                    })
            i = j

    # Report.
    live = [r for r in reversals if r["n_inc1"] > 0]
    handled = [r for r in reversals if r["n_inc1"] == 0]
    show = live if only_report_live else reversals

    logger.info("=" * 56, indent=1)
    logger.info(f"DETECTED REVERSALS: {len(reversals)} (min backtrack {min_backtrack_ft:.0f} units)", indent=1)
    logger.info(f"LIVE (>=1 include=1): {len(live)}   HANDLED (all include=0): {len(handled)}", indent=1)

    by_pre = defaultdict(int)
    for r in show:
        by_pre[r["pre"]] += 1
        omp = f"{r['outer_mp']:.4f}" if r["outer_mp"] is not None else "—"
        imp = f"{r['inner_mp']:.4f}" if r["inner_mp"] is not None else "—"
        tag = "LIVE" if r["n_inc1"] > 0 else "handled"
        logger.info(
            f"#{r['id']} [{tag}] {r['pre']} reel {r['run'][0]} @ {r['run'][1]} "
            f"frames {r['start_frame']}..{r['end_frame']} "
            f"({r['n_pts']} pts: {r['n_inc1']} inc1, {r['n_inc0']} inc0) "
            f"backtrack {r['backtrack_ft']:.1f}  overlap MP ~ [{imp}, {omp}]",
            indent=2,
        )
        if r["n_inc1"] > 0:
            logger.warning(f"LIVE include=1 OIDs needing resolution: {r['live_oids']}", indent=2)

    logger.info("LIVE reversals by subdivision:", indent=1)
    for pre in sorted(by_pre):
        logger.info(f"{pre}: {by_pre[pre]}", indent=2)
    logger.info(
        f"Total include=1 points inside LIVE reversals: {sum(r['n_inc1'] for r in live):,}",
        indent=1,
    )

    # Optionally stamp reversal_id (detection only).
    if write_reversal_id and reversals:
        have = {f.name for f in arcpy.ListFields(fc)}
        if reversal_id_field not in have:
            logger.warning(
                f"Field '{reversal_id_field}' (LONG) not found — add it or leave "
                "write_reversal_id off. Skipping write.",
                indent=1,
            )
        else:
            oid_to_rev = {}
            for r in reversals:
                for oid in r["oids"]:
                    oid_to_rev[oid] = r["id"]
            with arcpy.da.UpdateCursor(fc, [oid_field, reversal_id_field]) as cur:
                for row in cur:
                    row[1] = oid_to_rev.get(row[0])  # None clears non-reversal pts
                    cur.updateRow(row)
            logger.info(f"Wrote {reversal_id_field} for {len(oid_to_rev):,} points.", indent=1)

    logger.success("Reversal detection complete (no points excluded — report only).", indent=1)
    return {
        "total": len(reversals),
        "live": len(live),
        "handled": len(handled),
        "live_points": sum(r["n_inc1"] for r in live),
        "by_subdivision": dict(by_pre),
    }
