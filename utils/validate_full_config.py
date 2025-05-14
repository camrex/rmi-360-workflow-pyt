# =============================================================================
# ✅ Config Validator & Tool Schema Enforcer (utils/validate_full_config.py)
# -----------------------------------------------------------------------------
# Purpose:             Validates the entire YAML configuration against expected structure, types, and tool-specific rules
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Performs comprehensive validation of the pipeline’s configuration, including schema version checks,
#   required section enforcement, and dynamic expression resolution. Registers tool-specific validators
#   for all supported workflow steps (e.g., enhance_images, copy_to_aws, deploy_lambda_monitor).
#   Raises `ConfigValidationError` for invalid structures, missing fields, or improper expressions.
#
# File Location:        /utils/validate_full_config.py
# Called By:            config_loader.py, orchestrator, CLI validation entrypoint
# Int. Dependencies:    arcpy_utils, expression_utils, path_resolver, config_loader, schema_paths
# Ext. Dependencies:    shutil, string, typing, pathlib
#
# Documentation:
#   See: docs_legacy/CONFIG_GUIDE.md and docs_legacy/config_schema_reference.md
#
# Notes:
#   - Uses per-tool validator dispatch via `TOOL_VALIDATORS` registry
#   - Supports `DISABLED` flags and external command validation (e.g., exiftool path)
#   - Designed to be run both via `__main__` and programmatically from tool execution
# =============================================================================
from utils.validators.common_validators import (
    validate_type,
    validate_config_section,
    validate_expression_block
)
from utils.manager.config_manager import ConfigManager, SUPPORTED_SCHEMA_VERSIONS
from utils.exceptions import ConfigValidationError


def validate_full_config(cfg: ConfigManager):
    """
    Validates the entire configuration for the orchestrator workflow.
    
    Checks schema version support, required top-level sections, and key types. Validates spatial reference expressions
    and delegates to all tool-specific validators. Logs errors for any validation failures and reports success if all
    checks pass.
    """
    schema_version = cfg.get("schema_version")

    logger = cfg.get_logger()
    error_count = 0

    try:
        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            logger.error(f"Unsupported schema_version '{schema_version}'. Supported versions: "
                        f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}", error_type=ConfigValidationError)
            error_count += 1

        validate_type(cfg.get("debug_messages"), "debug_messages", bool, cfg)

        required_sections = [
            "logs", "project", "camera", "camera_offset", "spatial_ref", "executables", "oid_schema_template",
            "gps_smoothing", "image_output.filename_settings", "image_output.metadata_tags", "aws", "portal",
            "geocoding"
        ]

        for section in required_sections:
            validate_config_section(cfg, section, cfg)

        validate_expression_block(cfg["spatial_ref"],
                                  ["gcs_horizontal_wkid", "vcs_vertical_wkid", "pcs_horizontal_wkid"],
                                  cfg, int, "spatial_ref")

        # Tool-specific validation
        for tool in cfg.TOOL_VALIDATORS:
            cfg.TOOL_VALIDATORS[tool](cfg)
            error_count += 1

    except ConfigValidationError as e:
        logger.error(f"[Config Validation] {e}", error_type=ConfigValidationError)
        return False

    if error_count == 0:
        logger.info("✅ Full config validation passed.")
        return True
    return False


if __name__ == "__main__":
    import sys
    from utils.config_loader import load_config
    config_path = sys.argv[1] if len(sys.argv) > 1 else "../configs/config.yaml"
    config = load_config(config_path)
    validate_full_config(config)
