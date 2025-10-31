# =============================================================================
# 📏 Distance-Based Image Spacing Filter (utils/filter_distance_spacing.py)
# -----------------------------------------------------------------------------
# Purpose:             Filters OID features to maintain proper distance spacing between captures
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-10-31
# Last Updated:        2025-10-31
#
# Description:
#   Analyzes GPS tracks in an OID feature class to identify captures that are too close together,
#   typically caused by time-based capture mode instead of distance-based. Flags or removes 
#   images that fall within a minimum spacing threshold, keeping one representative image
#   per distance interval. Particularly useful for correcting field mistakes where camera
#   was inadvertently set to time-based capture mode.
#
# File Location:        /utils/filter_distance_spacing.py
# Validator:            /utils/validators/filter_distance_spacing_validator.py
# Called By:            tools/process_360_orchestrator.py
# Int. Dependencies:    utils/manager/config_manager
# Ext. Dependencies:    arcpy, csv, math, typing
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md
#
# Notes:
#   - Works by reel to maintain proper sequential ordering
#   - Can either flag images for review or remove them entirely
#   - Preserves the first image in each distance interval
# =============================================================================

__all__ = ["filter_distance_spacing"]

import arcpy
import csv
from typing import Optional, Dict, List, Tuple
from math import radians, sin, cos, sqrt, atan2

from utils.manager.config_manager import ConfigManager


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
    r = 6371000  # Earth radius in meters
    phi1, phi2 = radians(y1), radians(y2)
    d_phi = radians(y2 - y1)
    d_lambda = radians(x2 - x1)
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return r * 2 * atan2(sqrt(a), sqrt(1 - a))


def analyze_spacing_by_reel(
        points: List[dict],
        min_spacing_m: float,
        tolerance_m: float,
        logger
) -> Tuple[List[int], Dict]:
    """
    Analyze a reel's points and identify if it was captured in time-based mode.
    
    Time-based captures (0.1s intervals) create very dense clusters of points that are
    extremely close together (typically <1m apart). This function detects such reels
    and filters them to maintain proper distance-based spacing.
    
    Args:
        points: List of point dictionaries with 'oid', 'x', 'y', 'ts', 'reel' keys
        min_spacing_m: Minimum spacing required between images (e.g., 5.0 meters)
        tolerance_m: Tolerance for spacing variation (e.g., 1.0 meters)
        logger: Logger instance for debug messages
        
    Returns:
        Tuple of (oids_to_remove, analysis_stats)
    """
    if len(points) < 5:  # Need reasonable sample size to detect time-based pattern
        return [], {
            "total_points": len(points), 
            "removed_count": 0, 
            "kept_count": len(points),
            "avg_original_spacing": 0,
            "assumed_capture": "insufficient data (<5 points)",
            "capture_mode": "INSUFFICIENT_DATA",
            "is_time_based": False,
            "close_points_ratio": 0,
            "spacing_issues_detected": False
        }
    
    # Calculate all consecutive distances to analyze the spacing pattern
    consecutive_distances = []
    for i in range(1, len(points)):
        prev_pt = points[i-1]
        curr_pt = points[i]
        distance = haversine(prev_pt["x"], prev_pt["y"], curr_pt["x"], curr_pt["y"])
        consecutive_distances.append(distance)
    
    # Analyze the spacing pattern to detect time-based captures
    very_close_threshold = 1.0  # Points closer than 1m are likely time-based
    close_points = [d for d in consecutive_distances if d < very_close_threshold]
    close_points_ratio = len(close_points) / len(consecutive_distances)
    avg_spacing = sum(consecutive_distances) / len(consecutive_distances)
    
    # Determine assumed capture setting based on average spacing
    if avg_spacing < 2.0:
        assumed_capture = "time-based (~0.1s intervals)"
        capture_mode = "TIME"
    elif 3.5 <= avg_spacing <= 6.5:
        assumed_capture = "distance-based (~5m)"
        capture_mode = "DISTANCE_5M"
    elif 8.0 <= avg_spacing <= 12.0:
        assumed_capture = "distance-based (~10m)"
        capture_mode = "DISTANCE_10M"
    elif avg_spacing > 12.0:
        assumed_capture = "distance-based (>10m spacing)"
        capture_mode = "DISTANCE_WIDE"
    else:
        assumed_capture = "mixed/unclear pattern"
        capture_mode = "MIXED"
    
    # Detect time-based reel: high percentage of very close points AND low average spacing
    is_time_based = (close_points_ratio > 0.6 and avg_spacing < 2.0)
    
    logger.info(f"  [ANALYSIS] avg={avg_spacing:.2f}m; {assumed_capture}", indent=3)
    logger.debug(f"     Close points: {close_points_ratio:.1%} under {very_close_threshold}m threshold", indent=3)
    
    oids_to_remove = []
    stats = {
        "total_points": len(points),
        "kept_count": len(points),
        "removed_count": 0,
        "avg_original_spacing": avg_spacing,
        "assumed_capture": assumed_capture,
        "capture_mode": capture_mode,
        "is_time_based": is_time_based,
        "close_points_ratio": close_points_ratio
    }
    
    if not is_time_based:
        logger.info(f"  [OK] {capture_mode}: Preserving reel (good spacing pattern)", indent=3)
        return oids_to_remove, stats
    
    # Time-based reel detected - filter to maintain proper spacing
    logger.warning(f"  [TIME-BASED DETECTED]: Filtering {len(points)} -> target ~{min_spacing_m}m spacing", indent=3)
    
    kept_points = [points[0]]  # Always keep first point
    oids_to_remove = []
    
    for i in range(1, len(points)):
        current_point = points[i]
        last_kept_point = kept_points[-1]
        
        # Calculate distance from the last kept point
        distance = haversine(
            last_kept_point["x"], last_kept_point["y"],
            current_point["x"], current_point["y"]
        )
        
        # Keep if distance meets minimum spacing requirements (accounting for tolerance)
        if distance >= (min_spacing_m - tolerance_m):
            kept_points.append(current_point)
            logger.debug(f"    Keeping OID {current_point['oid']}: {distance:.2f}m from previous", indent=4)
        else:
            oids_to_remove.append(current_point["oid"])
            logger.debug(f"    Removing OID {current_point['oid']}: {distance:.2f}m < {min_spacing_m}m", indent=4)
    
    # Update statistics
    stats.update({
        "kept_count": len(kept_points),
        "removed_count": len(oids_to_remove),
        "spacing_issues_detected": True
    })
    
    return oids_to_remove, stats


