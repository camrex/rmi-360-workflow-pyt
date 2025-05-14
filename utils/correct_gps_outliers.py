# =============================================================================
# 📍 GPS Outlier Correction Logic (utils/correct_gps_outliers.py)
# -----------------------------------------------------------------------------
# Purpose:             Interpolates and corrects GPS outlier points in an OID feature class
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-13
#
# Description:
#   Identifies sequences of features flagged as GPS outliers (`QCFlag = GPS_OUTLIER`) in an
#   Oriented Imagery Dataset and interpolates new XY coordinates between valid anchor points.
#   Updates geometry and CameraOrientation fields in-place using ArcPy cursors.
#
# File Location:        /utils/correct_gps_outliers.py
# Validator:            /utils/validators/correct_gps_outliers_validator.py
# Called By:            tools/smooth_gps_noise_tool.py
# Int. Dependencies:    config_loader, arcpy_utils
# Ext. Dependencies:    arcpy, typing
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/smooth_gps_noise.md
#
# Notes:
#   - Skips outliers at the beginning or end of the dataset (no anchors available)
#   - Orientation string is recomputed using default WKIDs from config
# =============================================================================

__all__ = ["correct_gps_outliers"]

import arcpy

from utils.manager.config_manager import ConfigManager


def correct_gps_outliers(cfg: ConfigManager, oid_fc: str) -> None:
    """
    Identifies and corrects GPS outlier points in a feature class by interpolating their positions.

    For each contiguous sequence of points flagged as GPS outliers (`QCFlag = 'GPS_OUTLIER'`), this function
    interpolates X and Y coordinates evenly between the nearest valid points before and after the sequence. The
    geometry, X, Y, and CameraOrientation fields of the outlier points are updated in place. Configuration for spatial
    reference is loaded from the provided dictionary or file, with defaults applied if not specified. Logs the number
    of corrected points or a warning if none are found.

    Args:
        cfg (ConfigManager): Configuration manager with validated config.
        oid_fc (str): Path to the OID feature class.
    """
    logger = cfg.get_logger()
    cfg.validate(tool="correct_gps_outliers")

    default_h_wkid = cfg.get("spatial_ref.gcs_horizontal_wkid", 4326)
    default_v_wkid = cfg.get("spatial_ref.vcs_vertical_wkid", 5703)

    # Load relevant data into memory
    fields = ["OID@", "QCFlag", "SHAPE@XY", "CameraOrientation", "CameraHeading",
              "CameraPitch", "CameraRoll", "Z", "X", "Y"]

    rows = []
    with arcpy.da.SearchCursor(oid_fc, fields) as cursor:
        for row in cursor:
            rows.append({
                "oid": row[0],
                "qcflag": row[1],
                "xy": row[2],
                "orientation": row[3],
                "heading": row[4],
                "pitch": row[5],
                "roll": row[6],
                "z": row[7],
                "x": row[8],
                "y": row[9],
            })

    # Identify sequences of outliers
    corrected_oids = set()
    i = 0
    while i < len(rows):
        if rows[i]["qcflag"] != "GPS_OUTLIER":
            i += 1
            continue

        # Start of outlier sequence
        start_idx = i
        while i < len(rows) and rows[i]["qcflag"] == "GPS_OUTLIER":
            i += 1
        end_idx = i - 1

        # Find anchor points
        if start_idx == 0 or end_idx == len(rows) - 1:
            continue

        p0 = rows[start_idx - 1]
        p1 = rows[end_idx + 1]
        num = end_idx - start_idx + 2  # num of segments between points

        dx = (p1["x"] - p0["x"]) / num
        dy = (p1["y"] - p0["y"]) / num

        for j, idx in enumerate(range(start_idx, end_idx + 1), start=1):
            new_x = p0["x"] + dx * j
            new_y = p0["y"] + dy * j
            z = rows[idx]["z"]
            heading = rows[idx]["heading"]
            pitch = rows[idx]["pitch"]
            roll = rows[idx]["roll"]
            orientation = f"1|{default_h_wkid}|{default_v_wkid}|{new_x:.6f}|{new_y:.6f}|{z:.3f}|{heading:.1f}|{pitch:.1f}|{roll:.1f}"

            rows[idx].update({
                "xy": (new_x, new_y),
                "x": new_x,
                "y": new_y,
                "orientation": orientation,
            })
            corrected_oids.add(rows[idx]["oid"])

    if not corrected_oids:
        logger.info("No GPS outliers found or corrected.")
        return

    # Apply updates
    with cfg.get_progressor(total=len(corrected_oids), label="Correcting GPS outliers") as progressor:
        with arcpy.da.UpdateCursor(oid_fc, fields) as cursor:
            for row in cursor:
                oid = row[0]
                if oid in corrected_oids:
                    r = next((r for r in rows if r["oid"] == oid), None)
                    if r:
                        row[2] = r["xy"]
                        row[3] = r["orientation"]
                        row[7] = r["z"]  # unchanged
                        row[8] = r["x"]
                        row[9] = r["y"]
                        cursor.updateRow(row)
                        progressor.update(1)

    logger.info(f"✅ Corrected {len(corrected_oids)} GPS outlier point(s).")
