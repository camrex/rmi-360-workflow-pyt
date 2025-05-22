# =============================================================================
# 🧬 OID Schema Template Builder (utils/build_oid_schema.py)
# -----------------------------------------------------------------------------
# Purpose:             Creates a reusable schema template table for Oriented Imagery Datasets (OIDs)
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.1
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
# Last Updated:        2025-05-22
#
# Description:
#   Builds a geodatabase table to serve as a schema template for OID creation. It integrates
#   fields from both a central field registry and project-level config blocks. Performs backup
#   of existing templates, schema validation, and writes fields using ArcPy management tools.
#
# File Location:        /utils/build_oid_schema.py
# Validator:            /utils/validators/build_oid_schema_validator.py
# Called By:            tools/create_oid_template_tool.py
# Int. Dependencies:    utils/manager/config_manager, utils/shared/expression_utils
# Ext. Dependencies:    arcpy, os, datetime, typing
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/create_oid_and_schema.md
#   (Ensure these docs are current; update if needed.)
#
# Notes:
#   - Respects categories (standard, not_applicable) from registry
#   - Auto-backs up existing templates with timestamp before overwrite
# =============================================================================

__all__ = ["create_oid_schema_template"]

import arcpy
import os
from datetime import datetime
from typing import Optional, cast

from utils.manager.config_manager import ConfigManager
from utils.shared.expression_utils import load_field_registry
from utils.validators.common_validators import EsriFieldType


def _field_tuple(f: dict) -> tuple[str, str, Optional[int], str]:
    return (
        f["name"],
        f["type"],
        f.get("length"),
        f.get("alias", f["name"])
    )

def create_oid_schema_template(
    cfg: ConfigManager
) -> str:
    """
    Creates a schema template table for Oriented Imagery Datasets (OIDs) using configuration and field registry files.

    Args:
        cfg: Validated configuration manager.
    Returns:
        The full path to the created schema template table.
    Raises:
        ValueError: If the required field registry path is missing in the configuration.
    """
    logger = cfg.get_logger()
    cfg.validate(tool="build_oid_schema")
    paths = cfg.paths
    esri_cfg = cfg.get("oid_schema_template.esri_default", {})
    logger.debug(f"Creating OID schema template: {paths.oid_schema_template_path}", indent=0)
    templates_path = paths.templates
    oid_schema_gdb_path = paths.oid_schema_gdb
    oid_schema_gdb_name = os.path.basename(oid_schema_gdb_path)

    try:
        if not os.path.exists(templates_path):
            logger.debug(f"Templates directory does not exist, creating: {templates_path}", indent=1)
            os.makedirs(templates_path, exist_ok=True)
            logger.debug(f"Templates directory created: {templates_path}", indent=1)
        if not arcpy.Exists(oid_schema_gdb_path):
            logger.debug(f"OID schema gdb does not exist, creating: {oid_schema_gdb_path}", indent=1)
            arcpy.management.CreateFileGDB(str(templates_path), str(oid_schema_gdb_name))
            logger.debug(f"OID schema gdb created: {oid_schema_gdb_path}", indent=1)
        if arcpy.Exists(str(paths.oid_schema_template_path)):
            logger.debug(f"Existing schema template found: {paths.oid_schema_template_path}", indent=1)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{paths.oid_schema_template_name}_{timestamp}"
            arcpy.management.Rename(str(paths.oid_schema_template_path), str(backup_name))
            logger.info(f"Existing schema template found and backed up as: {backup_name}", indent=1)
        logger.debug(f"Creating new schema template table: {paths.oid_schema_template_path}", indent=1)
        arcpy.management.CreateTable(str(oid_schema_gdb_path), str(paths.oid_schema_template_name))
        logger.debug(f"Schema template table created: {paths.oid_schema_template_path}", indent=1)
        fields: list[tuple[str, str, Optional[int], str]] = []

        # Load registry-defined fields (assumes prior validation)
        for category in ("standard", "not_applicable"):
            if esri_cfg.get(category, True):
                entries = load_field_registry(cfg, category_filter=category)
                if not entries:
                    logger.debug(f"No fields loaded for category: {category}", indent=1)
                for f in entries.values():
                    fields.append(_field_tuple(f))

        # Add config-defined fields
        for group in ["mosaic_fields", "grp_idx_fields", "linear_ref_fields", "custom_fields"]:
            block = cfg.get(f"oid_schema_template.{group}", {})
            for f in block.values():
                fields.append(_field_tuple(f))
        added_fields = 0
        logger.debug("Checking if fields exist in schema template and adding missing fields", indent=1)
        for name, ftype, length, alias in fields:
            field_type = cast(EsriFieldType, ftype)
            if not arcpy.ListFields(str(paths.oid_schema_template_path), name):
                logger.debug(f"Field '{name}' not found in schema template, adding...", indent=1)
                try:
                    arcpy.management.AddField(
                        in_table=str(paths.oid_schema_template_path),
                        field_name=name,
                        field_type=field_type,
                        field_length=length,
                        field_alias=alias,
                        field_is_nullable="NULLABLE"
                    )
                    logger.debug(f"Field '{name}' added to schema template: {paths.oid_schema_template_path}", indent=1)
                    added_fields += 1
                except Exception as e:
                    logger.error(f"Failed to add field '{name}' (type={ftype}, length={length}) to schema: {e}", indent=1)
                    raise
        logger.success(f"OID schema template table created: {paths.oid_schema_template_path} with {added_fields} fields.", indent=0)
        return paths.oid_schema_template_path
    except Exception as e:
        logger.error(f"Failed to create OID schema template: {e}", indent=0)
        raise
