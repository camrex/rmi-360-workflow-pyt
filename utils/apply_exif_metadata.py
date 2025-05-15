# =============================================================================
# 🏷️ EXIF Metadata Tagging Logic (utils/apply_exif_metadata.py)
# -----------------------------------------------------------------------------
# Purpose:             Applies EXIF metadata to images using ExifTool, based on dynamic config expressions
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-13
# Last Updated:        2025-05-15
#
# Description:
#   Resolves tag expressions from config for each image in an OID feature class, then generates
#   a batch ExifTool command file. Supports tagging standard and GPS outlier images in-place.
#   Logs resolved metadata and captures success/failure outcomes.
#
# File Location:        /utils/apply_exif_metadata.py
# Validator:            /utils/validators/apply_exif_metadata_validator.py
# Called By:            tools/rename_and_tag_tool.py
# Int. Dependencies:    utils/manager/config_manager, utils/shared/arcpy_utils, utils/shared/expression_utils
# Ext. Dependencies:    arcpy, os, subprocess
# External Tools:       ExifTool (must be installed and available via PATH or config path)
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/rename_and_tag.md
#   (Ensure these docs are current; update if needed.)
#
# Notes:
#   - Supports both string and list-based tag expressions
#   - Uses ExifTool's -@ arg file interface for efficient batch execution
#   - Logs all resolved metadata and batch execution results
# =============================================================================

__all__ = ["update_metadata_from_config"]

import os
import subprocess
import arcpy

from utils.manager.config_manager import ConfigManager
from utils.shared.expression_utils import resolve_expression
from utils.shared.arcpy_utils import validate_fields_exist


def _extract_required_fields(tags):
    required_fields = set()
    for v in tags.values():
        if isinstance(v, str):
            required_fields.update([part.split('.')[1] for part in v.split() if part.startswith("field.")])
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    required_fields.update([part.split('.')[1] for part in item.split() if part.startswith("field.")])
    required_fields.update(["X", "Y", "QCFlag"])
    return required_fields


def _resolve_tags(cfg, tags, row_dict):
    resolved_tags = {}
    for tag_name, expression in tags.items():
        try:
            if isinstance(expression, str):
                value = resolve_expression(expression, cfg, row=row_dict)
                resolved_tags[tag_name] = value
            elif isinstance(expression, list):
                keywords = []
                for item in expression:
                    value = resolve_expression(item, cfg, row=row_dict)
                    keywords.append(value)
                resolved_tags[tag_name] = ";".join(keywords)
        except Exception as e:
            print(f"Failed to resolve tag {tag_name}: {e}")
    return resolved_tags


def _write_exiftool_args(cfg, tags, rows):
    args_file = cfg.paths.get_log_file_path("exiftool_args", cfg)
    log_file = cfg.paths.get_log_file_path("exiftool_logs", cfg)
    lines = []
    log_entries = []
    for row in rows:
        row_dict = dict(zip(["OID@", "ImagePath", "QCFlag", "X", "Y"] + list(tags.keys()), row))
        path = row_dict["ImagePath"]
        if not os.path.exists(path):
            print(f"Image path does not exist: {path}")
            continue

        resolved_tags = _resolve_tags(cfg, tags, row_dict)
        for tag_name, value in resolved_tags.items():
            lines.append(f"-{tag_name}={value}")

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

    with open(args_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("\n".join(log_entries))


def _run_exiftool(cfg, args_file):
    logger = cfg.get_logger()
    exe_path = cfg.paths.exiftool_exe
    if not cfg.paths.check_exiftool_available():
        logger.error(f"ExifTool not found or not working at: {exe_path}", error_type=RuntimeError)
    try:
        subprocess.run([exe_path, "-@", args_file], check=True)
        logger.info("✅ Metadata tagging completed.")
    except subprocess.CalledProcessError as e:
        logger.error(f"ExifTool failed: {e}", error_type=RuntimeError)


def update_metadata_from_config(cfg: ConfigManager, oid_fc: str):
    """
    Updates image metadata for images referenced in a feature class using configuration rules.

    Applies metadata tags to images by evaluating expressions defined in a configuration file or dictionary. Tagging
    is performed in batch using ExifTool, with tag values resolved from feature class fields. Handles GPS metadata
    updates for images flagged as outliers and logs all operations and errors.
    """
    logger = cfg.get_logger()
    cfg.validate(tool="apply_exif_metadata")

    tags = cfg.get("image_output.metadata_tags", {})
    if not tags:
        logger.error("No metadata_tags defined in config.yaml.", error_type=ValueError)

    required_fields = _extract_required_fields(tags)
    validate_fields_exist(oid_fc, list(required_fields))

    with arcpy.da.SearchCursor(oid_fc, ["OID@", "ImagePath", "QCFlag", "X", "Y"] + list(required_fields)) as cursor:
        rows = [row for row in cursor]

    _write_exiftool_args(cfg, tags, rows)
    _run_exiftool(cfg, cfg.paths.get_log_file_path("exiftool_args", cfg))
