# =============================================================================
# 🗂️ Image Renaming Utility (utils/rename_images.py)
# -----------------------------------------------------------------------------
# Purpose:             Renames and organizes OID images using config-based filename expressions
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-13
#
# Description:
#   Resolves dynamic filename parts from config expressions (e.g., reel, MP, timestamp),
#   renames/copies each image to a flat output folder, updates the OID’s ImagePath and Name
#   fields, and logs all rename operations. Optionally deletes originals after copy.
#
# File Location:        /utils/rename_images.py
# Validator:            /utils/validators/rename_images_validator.py
# Called By:            tools/rename_and_tag_tool.py, tools/process_360_orchestrator.py
# Int. Dependencies:    config_loader, arcpy_utils, expression_utils, check_disk_space, path_utils
# Ext. Dependencies:    arcpy, os, shutil, csv, pathlib, typing
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/rename_images.md
#
# Notes:
#   - Auto-detects duplicate filenames and applies numeric suffix (e.g., _v2)
#   - Ensures output directory is writable and validated before execution
# =============================================================================

# TODO: Make sure this properly handles enhance_images = FALSE

__all__ = ["rename_images"]

import arcpy
import os
import shutil
import csv
from pathlib import Path

from utils.manager.config_manager import ConfigManager
from utils.arcpy_utils import validate_fields_exist
from utils.expression_utils import resolve_expression
from utils.check_disk_space import check_sufficient_disk_space


def rename_images(cfg: ConfigManager, oid_fc: str, delete_originals: bool = False):
    """
    Renames and copies image files for an Oriented Imagery Dataset according to configuration rules.

    All renamed images are placed in a flat directory specified by the configuration, and the `Name` and `ImagePath`
    attributes in the dataset are updated in-place. Optionally deletes original images after copying. A CSV log of
    rename operations is generated. Returns a list of dictionaries with updated image metadata.

    Args:
        cfg:
        oid_fc: Path to the feature class containing image records.
        delete_originals: If True, deletes original image files after copying.

    Returns:
        A list of dictionaries representing updated image records, including OID, new path, filename, QC flag,
        coordinates, and resolved metadata.
    """
    logger = cfg.get_logger()
    cfg.validate(tool="rename_images")

    fmt = cfg.get("image_output.filename_settings.format", "{Name}.jpg")
    parts = cfg.get("image_output.filename_settings.parts", {})

    required_fields = ["OID@", "ImagePath", "Name", "QCFlag", "X", "Y"]
    for expr in parts.values():
        if isinstance(expr, str) and expr.startswith("field."):
            field_name = expr.split(".", 1)[1].split(".", 1)[0]
            if field_name not in required_fields:
                required_fields.append(field_name)

    validate_fields_exist(oid_fc, [f for f in required_fields if f != "OID@"])
    fields = list(dict.fromkeys(required_fields))

    check_sufficient_disk_space(oid_fc, cfg)

    output_dir = cfg.paths.renamed
    output_dir.mkdir(parents=True, exist_ok=True)

    # Verify write permissions
    try:
        test_file = output_dir / ".permission_test"
        test_file.touch()
        test_file.unlink()
    except (PermissionError, OSError) as e:
        logger.error(f"Output directory is not writable: {output_dir}. Error: {e}", error_type=PermissionError)

    logger.debug(f"Writing renamed images to: {output_dir}")

    # Prepare CSV log
    rename_log_path = cfg.paths.get_log_file_path("rename_log", cfg)
    logger.debug(f"Writing rename log to: {rename_log_path}")
    log_fields = ["OID", "OriginalPath", "OriginalName", "NewPath", "NewName"]
    log_rows = []

    updated_images = []

    with arcpy.da.UpdateCursor(oid_fc, fields) as cursor:
        for row in cursor:
            row_dict = dict(zip(fields, row))
            oid = row_dict["OID@"]
            old_path = Path(row_dict["ImagePath"])

            if not old_path.is_file():
                logger.warning(f"Image path missing or invalid for OID {oid}: {old_path}")
                continue

            try:
                resolved = {
                    key: resolve_expression(expr, cfg, row=row_dict)
                    for key, expr in parts.items()
                }

                filename = fmt.format(**resolved)
                new_path = output_dir / filename

                base, ext = os.path.splitext(filename)
                counter = 1
                while new_path.is_file():
                    filename = f"{base}_v{counter}{ext}"
                    new_path = output_dir / filename
                    counter += 1

                try:
                    shutil.copy2(old_path, new_path)
                    if delete_originals:
                        os.remove(old_path)
                except (PermissionError, OSError) as e:
                    logger.warning(f"Failed to copy/delete file for OID {oid}: {e}")
                    continue

                row_dict["ImagePath"] = str(new_path)
                row_dict["Name"] = filename
                cursor.updateRow([row_dict.get(f) for f in fields])

                updated_images.append({
                    "oid": oid,
                    "path": str(new_path),
                    "filename": filename,
                    "qcflag": row_dict.get("QCFlag"),
                    "x": row_dict.get("X"),
                    "y": row_dict.get("Y"),
                    "metadata": resolved
                })

                # Add to CSV log
                log_rows.append({
                    "OID": oid,
                    "OriginalPath": str(old_path),
                    "OriginalName": old_path.name,
                    "NewPath": str(new_path),
                    "NewName": filename
                })

                logger.debug(f"✅ Renamed OID {oid} ➜ {filename}")
            except KeyError as ke:
                logger.warning(f"Failed to resolve filename part for OID {oid}: Missing key {ke}")
                continue
            except ValueError as ve:
                logger.warning(f"Failed to resolve filename part for OID {oid}: Invalid value: {ve}")
                continue
            except Exception as e:
                logger.warning(f"Failed to rename/copy for OID {oid}: {e}")
                continue

    # Write rename log CSV
    try:
        with open(rename_log_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=log_fields)
            writer.writeheader()
            writer.writerows(log_rows)
        logger.info(f"📝 Rename log saved to: {rename_log_path}")
    except PermissionError as e:
        logger.warning(f"Failed to write rename log: {e}")

    logger.info(f"✅ {len(updated_images)} image(s) renamed and attributes updated.")
    return updated_images
