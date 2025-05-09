# =============================================================================
# 🗂️ OID Schema Path Resolver (utils/schema_paths.py)
# -----------------------------------------------------------------------------
# Purpose:             Resolves paths related to the OID schema template from configuration
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Extracts the template directory, geodatabase path, schema table name, and output path
#   from the YAML config. Returns a dataclass (`SchemaTemplatePaths`) with resolved fields.
#   Ensures OS-independent path handling using pathlib and config-relative resolution logic.
#
# File Location:        /utils/schema_paths.py
# Called By:            build_oid_schema.py, create_oid_feature_class.py
# Int. Dependencies:    config_loader, path_resolver
# Ext. Dependencies:    pathlib, dataclasses
#
# Documentation:
#   See: docs/UTILITIES.md and docs/config_schema_reference.md
#
# Notes:
#   - Refactor planned: convert all path-like fields to pathlib.Path objects
# =============================================================================

from dataclasses import dataclass
from utils.config_loader import load_config
from utils.path_resolver import resolve_relative_to_pyt
from pathlib import Path


@dataclass
class SchemaTemplatePaths:
    templates_dir: str
    gdb_path: str
    template_name: str
    output_path: str

# TODO: Convert path-like fields to pathlib.Path types for clarity and consistency
# - This will reduce repeated casting and improve OS-independent path handling
# - Audit downstream usage for any string assumptions before switching


def resolve_schema_template_paths(config=None) -> SchemaTemplatePaths:
    """
    Resolves and returns schema template file paths based on configuration.
    
    If no configuration is provided, uses the default configuration. Extracts template-related settings, resolves the
    templates directory, geodatabase path, template name, and constructs the output path. Returns a
    `SchemaTemplatePaths` instance containing these resolved values.
    
    Returns:
        SchemaTemplatePaths: An object with resolved paths for templates directory, geodatabase, template name, and
        output path.
    """
    if config is None:
        config = load_config(None)

    template_cfg = config.get("oid_schema_template", {}).get("template", {})

    templates_dir_raw = template_cfg.get("templates_dir", "templates")
    templates_dir = resolve_relative_to_pyt(templates_dir_raw)

    gdb_path_raw = template_cfg.get("gdb_path", "templates.gdb")
    gdb_path = str(Path(templates_dir) / gdb_path_raw)

    template_name = template_cfg.get("template_name", "oid_schema_template")
    output_path = str(Path(gdb_path) / template_name)

    return SchemaTemplatePaths(
        templates_dir=templates_dir,
        gdb_path=gdb_path,
        template_name=template_name,
        output_path=output_path
    )
