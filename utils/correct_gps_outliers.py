__all__ = ["correct_gps_outliers"]

import arcpy
from typing import Optional
from utils.config_loader import resolve_config
from utils.arcpy_utils import log_message


def correct_gps_outliers(
        oid_fc,
        config: Optional[dict] = None,
        config_file: Optional[str] = None,
        messages=None):
    """
    Identifies and corrects GPS outlier points in a feature class by interpolating their positions.

    For each contiguous sequence of points flagged as GPS outliers (`QCFlag = 'GPS_OUTLIER'`), this function
    interpolates X and Y coordinates evenly between the nearest valid points before and after the sequence. The
    geometry, X, Y, and CameraOrientation fields of the outlier points are updated in place. Configuration for spatial
    reference is loaded from the provided dictionary or file, with defaults applied if not specified. Logs the number
    of corrected points or a warning if none are found.
    """
    config = resolve_config(
        config=config,
        config_file=config_file,
        oid_fc_path=oid_fc,
        messages=messages,
        tool_name="correct_gps_outliers"
    )

    sr_cfg = config.get("spatial_ref", {})
    default_h_wkid = sr_cfg.get("gcs_horizontal_wkid", 4326)
    default_v_wkid = sr_cfg.get("vcs_vertical_wkid", 5703)

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

    # Apply updates
    with arcpy.da.UpdateCursor(oid_fc, fields) as cursor:
        for row in cursor:
            oid = row[0]
            if oid in corrected_oids:
                for r in rows:
                    if r["oid"] == oid:
                        row[2] = r["xy"]
                        row[3] = r["orientation"]
                        row[7] = r["z"]  # unchanged
                        row[8] = r["x"]
                        row[9] = r["y"]
                        break
                cursor.updateRow(row)

    if not corrected_oids:
        log_message("⚠️ No GPS outliers found or corrected.", messages, config=config)
    else:
        log_message(f"✅ Corrected {len(corrected_oids)} GPS outlier point(s).", messages, config=config)
