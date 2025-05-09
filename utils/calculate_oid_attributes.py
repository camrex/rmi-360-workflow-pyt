# =============================================================================
# 🧮 OID Attribute Enrichment Logic (utils/calculate_oid_attributes.py)
# -----------------------------------------------------------------------------
# Purpose:             Enriches Oriented Imagery Dataset features with camera orientation, reel, and Z attributes
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Applies default and derived values to fields in an OID feature class, including
#   orientation, SRS, reel, and frame info. Incorporates validation against a field
#   registry and adjusts Z-values using configured camera offsets. Validates field-of-view
#   defaults and integrates reel_info.json metadata if available.
#
# File Location:        /utils/calculate_oid_attributes.py
# Called By:            tools/add_images_to_oid_tool.py
# Int. Dependencies:    config_loader, arcpy_utils, expression_utils
# Ext. Dependencies:    arcpy, os, json, re, typing
#
# Documentation:
#   See: docs/TOOL_GUIDES.md and docs/tools/add_images_to_oid.md
#
# Notes:
#   - Integrates reel_info.json if present to supplement reel assignment
#   - Skips processing if OID is empty or missing required fields
# =============================================================================

__all__ = ["enrich_oid_attributes"]

import arcpy
import re
import os
import json
from typing import Optional, Tuple, List
from utils.config_loader import get_camera_offset_values, resolve_config
from utils.arcpy_utils import log_message
from utils.expression_utils import load_field_registry


def check_oid_fov_defaults(oid_fc_path: str, registry: dict, messages=None):
    """
    Checks that HFOV and VFOV values in the OID feature class match expected defaults.
    
    Logs an error for each row where the HorizontalFieldOfView or VerticalFieldOfView
    differs from the default values specified in the registry.
    """
    expected_hfov = registry.get("HFOV", {}).get("oid_default")
    expected_vfov = registry.get("VFOV", {}).get("oid_default")

    with arcpy.da.SearchCursor(oid_fc_path, ["HorizontalFieldOfView", "VerticalFieldOfView"]) as cursor:
        for i, row in enumerate(cursor):
            hfov, vfov = row
            if hfov != expected_hfov or vfov != expected_vfov:
                log_message(f"Row {i}: HFOV or VFOV does not match expected values from registry.\n"
                            f"Expected HFOV={expected_hfov}, VFOV={expected_vfov}, but got HFOV={hfov}, VFOV={vfov}",
                            messages, level="error", error_type=ValueError)


def load_reel_from_info_file(image_path: str, messages=None) -> Tuple[Optional[str], Optional[str]]:
    """
    Attempts to find and read a reel_info.json file near the specified image path.
    
    Searches the parent and grandparent directories of the image for a reel_info.json file.
    If exactly one file is found, returns its "reel" value and the file path. If multiple files
    are found or an error occurs, logs a warning and returns (None, None).
    
    Args:
        image_path: Full path to the image file.
        messages: Optional ArcGIS messaging interface (e.g., from script tools) for logging.
    
    Returns:
        A tuple containing the reel value and the path to the reel_info.json file, or (None, None)
        if not found or if an error occurs.
    """
    reel_info_paths: List[str] = []

    try:
        parent_dir = os.path.dirname(os.path.dirname(image_path))  # e.g., panos/
        grandparent_dir = os.path.dirname(parent_dir)              # e.g., reel_0001/
        for candidate in [parent_dir, grandparent_dir]:
            test_path = os.path.join(candidate, "reel_info.json")
            if os.path.isfile(test_path):
                reel_info_paths.append(test_path)

        if len(reel_info_paths) == 1:
            path = reel_info_paths[0]
            with open(path, "r") as f:
                reel_data = json.load(f)
                return reel_data.get("reel"), path

        elif len(reel_info_paths) > 1:
            msg = f"⚠️ Multiple reel_info.json files found near image: {image_path}\nFiles:\n" + "\n".join(reel_info_paths)
            if messages:
                messages.addWarningMessage(msg)
            else:
                print(msg)
            return None, None

    except Exception as e:
        msg = f"❌ Failed to load reel_info.json near: {image_path}\n{e}"
        if messages:
            messages.addWarningMessage(msg)
        else:
            print(msg)

    return None, None


def extract_reel_from_path(image_path: str) -> Optional[str]:
    """
    Extracts a 4-digit reel number from the grandparent directory of an image path.
    
    The function searches for a folder name matching the pattern 'reel_XXXX' (where XXXX is a 4-digit number) two
    levels above the provided image file. Returns the reel number if found, otherwise returns None.
    """

    reel_folder = os.path.basename(os.path.dirname(os.path.dirname(image_path)))
    match = re.search(r"reel_(\d{4})", reel_folder, re.IGNORECASE)
    return match.group(1) if match else None


def extract_frame_from_filename(image_path: str) -> Optional[str]:
    """
    Extracts a 6-digit frame number from the image filename.
    
    The function searches for a pattern like '_000234.jpg' at the end of the filename and returns the frame number if
    found. Returns None if the pattern is not present or an error occurs.
    """

    image_file = os.path.basename(image_path)
    match = re.search(r"_(\d{6})\.jpg$", image_file, re.IGNORECASE)
    return match.group(1) if match else None


