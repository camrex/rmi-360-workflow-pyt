# =============================================================================
# ✅ OID Schema Validator (utils/schema_validator.py)
# -----------------------------------------------------------------------------
# Purpose:             Validates the presence and completeness of the OID schema template
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Checks the existence and field completeness of the configured OID schema template feature class.
#   If auto-creation is enabled and the schema is missing or invalid, attempts to regenerate it
#   using build_oid_schema.py and revalidate. Verifies registry-defined fields, custom schema blocks,
#   and standard categories. Logs descriptive errors and raises on failure.
#
# File Location:        /utils/schema_validator.py
# Called By:            create_oid_feature_class.py, orchestrator, config_loader
# Int. Dependencies:    schema_paths, expression_utils, validate_config, build_oid_schema
# Ext. Dependencies:    arcpy
#
# Documentation:
#   See: docs_legacy/UTILITIES.md and docs_legacy/tools/create_oid_and_schema.md
#
# Notes:
#   - Supports auto-creation via config["oid_schema_template"]["template"]["auto_create_oid_template"]
#   - Detects and logs any missing required fields based on the registry and schema config
# =============================================================================

import arcpy
from utils.expression_utils import load_field_registry
from utils.validate_config import ConfigValidationError
from utils.build_oid_schema import create_oid_schema_template
from utils.manager.config_manager import ConfigManager


def validate_oid_template_schema(cfg: ConfigManager):
    """
    Validates that the OID schema template feature class exists and contains all required fields.
    
    Checks the existence of the OID schema template and verifies that it includes all fields required by the
    configuration, including ESRI default, mosaic, group index, linear reference, and custom fields. Logs an error and
    raises a ConfigValidationError if any required fields are missing.
    """
    logger = cfg.get_logger()
    paths = cfg.paths
    template_fc = paths.oid_schema_template_path

    if not arcpy.Exists(template_fc):
        logger.error(f"OID schema template not found at: {template_fc}", error_type=FileNotFoundError)

    existing_fields = {f.name for f in arcpy.ListFields(template_fc)}
    registry = load_field_registry(cfg=cfg)

    required_names = set()

    # ESRI standard + not_applicable (if enabled)
    not_applicable_enabled = cfg.get("oid_schema_template.esri_default.not_applicable", False)
    for _key, field in registry.items():
        cat = field.get("category")
        if cat == "standard" or (cat == "not_applicable" and not_applicable_enabled):
            required_names.add(field["name"])

    # Schema-based fields using flat access
    for section in ["mosaic_fields", "grp_idx_fields", "linear_ref_fields", "custom_fields"]:
        fields = cfg.get(f"oid_schema_template.{section}", {})
        for f in fields.values():
            required_names.add(f["name"])

    # Compare
    missing = required_names - existing_fields
    if missing:
        logger.error(f"OID template is missing {len(missing)} required field(s): {sorted(missing)}",
                     error_type=ConfigValidationError)

    return True


def ensure_valid_oid_schema_template(cfg: ConfigManager) -> None:
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

    try:
        validate_oid_template_schema(cfg)
        return  # ✅ Schema is valid, done
    except (FileNotFoundError, ConfigValidationError):
        if not auto_create:
            logger.error("❌ OID schema template is invalid and auto_create_oid_template is set to False. "
                         "Please run create_oid_schema_template() manually.", error_type=ConfigValidationError)
            return

        # 🚧 Try to rebuild
        logger.info("⚠️ Schema template invalid — attempting to regenerate with build_oid_schema.py...")
        create_oid_schema_template(config_file=cfg.source_path)

        try:
            validate_oid_template_schema(cfg)
        except (FileNotFoundError, ConfigValidationError):
            logger.error("❌ Rebuilt schema template, but validation still failed. Check for missing fields or "
                         "malformed registry.", error_type=ConfigValidationError)