def filter_distance_spacing(
    cfg: ConfigManager, 
    oid_fc: str, 
    min_spacing_m: Optional[float] = None,
    tolerance_m: Optional[float] = None,
    action: str = "flag"
) -> None:
    """
    Filters OID features to maintain proper distance spacing between captures.

    Analyzes each reel's GPS track to identify images that are too close together, typically
    caused by time-based capture mode. Can either flag problematic images or remove them entirely.
    Preserves chronological order within each reel and keeps the first image in each distance interval.

    Args:
        cfg: Configuration manager with validated config.
        oid_fc: Path to the input feature class containing GPS points.
        min_spacing_m: Minimum spacing required between images (uses config default if None).
        tolerance_m: Tolerance for spacing variation (uses config default if None).
        action: Action to take - "flag" (add QCFlag) or "remove" (delete features).

    """
    logger = cfg.get_logger()
    cfg.validate(tool="filter_distance_spacing")

    # Get configuration values with defaults
    min_spacing_m = min_spacing_m or cfg.get("distance_spacing.min_spacing_meters", 5.0)
    tolerance_m = tolerance_m or cfg.get("distance_spacing.tolerance_meters", 1.0)
    
    logger.info(f"🚀 Starting distance spacing filter:", indent=1)
    logger.info(f"   Min spacing: {min_spacing_m}m (±{tolerance_m}m tolerance)", indent=2)
    logger.info(f"   Action: {action}", indent=2)

    log_csv_path = cfg.paths.get_log_file_path("distance_spacing_debug", cfg)

    # Extract points by Reel, sorted by timestamp
    points_by_reel: Dict[str, List[dict]] = {}
    with arcpy.da.SearchCursor(oid_fc, ["OID@", "SHAPE@", "AcquisitionDate", "Reel"]) as cursor:
        for oid, shape, ts, reel in cursor:
            if not reel:
                reel = "__UNREEL__"
            pt = shape.centroid
            points_by_reel.setdefault(reel, []).append({
                "oid": oid,
                "x": pt.X,
                "y": pt.Y,
                "ts": ts,
                "reel": reel
            })

    # Sort points by timestamp within each reel
    for pts in points_by_reel.values():
        pts.sort(key=lambda p: p["ts"])

    # Analyze spacing for each reel
    all_oids_to_process = set()
    csv_rows = []
    reel_stats = {}

    logger.info(f"[ANALYZING] {len(points_by_reel)} reel(s) for time-based capture patterns:", indent=1)
    
    time_based_reels = []
    for reel, pts in points_by_reel.items():
        logger.info(f"  🎞 {reel}: {len(pts)} images", indent=2)
        
        oids_to_remove, stats = analyze_spacing_by_reel(pts, min_spacing_m, tolerance_m, logger)
        all_oids_to_process.update(oids_to_remove)
        reel_stats[reel] = stats

        # Log reel summary with detailed analysis
        if stats["is_time_based"]:
            time_based_reels.append(reel)
            logger.warning(f"     [TIME-BASED REEL]: Fixed {stats['removed_count']}/{stats['total_points']} images", indent=2)
            logger.info(f"     Corrected: {stats['avg_original_spacing']:.2f}m -> ~{min_spacing_m}m spacing", indent=2)
            logger.info(f"     Original avg spacing: {stats['avg_original_spacing']:.2f}m", indent=2)
            logger.info(f"     Close points ratio: {stats['close_points_ratio']:.1%}", indent=2)
        elif stats["spacing_issues_detected"]:
            logger.info(f"     Minor spacing adjustments: {stats['removed_count']}/{stats['total_points']} images", indent=2)
        else:
            logger.info(f"     ✓ Good distance-based spacing pattern", indent=2)

        # Add to CSV for debugging (include both removed and analysis summary)
        if stats["is_time_based"] or stats.get("spacing_issues_detected", False):
            # Add summary row for the reel
            csv_rows.append({
                "OID": f"REEL_SUMMARY_{reel}",
                "Reel": reel,
                "X": "N/A",
                "Y": "N/A", 
                "Timestamp": "N/A",
                "Action": "ANALYSIS",
                "Reason": f"{stats['assumed_capture']} - avg {stats['avg_original_spacing']:.2f}m",
                "Capture_Mode": stats["capture_mode"],
                "Avg_Spacing": stats["avg_original_spacing"],
                "Is_Time_Based": stats["is_time_based"]
            })
        
        # Add individual removed points
        for pt in pts:
            if pt["oid"] in oids_to_remove:
                reason = f"{stats['assumed_capture']} - removed (too close)" if stats["is_time_based"] else "Spacing adjustment"
                csv_rows.append({
                    "OID": pt["oid"],
                    "Reel": pt["reel"],
                    "X": round(pt["x"], 6),
                    "Y": round(pt["y"], 6),
                    "Timestamp": pt["ts"],
                    "Action": action.upper(),
                    "Is_Time_Based_Reel": stats["is_time_based"],
                    "Avg_Spacing_m": round(stats["avg_original_spacing"], 2),
                    "Close_Points_Ratio": round(stats["close_points_ratio"], 3),
                    "Reason": reason
                })

    # Write CSV debug log
    if csv_rows:
        try:
            with open(log_csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=csv_rows[0].keys())
                writer.writeheader()
                writer.writerows(csv_rows)
            logger.info(f"📄 Debug CSV written to: {log_csv_path}", indent=1)
        except Exception as e:
            logger.error(f"Could not write debug CSV to {log_csv_path}: {e}", indent=1)

    # Take action on identified images
    if not all_oids_to_process:
        logger.success("[OK] No spacing issues found - all images have proper spacing!", indent=1)
        return

    if action.lower() == "flag":
        # Add QCFlag if missing
        existing_fields = [f.name for f in arcpy.ListFields(oid_fc)]
        if "QCFlag" not in existing_fields:
            arcpy.management.AddField(oid_fc, "QCFlag", "TEXT", field_length=50)

        # Flag problematic images
        with cfg.get_progressor(total=len(all_oids_to_process), label="Flagging spacing issues") as progressor:
            with arcpy.da.UpdateCursor(oid_fc, ["OID@", "QCFlag"]) as cursor:
                for oid, flag in cursor:
                    if oid in all_oids_to_process:
                        cursor.updateRow((oid, "SPACING_TOO_CLOSE"))
                        progressor.update(1)
        
        logger.success(f"[FLAGGED] {len(all_oids_to_process)} image(s) with spacing issues", indent=1)

    elif action.lower() == "remove":
        # Remove problematic images
        oids_str = ",".join(map(str, all_oids_to_process))
        where_clause = f"OBJECTID IN ({oids_str})"
        
        deleted_count = 0
        with cfg.get_progressor(total=len(all_oids_to_process), label="Removing spacing issues") as progressor:
            with arcpy.da.UpdateCursor(oid_fc, ["OID@"], where_clause) as cursor:
                for row in cursor:
                    cursor.deleteRow()
                    deleted_count += 1
                    progressor.update(1)
        
        logger.success(f"[REMOVED] {deleted_count} image(s) with spacing issues", indent=1)

    # Log detailed summary statistics
    total_images = sum(stats["total_points"] for stats in reel_stats.values())
    total_removed = sum(stats["removed_count"] for stats in reel_stats.values())
    distance_reels = [reel for reel, stats in reel_stats.items() if not stats["is_time_based"]]
    
    logger.info(f"[SUMMARY] Distance Filter Results:", indent=1)
    logger.info(f"   Processed: {total_images} images across {len(points_by_reel)} reel(s)", indent=2)
    
    if time_based_reels:
        logger.warning(f"   [TIME-BASED] Corrected: {len(time_based_reels)} reel(s)", indent=2)
        for reel in time_based_reels:
            stats = reel_stats[reel]
            logger.info(f"      • {reel}: {stats['avg_original_spacing']:.2f}m avg → {stats['assumed_capture']}", indent=2)
    
    if distance_reels:
        logger.success(f"   [PRESERVED] Distance-based reels: {len(distance_reels)} reel(s)", indent=2)
        for reel in distance_reels[:3]:  # Show first 3 to avoid clutter
            stats = reel_stats[reel]
            logger.info(f"      • {reel}: {stats['assumed_capture']} ({stats['avg_original_spacing']:.2f}m avg)", indent=2)
        if len(distance_reels) > 3:
            logger.info(f"      • ... and {len(distance_reels) - 3} more", indent=2)
    
    if total_removed > 0:
        logger.info(f"   [TOTAL] {action}: {total_removed}/{total_images} images ({total_removed/total_images*100:.1f}%)", indent=2)