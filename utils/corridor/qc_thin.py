# =============================================================================
# 🔬 Corridor Stage 5c — Deep QC of Thinning (utils/corridor/qc_thin.py)
# -----------------------------------------------------------------------------
# Purpose:             Read-only: validate and characterize the kept set (flag=1).
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Sections:
#   1. Reconciliation       — script vs table kept counts.
#   2. Spacing violations   — kept pairs closer than threshold (≈0 within a run;
#                             reel seams explained).
#   3. Spacing distribution — percentiles per partition + overall + histogram.
#   4. Stretched gaps       — kept pairs notably ABOVE threshold.
#   5. Coverage holes       — kept steps over a big-gap threshold.
#   6. Dual-track overlap   — both tracks retained through overlaps (generic).
#   7. Reduction funnel     — captured -> include=1 -> kept.
#
#   Threshold is WKID-aware (matches the thinning target). Set threshold_m and
#   wkid to the values used by the Thin stage.
#
# Ported from corridor thinning work/scripts/qc_thin.py — logic preserved,
# dual-track section generalized beyond the original hard-coded ('H','4').
# Int. Dependencies:    utils/corridor/units
# Ext. Dependencies:    arcpy, math, collections
# =============================================================================

from __future__ import annotations

import math
from collections import defaultdict

import arcpy

from utils.corridor.units import (
    compile_identity_regex,
    parse_run_frame,
    resolve_logger,
    threshold_to_data_units,
    tkey,
)

__all__ = ["qc_thin"]


def _pctl(sorted_vals, q):
    if not sorted_vals:
        return float("nan")
    i = min(len(sorted_vals) - 1, int(len(sorted_vals) * q))
    return sorted_vals[i]


