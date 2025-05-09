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
#   See: docs/UTILITIES.md and docs/tools/create_oid_and_schema.md
#
# Notes:
#   - Supports auto-creation via config["oid_schema_template"]["template"]["auto_create_oid_template"]
#   - Detects and logs any missing required fields based on the registry and schema config
# =============================================================================

import arcpy
from utils.schema_paths import resolve_schema_template_paths
from utils.expression_utils import load_field_registry
from utils.validate_config import ConfigValidationError, log_message
from utils.build_oid_schema import create_oid_schema_template


def validate_oid_template_schema(config: dict, messages=None):
    """
    Validates that the OID schema template feature class exists and contains all required fields.
    
    Checks the existence of the OID schema template and verifies that it includes all fields required by the
    configuration, including ESRI default, mosaic, group index, linear reference, and custom fields. Logs an error and
    raises a ConfigValidationError if any required fields are missing.
    """
    template_fc = resolve_schema_template_paths(config).output_path

    if not arcpy.Exists(template_fc):
        log_message(f"OID schema template not found at: {template_fc}", messages,
                    level="error", error_type=FileNotFoundError, config=config)

    existing_fields = {f.name for f in arcpy.ListFields(template_fc)}
    template_cfg = config.get("oid_schema_template", {})
    esri_cfg = template_cfg.get("esri_default", {})
    registry_path = esri_cfg.get("field_registry")
    registry = load_field_registry(registry_path, config=config)

    required_names = set()

    # ESRI standard + not_applicable (if enabled)
    for _key, field in registry.items():
        cat = field.get("category")
        if cat == "standard" or (cat == "not_applicable" and esri_cfg.get("not_applicable", False)):
            required_names.add(field["name"])

    # Mosaic
    for f in template_cfg.get("mosaic_fields", {}).values():
        required_names.add(f["name"])

    # Group index fields
    for f in template_cfg.get("grp_idx_fields", {}).values():
        required_names.add(f["name"])

    # Linear ref fields
    for f in template_cfg.get("linear_ref_fields", {}).values():
        required_names.add(f["name"])

    # Custom
    for f in template_cfg.get("custom_fields", {}).values():
        required_names.add(f["name"])

    # Compare
    missing = required_names - existing_fields
    if missing:
        log_message(f"OID template is missing {len(missing)} required field(s): {sorted(missing)}",
                    messages, level="error", error_type=ConfigValidationError, config=config)


def ensure_valid_oid_schema_template(config: dict, config_file: str, messages=None) -> None:
    """
    Ensures the OID schema template exists and meets all required field specifications.
    
    If the template is missing or invalid and automatic creation is enabled in the configuration, attempts to
    regenerate the template and revalidate it. Logs errors and raises a ConfigValidationError if the schema remains
    invalid after regeneration.
    
    Args:
        config: Configuration dictionary containing OID schema template settings.
        config_file: Path to the configuration file, used for template regeneration.
        messages: Optional ArcGIS Pro message object for logging.
    
    Raises:
        ConfigValidationError: If the schema template is invalid after a rebuild attempt.
    """
    auto_create = config.get("oid_schema_template", {}).get("template", {}).get("auto_create_oid_template", False)

    try:
        validate_oid_template_schema(config, messages=messages)
        return  # ✅ Schema is valid, done
    except (FileNotFoundError, ConfigValidationError):
        if not auto_create:
            log_message(
                "❌ OID schema template is invalid and auto_create_oid_template is set to False. "
                "Please run create_oid_schema_template() manually.",
                messages, level="error", error_type=ConfigValidationError, config=config
            )
            return

        # 🚧 Try to rebuild
        log_message("⚠️ Schema template invalid — attempting to regenerate with build_oid_schema.py...", messages,
                    config=config)
        create_oid_schema_template(config_file=config_file, messages=messages)

        try:
            validate_oid_template_schema(config, messages=messages)
        except (FileNotFoundError, ConfigValidationError):
            log_message("❌ Rebuilt schema template, but validation still failed. Check for missing fields or "
                        "malformed registry.", messages, level="error", error_type=ConfigValidationError, config=config)
