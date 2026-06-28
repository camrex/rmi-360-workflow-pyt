# =============================================================================
# 🛰️ Corridor Stage 0 — Create Panorama Points (utils/corridor/create_points.py)
# -----------------------------------------------------------------------------
# Purpose:             Build the panorama point feature class the corridor pipeline
#                      consumes: GeoTagged Photos -> Points, parse reel /
#                      reel_start_ts / frame from the filename, and add the empty
#                      editorial fields (include / mp_pre / track) for the user.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Description:
#   This is the one NEW stage (not in the validated scripts). It removes the manual
#   "photos -> points" step so the only manual upstream work left is editorial:
#   setting include (1/0), mp_pre (subdivision), and track (parallel-track tag),
#   plus supplying per-subdivision M-enabled route centerlines.
#
#   Reel identity (reel, reel_start_ts) and frame are parsed from the filename
#   (PIPELINE.md: the filename embeds the reel START timestamp, the reliable
#   cross-reel ordering key — reel number alone is NOT reliable).
#
# File Location:        /utils/corridor/create_points.py
# Int. Dependencies:    utils/corridor/units
# Ext. Dependencies:    arcpy
# =============================================================================

from __future__ import annotations

import arcpy

from utils.corridor.units import compile_identity_regex, parse_reel_frame, resolve_logger

__all__ = ["create_points"]


def create_points(
    photo_folder: str,
    out_fc: str,
    include_non_geotagged: bool = False,
    add_as_attachments: bool = False,
    name_field: str = "Name",
    path_field: str = "Path",
    reel_field: str = "reel",
    reel_start_field: str = "reel_start_ts",
    frame_field: str = "frame",
    pre_field: str = "mp_pre",
    track_field: str = "track",
    include_field: str = "include",
    add_editorial_fields: bool = True,
    filename_regex: str | None = None,
    cfg=None,
    messages=None,
) -> dict:
    """Create the panorama point FC from geotagged photos and parse identity fields.

    Args:
        photo_folder: Folder of geotagged panoramas (searched recursively by ArcGIS).
        out_fc: Output point feature class path.
        add_editorial_fields: Add empty include/mp_pre/track for the user to populate.

    Returns a stats dict (created count, parsed count).
    """
    logger = resolve_logger(cfg, messages)
    arcpy.env.overwriteOutput = True
    regex = compile_identity_regex(filename_regex)

    invalid_tbl = (out_fc + "_invalid") if not add_as_attachments else None

    logger.info(f"GeoTagged Photos -> Points from '{photo_folder}'", indent=1)
    arcpy.management.GeoTaggedPhotosToPoints(
        Input_Folder=photo_folder,
        Output_Feature_Class=out_fc,
        Invalid_Photos_Table=invalid_tbl,
        Include_Non_GeoTagged_Photos="ALL_PHOTOS" if include_non_geotagged else "ONLY_GEOTAGGED",
        Add_Photos_As_Attachments="ADD_ATTACHMENTS" if add_as_attachments else "NO_ATTACHMENTS",
    )

    created = int(arcpy.management.GetCount(out_fc)[0])
    logger.info(f"Created {created:,} points.", indent=2)

    # Ensure identity + editorial fields exist.
    have = {f.name for f in arcpy.ListFields(out_fc)}
    to_add = [
        (reel_field, "TEXT", 8),
        (reel_start_field, "TEXT", 20),
        (frame_field, "TEXT", 10),
    ]
    if add_editorial_fields:
        to_add += [(include_field, "SHORT", None), (pre_field, "TEXT", 16), (track_field, "SHORT", None)]
    for fname, ftype, flen in to_add:
        if fname not in have:
            if ftype == "TEXT" and flen:
                arcpy.management.AddField(out_fc, fname, ftype, field_length=flen)
            else:
                arcpy.management.AddField(out_fc, fname, ftype)

    # Determine the source of the filename. GeoTaggedPhotosToPoints writes Name
    # and Path; prefer Name, fall back to Path basename.
    fields = [f.name for f in arcpy.ListFields(out_fc)]
    src = name_field if name_field in fields else (path_field if path_field in fields else None)
    if src is None:
        logger.warning(
            f"Neither '{name_field}' nor '{path_field}' present; cannot parse reel/frame. "
            "Populate identity fields manually.",
            indent=1,
        )
        return {"created": created, "parsed": 0}

    parsed = unmatched = 0
    with arcpy.da.UpdateCursor(out_fc, [src, reel_field, reel_start_field, frame_field]) as cur:
        for row in cur:
            val = row[0]
            if src == path_field and val:
                val = str(val).replace("\\", "/").split("/")[-1]
            res = parse_reel_frame(val, regex)
            if res is None:
                unmatched += 1
                cur.updateRow(row)
                continue
            reel, rts, frame = res
            row[1] = reel
            row[2] = rts
            row[3] = str(frame).zfill(len(regex.search(val).group(3))) if regex.search(val) else str(frame)
            cur.updateRow(row)
            parsed += 1

    logger.info(f"Parsed reel/reel_start_ts/frame for {parsed:,} points ({unmatched:,} unmatched).", indent=2)
    if add_editorial_fields:
        logger.info(
            f"Empty editorial fields added: {include_field}, {pre_field}, {track_field}. "
            "Populate include/mp_pre/track before Calculate Mileposts.",
            indent=2,
        )
    logger.success("Create Panorama Points complete.", indent=1)
    return {"created": created, "parsed": parsed, "unmatched": unmatched}
