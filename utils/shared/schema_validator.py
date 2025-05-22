# =============================================================================
# ✅ OID Schema Validator (utils/schema_validator.py)
# -----------------------------------------------------------------------------
# Purpose:             Validates the presence and completeness of the OID schema template
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.1
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
# Last Updated:        2025-05-22
#
# Description:
#   Checks the existence and field completeness of the configured OID schema template feature class.
#   If auto-creation is enabled and the schema is missing or invalid, attempts to regenerate it
#   using build_oid_schema.py and revalidate. Verifies registry-defined fields, custom schema blocks,
#   and standard categories. Logs descriptive errors and raises on failure.
#
# File Location:        /utils/shared/schema_validator.py
# Called By:            create_oid_feature_class.py, orchestrator, config_loader
# Int. Dependencies:    utils/manager/config_manager, utils/shared/expression_utils, utils/shared/exceptions, utils/shared/build_oid_schema
# Ext. Dependencies:    arcpy, typing
#
# Documentation:
#   See: docs_legacy/UTILITIES.md and docs_legacy/tools/create_oid_and_schema.md
#
# Notes:
#   - Supports auto-creation via config["oid_schema_template"]["template"]["auto_create_oid_template"]
#   - Detects and logs any missing required fields based on the registry and schema config
# =============================================================================

import arcpy
from typing import Set

from utils.shared.expression_utils import load_field_registry
from utils.build_oid_schema import create_oid_schema_template
from utils.shared.rmi_exceptions import ConfigValidationError
from utils.manager.config_manager import ConfigManager


def _extract_required_field_names(cfg: 'ConfigManager', registry: dict) -> Set[str]:
    """
    Helper to extract required field names from config and registry.
    """
    required_names = set()
    not_applicable_enabled = cfg.get("oid_schema_template.esri_default.not_applicable", False)
    for _key, field in registry.items():
        cat = field.get("category")
        if cat == "standard" or (cat == "not_applicable" and not_applicable_enabled):
            required_names.add(field["name"])
    for section in ["mosaic_fields", "grp_idx_fields", "linear_ref_fields", "custom_fields"]:
        fields = cfg.get(f"oid_schema_template.{section}", {})
        for f in fields.values():
            required_names.add(f["name"])
    return required_names

def validate_oid_template_schema(cfg: 'ConfigManager') -> bool:
    """
    Validates that the OID schema template feature class exists and contains all required fields.

    Args:
        cfg (ConfigManager): Configuration manager.
    Returns:
        True if validation passes.
        False if the template is missing, or required fields are missing (both now log a warning).
    """
    logger = cfg.get_logger()
    paths = cfg.paths
    template_fc = paths.oid_schema_template_path

    if not arcpy.Exists(template_fc):
        logger.warning(f"OID schema template not found at: {template_fc}")
        return False

    existing_fields = {f.name for f in arcpy.ListFields(template_fc)}
    registry = load_field_registry(cfg=cfg)
    required_names = _extract_required_field_names(cfg, registry)

    missing = required_names - existing_fields
    if missing:
        logger.warning(f"OID template is missing {len(missing)} required field(s): {sorted(missing)}")
        return False

    return True

def ensure_valid_oid_schema_template(cfg: 'ConfigManager') -> None:
    """
    Ensures the OID schema template exists and meets all required field specifications.

    If the template is missing or invalid and automatic creation is enabled in the configuration, attempts to
    regenerate the template and revalidate it. Logs errors and raises a ConfigValidationError if the schema remains
    invalid after regeneration.

    Args:
        cfg (ConfigManager): Configuration manager with paths, logging, and template access.
    Raises:
        ConfigValidationError: If the schema template is invalid after a rebuild attempt.
    """
    logger = cfg.get_logger()
    auto_create = cfg.get("oid_schema_template.template.auto_create_oid_template", False)

    with cfg.get_progressor(total=2, label="Validating OID Schema Template") as progressor:
        if validate_oid_template_schema(cfg):
            progressor.update(2)
            return  # ✅ Schema is valid, done

        if not auto_create:
            logger.error("OID schema template is invalid and auto_create_oid_template is set to False. "
                         "Please run create_oid_schema_template() manually.", error_type=ConfigValidationError, indent=1)
            return

        # 🚧 Try to rebuild
        logger.custom("Schema template invalid — attempting to regenerate with build_oid_schema.py...", emoji="🚧", indent=1)
        create_oid_schema_template(cfg)
        progressor.update(1)

        if validate_oid_template_schema(cfg):
            progressor.update(2)
            return
        else:
            logger.error("Rebuilt schema template, but validation still failed. Check for missing fields or malformed "
                         "registry.", error_type=ConfigValidationError, indent=1)
