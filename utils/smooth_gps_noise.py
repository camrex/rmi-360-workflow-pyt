# =============================================================================
# 🛰️ GPS Noise Smoothing Logic (utils/smooth_gps_noise.py)
# -----------------------------------------------------------------------------
# Purpose:             Detects and flags suspect GPS points in an OID using spatial + geometric checks
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Analyzes GPS tracks in an OID feature class to identify potential outlier points based on
#   spatial deviation, angle, spacing, and proximity to a centerline (if provided). Flags points
#   by updating a QCFlag field and optionally logs debug metrics to CSV for inspection.
#
# File Location:        /utils/smooth_gps_noise.py
# Called By:            tools/smooth_gps_noise_tool.py, orchestrator
# Int. Dependencies:    config_loader, arcpy_utils, path_utils
# Ext. Dependencies:    arcpy, csv, math, typing
#
# Documentation:
#   See: docs/TOOL_GUIDES.md and docs/tools/smooth_gps_noise.md
#
# Notes:
#   - Flags GPS outliers using configurable multi-criteria scoring
#   - Optionally integrates centerline route distance checks if provided
# =============================================================================

__all__ = ["smooth_gps_noise"]

import arcpy
import csv
from typing import Optional
from utils.config_loader import resolve_config
from utils.arcpy_utils import log_message
from utils.path_utils import get_log_path


def haversine(x1, y1, x2, y2):
    """
    Calculates the great-circle distance in meters between two latitude/longitude points.
    
    Args:
        x1: Longitude of the first point in decimal degrees.
        y1: Latitude of the first point in decimal degrees.
        x2: Longitude of the second point in decimal degrees.
        y2: Latitude of the second point in decimal degrees.
    
    Returns:
        The distance between the two points in meters.
    """
    from math import radians, sin, cos, sqrt, atan2
    r = 6371000  # Earth radius in meters
    phi1, phi2 = radians(y1), radians(y2)
    d_phi = radians(y2 - y1)
    d_lambda = radians(x2 - x1)
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return r * 2 * atan2(sqrt(a), sqrt(1 - a))


def angle_between(p1, p2, p3):
    """Calculate the angle at p2 formed by three points."""
    from math import degrees, atan2
    dx1, dy1 = p1[0] - p2[0], p1[1] - p2[1]
    dx2, dy2 = p3[0] - p2[0], p3[1] - p2[1]
    angle1 = atan2(dy1, dx1)
    angle2 = atan2(dy2, dx2)
    return abs(degrees(angle2 - angle1)) % 360


