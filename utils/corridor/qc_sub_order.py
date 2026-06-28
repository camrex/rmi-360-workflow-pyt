# =============================================================================
# 🔎 Corridor Stage 5a — QC Sequence (utils/corridor/qc_sub_order.py)
# -----------------------------------------------------------------------------
# Purpose:             Read-only validation of sub_order sequencing, partition-aware
#                      (mp_pre + track). Nothing is modified.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Checks:
#   1. Contiguity     : sub_order = 1..N per partition, no gaps, no dupes.
#   2. Reconciliation : partition counts sum to the include=1 total.
#   3. Step distance  : planar units between consecutive sub_order points.
#   4. Large jumps    : steps over a threshold (gap vs error).
#   5. Cluster order  : intra-cluster reversals (tied-meas points vs local dir).
#                       NOTE: this heuristic FALSE-FIRES at reel boundaries where
#                       two runs meet close with a heading change; confirm
#                       sub_order + mp_meas both ascend = correct order.
#   6. NULL audit     : include=1 points missing sub_order or mp_meas.
#
# Ported from corridor thinning work/scripts/qc_sub_order.py — logic preserved.
# Int. Dependencies:    utils/corridor/units
# Ext. Dependencies:    arcpy, math, collections
# =============================================================================

from __future__ import annotations

import math
from collections import defaultdict

import arcpy

from utils.corridor.units import resolve_logger, tkey

__all__ = ["qc_sub_order"]


def qc_sub_order(
    fc: str,
    track_field: str = "track",
    meas_field: str = "mp_meas",
    sub_order_field: str = "sub_order",
    pre_field: str = "mp_pre",
    include_field: str = "include",
    include_value=1,
    jump_threshold_ft: float = 100.0,
    cluster_colocated_ft: float = 0.5,
    top_n: int = 15,
    cfg=None,
    messages=None,
) -> dict:
    """Read-only QC of the sub_order sequence. Returns a summary dict."""
    logger = resolve_logger(cfg, messages)
    oid_field = arcpy.Describe(fc).OIDFieldName
    where = f"{include_field} = {include_value}"

    rows = []
    with arcpy.da.SearchCursor(
        fc,
        [oid_field, pre_field, track_field, meas_field, sub_order_field, "SHAPE@X", "SHAPE@Y", "Name"],
        where_clause=where,
    ) as cur:
        for oid, pre, track, meas, so, x, y, name in cur:
            rows.append({"oid": oid, "pre": pre, "tk": tkey(track), "meas": meas,
                         "so": so, "x": x, "y": y, "name": name})
    total = len(rows)
    logger.info(f"Loaded {total:,} {where} points.", indent=2)

    parts = defaultdict(list)
    for r in rows:
        parts[(r["pre"], r["tk"])].append(r)
    for p in parts:
        parts[p].sort(key=lambda r: (r["so"] if r["so"] is not None else 1e18))

    # 1. Contiguity
    logger.info("1. CONTIGUITY (sub_order = 1..N per partition)", indent=1)
    contig_ok = True
    for p in sorted(parts):
        vals = [r["so"] for r in parts[p] if r["so"] is not None]
        n_null = sum(1 for r in parts[p] if r["so"] is None)
        vals_sorted = sorted(vals)
        ok = (vals_sorted == list(range(1, len(vals) + 1))) and n_null == 0
        dupes = len(vals) - len(set(vals))
        contig_ok = contig_ok and ok
        logger.info(
            f"[{'OK ' if ok else 'FLAG'}] {p[0]}/{p[1]}: n={len(parts[p]):,}, "
            f"range={vals_sorted[0] if vals_sorted else '-'}.."
            f"{vals_sorted[-1] if vals_sorted else '-'}, dupes={dupes}, null_so={n_null}",
            indent=2,
        )
    logger.info(f"Contiguity overall: {'PASS' if contig_ok else 'FLAGGED'}", indent=1)

    # 2. Reconciliation
    part_sum = sum(len(v) for v in parts.values())
    logger.info(
        f"2. RECONCILIATION: partition sum {part_sum:,} vs {where} total {total:,} -> "
        f"{'PASS' if part_sum == total else 'FLAG'}",
        indent=1,
    )

    # 3 & 4. Step distance + large jumps
    logger.info("3. STEP DISTANCE (planar units between consecutive sub_order points)", indent=1)
    all_jumps = []
    for p in sorted(parts):
        seq = parts[p]
        steps = []
        for i in range(1, len(seq)):
            a, b = seq[i-1], seq[i]
            d = math.hypot(b["x"]-a["x"], b["y"]-a["y"])
            steps.append(d)
            all_jumps.append((d, p[0], p[1], a["so"], b["so"], a["oid"], b["oid"]))
        if not steps:
            continue
        ss = sorted(steps)
        nn = len(ss)
        logger.info(
            f"{p[0]}/{p[1]}: n={nn+1:,} min={ss[0]:.1f} p50={ss[nn//2]:.1f} "
            f"p95={ss[int(nn*0.95)]:.1f} max={ss[-1]:.1f}",
            indent=2,
        )

    big = sorted([j for j in all_jumps if j[0] > jump_threshold_ft], key=lambda j: j[0], reverse=True)
    logger.info(f"4. LARGE JUMPS (> {jump_threshold_ft:.0f}): {len(big)}", indent=1)
    for j in big[:top_n]:
        d, pre, tk, so1, so2, oid1, oid2 = j
        logger.info(f"{pre}/{tk}: sub_order {so1}->{so2}  {d:,.0f}  OID {oid1}->{oid2}", indent=2)

    # 5. Cluster order
    reversals = 0
    for p in sorted(parts):
        seq = parts[p]
        for i in range(1, len(seq) - 1):
            a, b, c = seq[i-1], seq[i], seq[i+1]
            if math.hypot(b["x"]-a["x"], b["y"]-a["y"]) < cluster_colocated_ft:
                vx, vy = b["x"]-a["x"], b["y"]-a["y"]
                fx, fy = c["x"]-b["x"], c["y"]-b["y"]
                if (vx*fx + vy*fy) < 0:
                    reversals += 1
    logger.info(
        f"5. CLUSTER ORDER: possible intra-cluster reversals = {reversals} "
        f"{'(PASS)' if reversals == 0 else '(REVIEW; may false-fire at reel seams)'}",
        indent=1,
    )

    # 6. NULL audit
    null_so = [r for r in rows if r["so"] is None]
    null_meas = [r for r in rows if r["meas"] is None]
    logger.info(
        f"6. NULL AUDIT: include=1 NULL sub_order = {len(null_so):,}, NULL mp_meas = {len(null_meas):,}",
        indent=1,
    )
    if null_meas:
        logger.warning(
            "NULL mp_meas on include=1 points means beyond Locate radius — review "
            "whether they should be include=0 or need a centerline/radius fix.",
            indent=2,
        )

    logger.success(
        f"QC Sequence: contiguity {'PASS' if contig_ok else 'FLAGGED'}, "
        f"reconciliation {'PASS' if part_sum == total else 'FLAGGED'}, "
        f"large jumps {len(big)}, cluster reversals {reversals}, "
        f"null sub_order {len(null_so)}, null mp_meas {len(null_meas)}.",
        indent=1,
    )
    return {
        "contiguity_pass": contig_ok,
        "reconciliation_pass": part_sum == total,
        "large_jumps": len(big),
        "cluster_reversals": reversals,
        "null_sub_order": len(null_so),
        "null_mp_meas": len(null_meas),
    }
