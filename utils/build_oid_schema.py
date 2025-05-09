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
# Called By:            tools/create_oid_template_tool.py
# Int. Dependencies:    config_loader, expression_utils, arcpy_utils, schema_paths
# Ext. Dependencies:    arcpy, os, datetime, typing
#
# Documentation:
#   See: docs/TOOL_GUIDES.md and docs/tools/create_oid_and_schema.md
#
# Notes:
#   - Respects categories (standard, not_applicable) from registry
#   - Auto-backs up existing templates with timestamp before overwrite
# =============================================================================

__all__ = ["create_oid_schema_template"]

import arcpy
import os
from datetime import datetime
from typing import Optional
from utils.config_loader import resolve_config
from utils.expression_utils import load_field_registry
from utils.arcpy_utils import log_message
from utils.schema_paths import resolve_schema_template_paths


def create_oid_schema_template(
        config: Optional[dict] = None,
        config_file: Optional[str] = None,
        messages=None) -> str:
    """
    Creates a schema template table for Oriented Imagery Datasets (OIDs) using configuration and field registry files.

    The function generates a geodatabase table with fields defined by a YAML configuration and a field registry. It
    ensures the output directory and geodatabase exist, backs up any existing schema template, and adds fields from
    both the registry and configuration groups. Returns the full path to the created schema template table.

    Args:
        config: Optional configuration dictionary. If not provided, loaded from config_file.
        config_file: Optional path to a configuration YAML file.
        messages: Optional messaging or logging handler.

    Returns:
        The full path to the created schema template table.

    Raises:
        ValueError: If the required field registry path is missing in the configuration.
    """
    config = resolve_config(
        config=config,
        config_file=config_file,
        messages=messages,
        tool_name="build_oid_schema")

    paths = resolve_schema_template_paths(config)
    esri_cfg = config.get("oid_schema_template", {}).get("esri_default", {})

    if not os.path.exists(paths.templates_dir):
        os.makedirs(paths.templates_dir, exist_ok=True)
    if not arcpy.Exists(paths.gdb_path):
        arcpy.management.CreateFileGDB(paths.templates_dir, os.path.basename(paths.gdb_path))

    if arcpy.Exists(paths.output_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{paths.template_name}_{timestamp}"
        arcpy.management.Rename(paths.output_path, backup_name)
        log_message(f"⚠️ Existing schema template found and backed up as: {backup_name}", messages, config=config)

    arcpy.management.CreateTable(paths.gdb_path, paths.template_name)

    fields = []

    # Load from registry
    registry_path = esri_cfg.get("field_registry")
    if not registry_path:
        log_message("Missing required key: oid_schema_template.esri_default.field_registry", messages, level="error",
                    error_type=ValueError, config=config)

    for category in ("standard", "not_applicable"):
        if esri_cfg.get(category, True):
            entries = load_field_registry(registry_path, config=config, category_filter=category)
            if not entries:
                if category == "standard":
                    log_message(f"Failed to load required {category} fields from registry: {registry_path}", messages,
                                level = "error", error_type = ValueError, config = config)
                else:
                    log_message(f"No {category} fields found in registry: {registry_path}", messages,
                                level = "warning", config = config)
                    continue
            for f in entries.values():
                fields.append((f["name"], f["type"], f.get("length", None), f.get("alias", f["name"])))

    # Add config-defined fields
    for group in ["mosaic_fields", "grp_idx_fields", "linear_ref_fields", "custom_fields"]:
        block = config.get("oid_schema_template", {}).get(group, {})
        for _key, f in block.items():
            if not isinstance(f, dict) or "name" not in f or "type" not in f:
                log_message(f"⚠️ Invalid field configuration in {group}.{_key}: missing required keys",
                            messages, level="warning", config=config)
                continue
            fields.append((f["name"], f["type"], f.get("length"), f.get("alias", f["name"])))

    # Valid ArcGIS field types
    VALID_FIELD_TYPES = {"TEXT", "FLOAT", "DOUBLE", "SHORT", "LONG", "DATE", "BLOB", "RASTER", "GUID", "GLOBALID", "XML"}

    for name, ftype, length, alias in fields:
        if ftype not in VALID_FIELD_TYPES:
            log_message(f"⚠️ Invalid field type '{ftype}' for field '{name}', skipping", messages,
                        level = "warning", config = config)
            continue
        if not arcpy.ListFields(paths.output_path, name):
            try:
                arcpy.management.AddField(
                    in_table=paths.output_path,
                    field_name=name,
                    field_type=ftype,
                    field_length=length,
                    field_alias=alias,
                    field_is_nullable="NULLABLE"
                )
            except arcpy.ExecuteError as e:
                log_message(f"⚠️ Failed to add field {name} to schema: {e}", messages, level="warning", config=config)

    log_message(f"✅ OID schema template table created: {paths.output_path}", messages, config=config)
    return paths.output_path
