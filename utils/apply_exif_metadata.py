# =============================================================================
# 🏷️ EXIF Metadata Tagging Logic (utils/apply_exif_metadata.py)
# -----------------------------------------------------------------------------
# Purpose:             Applies EXIF metadata to images using ExifTool, based on dynamic config expressions
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Resolves tag expressions from config for each image in an OID feature class, then generates
#   a batch ExifTool command file. Supports tagging standard and GPS outlier images in-place.
#   Logs resolved metadata and captures success/failure outcomes.
#
# File Location:        /utils/apply_exif_metadata.py
# Called By:            tools/rename_and_tag_tool.py
# Int. Dependencies:    config_loader, arcpy_utils, path_utils, expression_utils, executable_utils
# Ext. Dependencies:    arcpy, os, subprocess, typing
# External Tools:       ExifTool (must be installed and available via PATH or config path)
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/rename_and_tag.md
#
# Notes:
#   - Supports both string and list-based tag expressions
#   - Uses ExifTool's -@ arg file interface for efficient batch execution
# =============================================================================

__all__ = ["update_metadata_from_config"]

import os
import subprocess
import arcpy
from typing import Optional
from utils.config_loader import resolve_config
from utils.arcpy_utils import validate_fields_exist, log_message
from utils.path_utils import get_log_path
from utils.expression_utils import resolve_expression
from utils.executable_utils import is_executable_available


def update_metadata_from_config(
        oid_fc,
        config: Optional[dict] = None,
        config_file: Optional[str] = None,
        messages=None):
    """
    Updates image metadata for images referenced in a feature class using configuration rules.

    Applies metadata tags to images by evaluating expressions defined in a configuration file or dictionary. Tagging
    is performed in batch using ExifTool, with tag values resolved from feature class fields. Handles GPS metadata
    updates for images flagged as outliers and logs all operations and errors.
    """
    config = resolve_config(
        config=config,
        config_file=config_file,
        oid_fc_path=oid_fc,
        messages=messages,
        tool_name="apply_exif_metadata")

    tags = config.get("image_output", {}).get("metadata_tags", {})
    if not tags:
        log_message("No metadata_tags defined in config.yaml.", messages, level="error", error_type=ValueError,
                    config=config)

    # Extract required fields
    required_fields = set()
    for v in tags.values():
        if isinstance(v, str):
            required_fields.update([part.split('.')[1] for part in v.split() if part.startswith("field.")])
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    required_fields.update([part.split('.')[1] for part in item.split() if part.startswith("field.")])

    # Always require GPS and QC fields for GPS updates
    required_fields.update(["X", "Y", "QCFlag"])

    validate_fields_exist(oid_fc, list(required_fields))

    args_file = get_log_path("exiftool_args", config)
    log_file = get_log_path("exiftool_logs", config)
    lines = []
    log_entries = []

    with arcpy.da.SearchCursor(oid_fc, ["OID@", "ImagePath", "QCFlag", "X", "Y"] + list(required_fields)) as cursor:
        for row in cursor:
            row_dict = dict(zip(["OID@", "ImagePath", "QCFlag", "X", "Y"] + list(required_fields), row))
            path = row_dict["ImagePath"]
            if not os.path.exists(path):
                log_message(f"⚠️ Image path does not exist: {path}", messages, level="warning", config=config)
                continue

            resolved_tags = {}
            # --- Standard tags from config ---
            for tag_name, expression in tags.items():
                try:
                    if isinstance(expression, str):
                        value = resolve_expression(expression, row=row_dict, config=config)
                        resolved_tags[tag_name] = value
                        lines.append(f"-{tag_name}={value}")
                    elif isinstance(expression, list):
                        keywords = []
                        for item in expression:
                            value = resolve_expression(item, row=row_dict, config=config)
                            keywords.append(value)
                        resolved_tags[tag_name] = ";".join(keywords)
                        lines.append(f"-{tag_name}={';'.join(keywords)}")
                except Exception as e:
                    log_message(f"⚠️ Failed to resolve tag {tag_name}: {e}", messages, level="warning", config=config)

            # --- GPS Updates (only if flagged) ---
            if row_dict["QCFlag"] == "GPS_OUTLIER":
                lat, lon = row_dict["Y"], row_dict["X"]
                lat_ref = "North" if lat >= 0 else "South"
                lon_ref = "East" if lon >= 0 else "West"
                lines.extend([
                    f"-GPSLatitude={abs(lat)}",
                    f"-GPSLatitudeRef={lat_ref}",
                    f"-GPSLongitude={abs(lon)}",
                    f"-GPSLongitudeRef={lon_ref}"
                ])

            lines.extend([
                "-overwrite_original_in_place",
                path.replace('\\', '/'),
                "-execute",
                ""
            ])
            log_entries.append(f"✅ Tagged OID {row_dict['OID@']} → {os.path.basename(path)}")

    # Write ExifTool batch args
    with open(args_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("\n".join(log_entries))

    # Get exe_path from config (you already validated it earlier)
    exe_path = config["executables"]["exiftool"]["exe_path"]

    # Validate runtime availability
    if not is_executable_available(exe_path, ["-ver"]):
        log_message(f"❌ ExifTool not found or not working at: {exe_path}", messages, level="error",
                    error_type=RuntimeError, config=config)

    # Run ExifTool
    try:
        subprocess.run([exe_path, "-@", args_file], check=True)
        log_message("✅ Metadata tagging completed.", messages, config=config)
    except subprocess.CalledProcessError as e:
        log_message(f"❌ ExifTool failed: {e}", messages, level="error", error_type=RuntimeError, config=config)
