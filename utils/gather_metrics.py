# =============================================================================
# 📊 OID Metrics & Summary Generator (utils/gather_metrics.py)
# -----------------------------------------------------------------------------
# Purpose:             Collects and summarizes key statistics from an Oriented Imagery Dataset
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Extracts MP numbers, acquisition timestamps, and frame data by reel from an OID feature class.
#   Produces summary stats such as image count, MP ranges, and per-reel frame/acquisition metadata.
#   Designed to support HTML/PDF report generation and workflow diagnostics.
#
# File Location:        /utils/gather_metrics.py
# Called By:            reporting utilities, orchestrator, report generator
# Int. Dependencies:    None
# Ext. Dependencies:    arcpy, typing, collections
#
# Documentation:
#   See: docs/UTILITIES.md
#
# Notes:
#   - Gracefully handles empty or incomplete datasets
#   - Rounds MP values to 3 decimal places and formats timestamps as strings
# =============================================================================

import arcpy
from collections import defaultdict
from typing import Tuple, Dict, Any, List


def collect_oid_metrics(oid_fc_path: str) -> Dict[str, Any]:
    """
    Extracts MP numbers, acquisition dates, and per-reel frame data from an Oriented Imagery Dataset feature class.
    
    Args:
        oid_fc_path: Path to the OID feature class.
    
    Returns:
        A dictionary containing:
            - mp_values: List of MP_Num values found in the dataset.
            - acq_dates: List of AcquisitionDate values.
            - reel_data: Dictionary keyed by reel identifier, each with lists of frames and acquisition dates.
    """
    result = {
        "mp_values": [],
        "acq_dates": [],
        "reel_data": defaultdict(lambda: {"frames": [], "dates": []})
    }

    fields = ["MP_Num", "CameraHeight", "AcquisitionDate", "Reel", "Frame"]

    with arcpy.da.SearchCursor(oid_fc_path, fields) as cursor:
        for mp, _height, acq, reel, frame in cursor:
            if mp is not None:
                result["mp_values"].append(mp)
            if acq:
                result["acq_dates"].append(acq)
            if reel and frame is not None:
                result["reel_data"][reel]["frames"].append(int(frame))
                if acq:
                    result["reel_data"][reel]["dates"].append(acq)

    return result


def summarize_oid_metrics(metrics: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Computes overall and per-reel summary statistics from OID feature class metrics.
    
    Args:
        metrics: Dictionary containing lists of MP numbers, acquisition dates, and per-reel data as produced by
        `collect_oid_metrics`.
    
    Returns:
        A tuple containing:
            - A dictionary with overall statistics: total image count, minimum and maximum MP values (rounded to three
            decimals), MP delta, and acquisition start and end dates as strings (or "—" if unavailable).
            - A list of dictionaries, each summarizing a reel with zero-padded reel ID, image count, and acquisition
            date range.
    """

    mp_vals = metrics.get("mp_values", [])
    dates = metrics.get("acq_dates", [])
    reel_map = metrics.get("reel_data", {})

    summary = {
        "total_images": len(mp_vals),
        "mp_min": round(min(mp_vals), 3) if mp_vals else "—",
        "mp_max": round(max(mp_vals), 3) if mp_vals else "—",
        "mp_delta": round(max(mp_vals) - min(mp_vals), 3) if mp_vals else "—",
        "acq_start": min(dates).strftime("%Y-%m-%d %H:%M:%S") if dates else "—",
        "acq_end": max(dates).strftime("%Y-%m-%d %H:%M:%S") if dates else "—"
    }

    reels = []
    for reel_id, data in sorted(reel_map.items()):
        padded = str(reel_id).zfill(4)
        max_frame = max(data["frames"]) if data["frames"] else -1
        min_date = min(data["dates"]).strftime("%Y-%m-%d %H:%M:%S") if data["dates"] else "—"
        max_date = max(data["dates"]).strftime("%Y-%m-%d %H:%M:%S") if data["dates"] else "—"
        reels.append({
            "reel": padded,
            "image_count": max_frame + 1,
            "acq_start": min_date,
            "acq_end": max_date
        })

    return summary, reels