def smooth_gps_noise(
        oid_fc,
        centerline_fc=None,
        config: Optional[dict] = None,
        config_file: Optional[str] = None,
        messages=None
):
    """
    Detects and flags outlier GPS points in a feature class based on spatial and geometric criteria.

    Analyzes each GPS point for deviation from the local path, angle with neighbors, step distance, and (optionally)
    distance from a provided centerline route. Flags points as outliers if they meet or exceed a configurable threshold
    of outlier criteria. Optionally outputs a debug CSV summarizing metrics and reasons for outlier status, and updates
    a "QCFlag" field in the input feature class for flagged points.

    Args:
        oid_fc: Path to the input feature class containing GPS points.
        centerline_fc: Optional path to a centerline feature class for route-based deviation checks.
        config: Optional dictionary of configuration parameters to override defaults.
        config_file: Optional path to a configuration file.
        messages: Optional messaging or logging object for status updates.
    """
    config = resolve_config(
        config=config,
        config_file=config_file,
        oid_fc_path=oid_fc,
        messages=messages,
        tool_name="smooth_gps_noise")

    smoothing = config.get("gps_smoothing", {})
    spacing = config.get("capture_spacing_meters", 5.0)
    deviation_thresh = smoothing.get("deviation_threshold_m", 0.5)
    angle_bounds = smoothing.get("angle_bounds_deg", [175, 185])
    proximity_range = smoothing.get("proximity_check_range_m", 0.75)
    window = smoothing.get("smoothing_window", 2)
    max_route_dev = smoothing.get("max_route_dist_deviation_m", 0.5)
    outlier_threshold = smoothing.get("outlier_reason_threshold", 2)
    log_csv_path = get_log_path("gps_smooth_debug", config)

    # Extract OID points
    points = []
    with arcpy.da.SearchCursor(oid_fc, ["OID@", "SHAPE@", "AcquisitionDate"]) as cursor:
        for row in cursor:
            oid, shape, ts = row
            point_geom = shape.centroid
            points.append({
                "oid": oid,
                "x": point_geom.X,
                "y": point_geom.Y,
                "z": point_geom.Z if point_geom.Z is not None else 0,
                "shape": point_geom,
                "ts": ts
            })

    # Prepare routes if provided
    routes = []
    route_sr = None
    if centerline_fc:
        with arcpy.da.SearchCursor(centerline_fc, ["SHAPE@"]) as cursor:
            for row in cursor:
                route = row[0]
                routes.append(route)
        if routes:
            route_sr = routes[0].spatialReference

    # First pass: compute metrics
    for i in range(len(points)):
        p = points[i]
        prev_pt = points[i - window] if i >= window else None
        next_pt = points[i + window] if i + window < len(points) else None

        # Deviation from midpoint
        if prev_pt and next_pt:
            mid_x = (prev_pt["x"] + next_pt["x"]) / 2
            mid_y = (prev_pt["y"] + next_pt["y"]) / 2
            p["deviation"] = haversine(p["x"], p["y"], mid_x, mid_y)
            p["angle"] = angle_between((prev_pt["x"], prev_pt["y"]), (p["x"], p["y"]), (next_pt["x"], next_pt["y"]))
        else:
            p["deviation"] = 0
            p["angle"] = 180

        # Step distance from previous point
        p["step"] = haversine(points[i - 1]["x"], points[i - 1]["y"], p["x"], p["y"]) if i > 0 else 0

        # Distance from centerline (requires projection)
        p["route_dist"] = 0
        if centerline_fc and route_sr:
            try:
                pt_geom = arcpy.PointGeometry(arcpy.Point(p["x"], p["y"]), arcpy.SpatialReference(4326))
                pt_projected = pt_geom.projectAs(route_sr)
                min_dist = float("inf")
                for route in routes:
                    dist = route.queryPointAndDistance(pt_projected.centroid, use_percentage=False)[2]
                    if dist < min_dist:
                        min_dist = dist
                p["route_dist"] = min_dist
            except Exception as e:
                log_message(f"Projection failed for OID {p['oid']}: {e}", messages, level="warning", config=config)
                p["route_dist"] = 0

    # Compute route distance deviation from neighbors
    for i in range(1, len(points) - 1):
        prev_dist = points[i - 1]["route_dist"]
        next_dist = points[i + 1]["route_dist"]
        avg = (prev_dist + next_dist) / 2
        points[i]["route_dev"] = abs(points[i]["route_dist"] - avg)

    csv_rows = []
    outlier_oids = set()

    for i, p in enumerate(points):
        # Initial exclusion: first point can never be flagged
        if i == 0:
            p["is_outlier"] = False
        else:
            reasons = {
                "Deviation": p["deviation"] > deviation_thresh,
                "Angle": not (angle_bounds[0] <= p["angle"] <= angle_bounds[1]),
                "Step": p["step"] < spacing - proximity_range or p["step"] > spacing + proximity_range,
                "RouteDev": p.get("route_dev", 0) > max_route_dev
            }
            count = sum(reasons.values())
            p["is_outlier"] = count >= outlier_threshold
            p.update({f"Reason_{k}": v for k, v in reasons.items()})
            p["Reason_Count"] = count

        if p["is_outlier"]:
            outlier_oids.add(p["oid"])

        # Append to CSV only if at least one reason is True
        if p.get("Reason_Count", 0) > 0:
            reason_keys = [k for k in ["Deviation", "Angle", "Step", "RouteDev"] if p.get(f"Reason_{k}")]
            reason_str = ", ".join(reason_keys) if reason_keys else ""

            csv_rows.append({
                "OID": p["oid"],
                "Deviation": round(p["deviation"], 3),
                "Angle": round(p["angle"], 2),
                "Step": round(p["step"], 3),
                "RouteDist": round(p["route_dist"], 3),
                "RouteDistDev": round(p.get("route_dev", 0), 3),
                "Reason_Deviation": p.get("Reason_Deviation", False),
                "Reason_Angle": p.get("Reason_Angle", False),
                "Reason_Step": p.get("Reason_Step", False),
                "Reason_RouteDev": p.get("Reason_RouteDev", False),
                "Reason_Count": p.get("Reason_Count", 0),
                "Is_Outlier": p["is_outlier"],
                "QCReason": reason_str
            })

    # Propagate flags for sequences (surrounded by outliers)
    for i in range(1, len(points) - 1):
        if not points[i]["is_outlier"] and points[i - 1]["is_outlier"] and points[i + 1]["is_outlier"]:
            points[i]["is_outlier"] = True
            outlier_oids.add(points[i]["oid"])
            for row in csv_rows:
                if row["OID"] == points[i]["oid"]:
                    row["Is_Outlier"] = True
                    break

    # Attempt to write debug CSV (safe fallback)
    try:
        with open(log_csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_rows[0].keys())
            writer.writeheader()
            writer.writerows(csv_rows)
    except Exception as e:
        log_message(f"Could not write debug CSV to {log_csv_path}: {e}", messages, level="warning", config=config)

    # Add QCFlag
    existing = [f.name for f in arcpy.ListFields(oid_fc)]
    if "QCFlag" not in existing:
        arcpy.AddField_management(oid_fc, "QCFlag", "TEXT", field_length=50)
    with arcpy.da.UpdateCursor(oid_fc, ["OID@", "QCFlag"]) as cursor:
        for oid, val in cursor:
            if oid in outlier_oids:
                cursor.updateRow((oid, "GPS_OUTLIER"))

    log_message(f"Detected {len(outlier_oids)} suspect GPS points.", messages, config=config)