def enrich_oid_attributes(
        oid_fc_path: str,
        config: Optional[dict] = None,
        config_file: Optional[str] = None,
        messages=None,
        adjust_z: bool = True):
    """
    Enriches an Oriented Imagery Dataset with derived and default attribute values.

    This function updates the specified OID feature class by setting default values for camera parameters, adjusting Z
    coordinates by camera offset if requested, and populating orientation, spatial reference, reel, and frame fields.
    Reel and frame numbers are extracted from image paths or associated metadata files. Field of view values are
    validated against expected defaults. The function is typically used after adding images to the dataset.
    """
    config = resolve_config(
        config=config,
        config_file=config_file,
        oid_fc_path=oid_fc_path,
        messages=messages,
        tool_name="calculate_oid_attributes"
    )

    z_offset, camera_height = get_camera_offset_values(config)
    sr_cfg = config.get("spatial_ref", {})
    h_wkid = sr_cfg.get("gcs_horizontal_wkid", 4326)
    v_wkid = sr_cfg.get("vcs_vertical_wkid", 5703)

    registry_path = config["oid_schema_template"]["esri_default"]["field_registry"]
    registry = load_field_registry(registry_path, config=config)

    pitch = registry.get("CameraPitch", {}).get("oid_default", 90)
    roll = registry.get("CameraRoll", {}).get("oid_default", 0)
    near = registry.get("NearDistance", {}).get("oid_default", 2)
    far = registry.get("FarDistance", {}).get("oid_default", 50)

    # Start with geometry and ESRI standard fields
    esri_cfg = config.get("oid_schema_template", {}).get("esri_default", {})
    fields = ["OID@", "SHAPE@X", "SHAPE@Y", "SHAPE@Z"]
    for _key, field in registry.items():
        if field.get("category") == "standard" or (
            field.get("category") == "not_applicable" and esri_cfg.get("not_applicable", False)
        ):
            fields.append(field["name"])

    # Add just the mosaic fields
    schema_cfg = config.get("oid_schema_template", {})
    for fdef in schema_cfg.get("mosaic_fields", {}).values():
        fields.append(fdef["name"])

    # Deduplicate in case of overlap
    fields = list(dict.fromkeys(fields))
    field_to_index = {name: i for i, name in enumerate(fields)}

    check_oid_fov_defaults(oid_fc_path, registry, messages)

    # Load reel_info.json once per dataset
    first_image_path = None
    with arcpy.da.SearchCursor(oid_fc_path, ["ImagePath"], where_clause="ImagePath IS NOT NULL") as cursor:
        for row in cursor:
            first_image_path = row[0].strip()
            break

    # Handle empty dataset scenario
    if not first_image_path:
        log_message("❌ No images found in the OID dataset. Skipping OID attribute calculation.", messages,
                    level="error", config=config)
        return  # Short-circuit the function if no images are found

    reel_from_info, reel_info_path_used = load_reel_from_info_file(first_image_path or "", messages)

    if reel_info_path_used:
        log_message(f"📄 Using reel_info.json from: {reel_info_path_used}", messages, config=config)

    count = 0
    with arcpy.da.UpdateCursor(oid_fc_path, fields) as cursor:
        for row in cursor:
            x = row[field_to_index["SHAPE@X"]]
            y = row[field_to_index["SHAPE@Y"]]
            z = row[field_to_index["SHAPE@Z"]]
            adjusted_z = z + z_offset if adjust_z else z
            heading = row[field_to_index["CameraHeading"]]

            orientation = f"1|{h_wkid}|{v_wkid}|{x:.6f}|{y:.6f}|{adjusted_z:.3f}|{heading:.1f}|{pitch:.1f}|{roll:.1f}"

            # Parse frame number from filename
            image_path = row[field_to_index["ImagePath"]].strip()

            reel = extract_reel_from_path(image_path) or reel_from_info
            frame = extract_frame_from_filename(image_path)

            row[field_to_index["CameraPitch"]] = pitch
            row[field_to_index["CameraRoll"]] = roll
            row[field_to_index["NearDistance"]] = near
            row[field_to_index["FarDistance"]] = far
            row[field_to_index["X"]] = x
            row[field_to_index["Y"]] = y
            row[field_to_index["Z"]] = adjusted_z
            row[field_to_index["SHAPE@Z"]] = adjusted_z
            row[field_to_index["SRS"]] = f"{h_wkid},{v_wkid}"
            row[field_to_index["CameraHeight"]] = camera_height
            row[field_to_index["CameraOrientation"]] = orientation
            if "Reel" in field_to_index:
                row[field_to_index["Reel"]] = reel
            if "Frame" in field_to_index:
                row[field_to_index["Frame"]] = frame

            cursor.updateRow(row)
            count += 1

    log_message(f"✅ OID enrichment complete. Updated {count} image(s) with orientation, Z, and mosaic fields.",
                messages, config=config)
