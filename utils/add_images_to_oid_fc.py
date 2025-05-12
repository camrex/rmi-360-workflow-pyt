# =============================================================================
# 🧭 OID Image Import Logic (utils/add_images_to_oid_fc.py)
# -----------------------------------------------------------------------------
# Purpose:             Adds geotagged 360° images to an ArcGIS Oriented Imagery Dataset (OID)
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Scans and validates a folder of enhanced/final images, checks for reel_info
#   collisions, and appends entries to a target Oriented Imagery Dataset using
#   ArcPy’s Oriented Imagery tools. Includes schema validation and recursive support.
#
# File Location:        /utils/add_images_to_oid_fc.py
# Called By:            tools/add_images_to_oid_tool.py
# Int. Dependencies:    config_loader, arcpy_utils, expression_utils
# Ext. Dependencies:    arcpy, os, pathlib, typing
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/add_images_to_oid.md
#
# Notes:
#   - Supports recursive reel folder discovery and duplicate prevention
# =============================================================================

__all__ = ["add_images_to_oid"]

import arcpy
import os
from pathlib import Path
from typing import Optional
from utils.arcpy_utils import log_message
from utils.config_loader import resolve_config
from utils.expression_utils import load_field_registry


def warn_if_multiple_reel_info(image_folder, messages=None):
    """
    Checks for multiple 'reel_info.json' files within the specified image folder and its subfolders.
    
    If more than one 'reel_info.json' file is found, logs an error message listing all detected file paths.
    """
    reel_info_paths = []
    # Use pathlib to walk the directory and look for 'reel_info.json' files
    for json_file in Path(image_folder).rglob("reel_info.json"):  # rglob allows recursive search
        reel_info_paths.append(str(json_file))

    if len(reel_info_paths) > 1:
        log_message(f"⚠️ Multiple reel_info.json files detected in image folder '{image_folder}':\n"
                    + "\n".join(reel_info_paths), messages, level="error", error_type=RuntimeError)


def add_images_to_oid(
        project_folder: str,
        oid_fc_path: str,
        config: Optional[dict] = None,
        config_file: Optional[str] = None,
        messages=None):
    """
    Adds images from a project folder to an existing Oriented Imagery Dataset (OID).

    Resolves configuration to determine the image folder, validates the presence of required files and directories,
    and adds all JPEG images (including those in subfolders) to the specified OID feature class using ArcPy. Logs errors
    if the OID, image folder, or images are missing, and integrates with ArcGIS messaging for status updates.
    """
    config = resolve_config(
        config=config,
        config_file=config_file,
        project_folder=project_folder,
        oid_fc_path=oid_fc_path,
        messages=messages,
        tool_name="add_images_to_oid")

    folders = config.get("image_output", {}).get("folders", {})
    image_folder = Path(config["__project_root__"]) / folders.get("parent", "panos") / folders.get("original", "original")

    warn_if_multiple_reel_info(image_folder, messages=messages)

    if not arcpy.Exists(oid_fc_path):
        log_message(f"OID does not exist at path: {oid_fc_path}", messages, level="error", error_type=FileNotFoundError,
                    config=config)

    if not os.path.isdir(image_folder):
        log_message(f"Image folder not found: {image_folder}", messages, level="error", error_type=FileNotFoundError,
                    config=config)

    # Use pathlib to collect all .jpg files recursively
    jpg_files = list(Path(image_folder).rglob("*.jpg"))
    if not jpg_files:
        log_message(f"No .jpg files found in image folder or its subfolders: {image_folder}", messages,
                    level="error", error_type=RuntimeError, config=config)

    registry_path = (
        config.get("oid_schema_template", {})
        .get("esri_default", {})
        .get("field_registry")
    )
    if not registry_path:
        log_message(
            "Missing `oid_schema_template.esri_default.field_registry` in config.",
            messages,
            level="error",
            error_type=KeyError,
            config=config,
        )
    registry = load_field_registry(registry_path, config=config)
    imagery_type = registry.get("OrientedImageryType", {}).get("oid_default", "360")

    log_message(f"Adding images from '{image_folder}' (including subfolders) to OID: {oid_fc_path}", messages,
                config=config)

    arcpy.oi.AddImagesToOrientedImageryDataset(
        in_oriented_imagery_dataset=oid_fc_path,
        imagery_category=imagery_type,
        input_data=[str(image_folder)],
        include_sub_folders="SUBFOLDERS"
    )

    log_message("Images successfully added to OID.", messages, config=config)