def qc_thin(
    fc: str,
    track_field: str = "track",
    flag_field: str = "flag_5m",
    sub_order_field: str = "sub_order",
    meas_field: str = "mp_meas",
    pre_field: str = "mp_pre",
    include_field: str = "include",
    include_value=1,
    threshold_m: float = 5.0,
    wkid: int | None = None,
    meters_per_unit_override: float | None = None,
    tol: float = 0.05,
    stretch_factor: float = 1.25,
    biggap_ft: float = 100.0,
    filename_regex: str | None = None,
    cfg=None,
    messages=None,
) -> dict:
    """Read-only deep QC of the thinned (flag=1) set. Returns a summary dict."""
    logger = resolve_logger(cfg, messages)
    oid_field = arcpy.Describe(fc).OIDFieldName
    regex = compile_identity_regex(filename_regex)
    threshold_units = threshold_to_data_units(threshold_m, wkid, meters_per_unit_override)
    where_keep = f"{include_field} = {include_value} AND {flag_field} = 1"

    parts = defaultdict(list)
    with arcpy.da.SearchCursor(
        fc,
        [oid_field, pre_field, track_field, sub_order_field, "SHAPE@X", "SHAPE@Y", meas_field, "Name"],
        where_clause=where_keep,
    ) as cur:
        for oid, pre, track, so, x, y, meas, name in cur:
            run, _ = parse_run_frame(name, regex)
            parts[(pre, tkey(track))].append({"oid": oid, "so": so, "x": x, "y": y, "meas": meas, "run": run})
    for p in parts:
        parts[p].sort(key=lambda r: (r["so"] if r["so"] is not None else 1e18))
    total_keep = sum(len(v) for v in parts.values())

    steps = defaultdict(list)
    for p in sorted(parts):
        seq = parts[p]
        for i in range(1, len(seq)):
            a, b = seq[i-1], seq[i]
            steps[p].append({
                "d": math.hypot(b["x"]-a["x"], b["y"]-a["y"]),
                "so1": a["so"], "so2": b["so"], "oid1": a["oid"], "oid2": b["oid"],
                "reel_boundary": a["run"] != b["run"], "mp1": a["meas"], "mp2": b["meas"],
            })
    all_d = sorted(s["d"] for p in steps for s in steps[p])

    # 1. Reconciliation
    lyr = arcpy.management.MakeFeatureLayer(fc, "corridor_qc_k", where_keep)
    tbl_keep = int(arcpy.management.GetCount(lyr)[0])
    arcpy.management.Delete("corridor_qc_k")
    logger.info(
        f"1. RECONCILIATION: script kept {total_keep:,} vs table flag=1 {tbl_keep:,} -> "
        f"{'PASS' if total_keep == tbl_keep else 'MISMATCH'}",
        indent=1,
    )

    # 2. Spacing violations
    viol = [(p, s) for p in steps for s in steps[p] if s["d"] < threshold_units - tol]
    vb = sum(1 for _, s in viol if s["reel_boundary"])
    logger.info(
        f"2. SPACING VIOLATIONS (< {threshold_units:.2f} units): {len(viol)} "
        f"(reel-boundary {vb}, WITHIN-RUN {len(viol)-vb})",
        indent=1,
    )
    for p, s in sorted(viol, key=lambda x: x[1]["d"])[:15]:
        tag = "reel-boundary" if s["reel_boundary"] else "WITHIN-RUN"
        logger.info(f"{p[0]}/{p[1]}: {s['d']:.2f} so {s['so1']}->{s['so2']} [{tag}]", indent=2)

    # 3. Spacing distribution
    logger.info("3. SPACING DISTRIBUTION (kept consecutive step, units)", indent=1)
    for p in sorted(parts):
        ds = sorted(s["d"] for s in steps[p])
        if not ds:
            continue
        logger.info(
            f"{p[0]}/{p[1]} n={len(ds)+1} min={ds[0]:.1f} p05={_pctl(ds,0.05):.1f} "
            f"p50={_pctl(ds,0.50):.1f} p95={_pctl(ds,0.95):.1f} max={ds[-1]:.1f}",
            indent=2,
        )
    if all_d:
        logger.info(
            f"OVERALL n={len(all_d)+1} min={all_d[0]:.1f} p05={_pctl(all_d,0.05):.1f} "
            f"p50={_pctl(all_d,0.50):.1f} p95={_pctl(all_d,0.95):.1f} max={all_d[-1]:.1f}",
            indent=2,
        )

    # 4. Stretched gaps
    stretched = [(p, s) for p in steps for s in steps[p]
                 if threshold_units * stretch_factor <= s["d"] < biggap_ft]
    sb = sum(1 for _, s in stretched if s["reel_boundary"])
    logger.info(
        f"4. STRETCHED GAPS ({threshold_units*stretch_factor:.1f}–{biggap_ft:.0f}): "
        f"{len(stretched)} (reel-boundary {sb}, within-run {len(stretched)-sb})",
        indent=1,
    )

    # 5. Coverage holes
    holes = [(p, s) for p in steps for s in steps[p] if s["d"] >= biggap_ft]
    logger.info(f"5. COVERAGE HOLES (> {biggap_ft:.0f}): {len(holes)}", indent=1)
    for p, s in sorted(holes, key=lambda x: x[1]["d"], reverse=True):
        tag = "reel-boundary" if s["reel_boundary"] else "WITHIN-RUN (hole?)"
        logger.info(f"{p[0]}/{p[1]}: {s['d']:,.0f} so {s['so1']}->{s['so2']} [{tag}]", indent=2)

    # 6. Dual-track overlap (generic: any mp_pre with _main + a numeric track)
    logger.info("6. DUAL-TRACK OVERLAP", indent=1)
    overlaps = 0
    pres_with_track = defaultdict(set)
    for (pre, tk) in parts:
        pres_with_track[pre].add(tk)
    for pre, tks in sorted(pres_with_track.items()):
        numeric_tracks = [tk for tk in tks if tk != "_main"]
        if not numeric_tracks or "_main" not in tks:
            continue
        for tk in numeric_tracks:
            track_pts = parts[(pre, tk)]
            mvals = [r["meas"] for r in track_pts if r["meas"] is not None]
            if not mvals:
                continue
            lo, hi = min(mvals), max(mvals)
            main_zone = [r for r in parts[(pre, "_main")]
                         if r["meas"] is not None and lo <= r["meas"] <= hi]
            overlaps += 1
            logger.info(
                f"{pre}: track {tk} kept {len(track_pts)} over MP [{lo:.4f},{hi:.4f}]; "
                f"main kept in zone {len(main_zone)} -> "
                f"{'both retained' if track_pts and main_zone else 'CHECK'}",
                indent=2,
            )
    if overlaps == 0:
        logger.info("no dual-track partitions present", indent=2)

    # 7. Reduction funnel
    inc_lyr = arcpy.management.MakeFeatureLayer(fc, "corridor_qc_i", f"{include_field} = {include_value}")
    inc1 = int(arcpy.management.GetCount(inc_lyr)[0])
    arcpy.management.Delete("corridor_qc_i")
    allpts = int(arcpy.management.GetCount(fc)[0])
    logger.info(
        f"7. REDUCTION: captured {allpts:,} -> include=1 {inc1:,} "
        f"({inc1/allpts*100 if allpts else 0:.1f}%) -> kept {total_keep:,} "
        f"({total_keep/inc1*100 if inc1 else 0:.1f}% of include=1, "
        f"{total_keep/allpts*100 if allpts else 0:.1f}% of captured)",
        indent=1,
    )

    within_run_viol = len(viol) - vb
    logger.success(
        f"QC Thinning complete (read-only): kept {total_keep:,}, "
        f"within-run spacing violations {within_run_viol} (target 0), "
        f"coverage holes {len(holes)}.",
        indent=1,
    )
    return {
        "kept": total_keep,
        "reconciliation_pass": total_keep == tbl_keep,
        "spacing_violations": len(viol),
        "within_run_violations": within_run_viol,
        "stretched_gaps": len(stretched),
        "coverage_holes": len(holes),
        "include_1": inc1,
        "captured": allpts,
    }
