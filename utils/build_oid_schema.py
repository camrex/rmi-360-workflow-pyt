# =============================================================================
# 🧬 OID Schema Template Builder (utils/build_oid_schema.py)
# -----------------------------------------------------------------------------
# Purpose:             Creates a reusable schema template table for Oriented Imagery Datasets (OIDs)
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Builds a geodatabase table to serve as a schema template for OID creation. It integrates
#   fields from both a central field registry and project-level config blocks. Performs backup
#   of existing templates, schema validation, and writes fields using ArcPy management tools.
#
# File Location:        /utils/build_oid_schema.py
# Validator:            /utils/validators/build_oid_schema_validator.py
# Called By:            tools/create_oid_template_tool.py
# Int. Dependencies:    config_loader, expression_utils, arcpy_utils, schema_paths
# Ext. Dependencies:    arcpy, os, datetime, typing
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/create_oid_and_schema.md
#
# Notes:
#   - Respects categories (standard, not_applicable) from registry
#   - Auto-backs up existing templates with timestamp before overwrite
# =============================================================================

__all__ = ["create_oid_schema_template"]

import arcpy
import os
from datetime import datetime
from utils.manager.config_manager import ConfigManager
from utils.expression_utils import load_field_registry


def create_oid_schema_template(cfg: ConfigManager) -> str:
    """
    Creates a schema template table for Oriented Imagery Datasets (OIDs) using configuration and field registry files.

    The function generates a geodatabase table with fields defined by a YAML configuration and a field registry. It
    ensures the output directory and geodatabase exist, backs up any existing schema template, and adds fields from
    both the registry and configuration groups. Returns the full path to the created schema template table.

    Args:
        cfg (ConfigManager): Validated configuration manager.

    Returns:
        The full path to the created schema template table.

    Raises:
        ValueError: If the required field registry path is missing in the configuration.
    """
    logger = cfg.get_logger()
    cfg.validate(tool="build_oid_schema")

    paths = cfg.paths
    esri_cfg = cfg.get("oid_schema_template.esri_default", {})

    if not os.path.exists(paths.templates):
        os.makedirs(paths.templates, exist_ok=True)
    if not arcpy.Exists(paths.oid_schema_gdb):
        arcpy.management.CreateFileGDB(paths.templates, os.path.basename(paths.oid_schema_gdb))

    if arcpy.Exists(paths.oid_schema_template_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{paths.oid_schema_template_name}_{timestamp}"
        arcpy.management.Rename(paths.oid_schema_template_path, backup_name)
        logger.info(f"Existing schema template found and backed up as: {backup_name}")

    arcpy.management.CreateTable(paths.oid_schema_gdb, paths.oid_schema_template_path)

    fields = []

    # Load registry-defined fields (assumes prior validation)
    for category in ("standard", "not_applicable"):
        if esri_cfg.get(category, True):
            entries = load_field_registry(cfg, category_filter=category)
            if not entries:
                logger.debug(f"No fields loaded for category: {category}")
            for f in entries.values():
                fields.append((f["name"], f["type"], f.get("length"), f.get("alias", f["name"])))

    # Add config-defined fields
    for group in ["mosaic_fields", "grp_idx_fields", "linear_ref_fields", "custom_fields"]:
        block = cfg.get(f"oid_schema_template.{group}", {})
        for f in block.values():
            fields.append((f["name"], f["type"], f.get("length"), f.get("alias", f["name"])))

    added_fields = 0
    for name, ftype, length, alias in fields:
        if not arcpy.ListFields(paths.oid_schema_template_path, name):
            try:
                arcpy.management.AddField(
                    in_table=paths.oid_schema_template_path,
                    field_name=name,
                    field_type=ftype,
                    field_length=length,
                    field_alias=alias,
                    field_is_nullable="NULLABLE"
                )
                added_fields += 1
            except arcpy.ExecuteError as e:
                logger.warning(f"Failed to add field '{name}' (type={ftype}, length={length}) to schema: {e}")

    logger.info(f"✅ OID schema template table created: {paths.oid_schema_template_path} with {added_fields} fields.")
    return paths.oid_schema_template_path
