# =============================================================================
# ✅ Config Validator & Tool Schema Enforcer (utils/validate_config.py)
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
# File Location:        /utils/validate_config.py
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
import string
from typing import Union, Type, Tuple, Optional

from utils.expression_utils import load_field_registry, resolve_expression
from utils.path_resolver import resolve_relative_to_pyt
from utils.validators.common_validators import *

SUPPORTED_SCHEMA_VERSIONS = {"1.0.1"}


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# TOOL-SPECIFIC VALIDATORS (Modular)
# ─────────────────────────────────────────────────────────────────────────────








def validate_tool_smooth_gps_noise(cfg, messages=None):
    """
    Validates the 'gps_smoothing' section of the configuration for required keys and value types.
    
    Checks that all required parameters are present in the 'gps_smoothing' section, verifies their types, and ensures
    'angle_bounds_deg' is a list of two numeric values. Logs errors for missing keys, type mismatches, or invalid list
    structure.
    """
    gps = cfg.get("gps_smoothing", {})
    validate_type(gps, "gps_smoothing", dict, messages)

    required_keys = {
        "capture_spacing_meters": (int, float),
        "deviation_threshold_m": (int, float),
        "angle_bounds_deg": list,
        "proximity_check_range_m": (int, float),
        "max_route_dist_deviation_m": (int, float),
        "smoothing_window": int,
        "outlier_reason_threshold": int
    }

    for key, expected_type in required_keys.items():
        val = gps.get(key)
        if val is None:
            log_message(f"gps_smoothing.{key} is required", messages, level="error",
                        error_type=ConfigValidationError, config=cfg)
        else:
            validate_type(val, f"gps_smoothing.{key}", expected_type, messages)

    angle_bounds = gps.get("angle_bounds_deg")
    if angle_bounds is None:
        return
    if not (isinstance(angle_bounds, list) and len(angle_bounds) == 2):
        log_message("gps_smoothing.angle_bounds_deg must be a list of two values", messages,
                    level="error", error_type=ConfigValidationError, config=cfg)
    else:
        for i, val in enumerate(angle_bounds):
            validate_type(val, f"gps_smoothing.angle_bounds_deg[{i}]", (int, float), messages)


def validate_tool_correct_gps_outliers(cfg, messages=None):
    """
    Validates the configuration for the "correct_gps_outliers" tool.
    
    Checks that the "spatial_ref" section exists and is a dictionary, and that the keys
    "gcs_horizontal_wkid" and "vcs_vertical_wkid" are present and are either integers or
    expressions resolving to integers.
    """
    validate_config_section(cfg, "spatial_ref", expected_type=dict, messages=messages)

    sr = cfg.get("spatial_ref", {})
    validate_expression_block(block=sr, keys=["gcs_horizontal_wkid", "vcs_vertical_wkid"], cfg=cfg,
                              expected_type=int, context="spatial_ref", messages=messages)


def validate_tool_update_linear_and_custom(cfg, messages=None):
    """
    Validates the 'linear_ref_fields' and 'custom_fields' sections of the OID schema template.
    
    Checks that both sections exist and are dictionaries. Validates each field block within these sections for correct
    structure and types. Ensures that the 'route_measure' field in 'linear_ref_fields' has type 'DOUBLE'.
    """
    validate_config_section(cfg, "oid_schema_template.linear_ref_fields", dict, messages)
    validate_config_section(cfg, "oid_schema_template.custom_fields", dict, messages)

    template = cfg.get("oid_schema_template", {})
    linear_ref = template.get("linear_ref_fields", {})
    custom_fields = template.get("custom_fields", {})

    for key, field in linear_ref.items():
        validate_field_block(field, context=f"linear_ref_fields.{key}", messages=messages)
        if key == "route_measure" and field.get("type") != "DOUBLE":
            log_message("oid_schema_template.linear_ref_fields.route_measure.type must be 'DOUBLE'", messages,
                        level="error", error_type=ConfigValidationError, config=cfg)

    for key, field in custom_fields.items():
        validate_field_block(field, context=f"custom_fields.{key}", messages=messages)


def validate_tool_rename_images(cfg, messages=None):
    """
    Validates the configuration for the image renaming tool's filename settings.
    
    Checks that the filename format string and parts dictionary are present and of correct types, ensures all
    placeholders in the format have corresponding part definitions, warns on unused parts, and validates that each part
    expression resolves to a string.
    """
    validate_config_section(cfg, "image_output.filename_settings", dict, messages)

    settings = cfg.get("image_output", {}).get("filename_settings", {})
    fmt = settings.get("format")
    validate_type(fmt, "image_output.filename_settings.format", str, messages)

    parts = settings.get("parts")
    validate_type(parts, "image_output.filename_settings.parts", dict, messages)

    # ✅ Parse placeholders in format string
    placeholders = {fname for _, fname, _, _ in string.Formatter().parse(fmt) if fname}
    part_keys = set(parts.keys())

    # ✅ Check that all placeholders have matching part definitions
    missing = placeholders - part_keys
    extra = part_keys - placeholders

    if missing:
        log_message(f"Filename format includes undefined placeholder(s): {sorted(missing)}", messages,
                    level="error", error_type=ConfigValidationError, config=cfg)

    if extra:
        log_message(f"Parts contain unused definitions: {sorted(extra)}", messages,
                    level="warning", config=cfg)

    # ✅ Validate that each part expression (if string) resolves to a string (config or mixed)
    for part_name, expr in parts.items():
        if isinstance(expr, str):
            try_resolve_config_expression(expr, f"filename_settings.parts.{part_name}", cfg, messages,
                                          expected_type=str)


def validate_tool_apply_exif_metadata(cfg, messages=None):
    """
    Validates the configuration for applying EXIF metadata to images.
    
    Checks that all required metadata tags are present and correctly structured as strings or lists of strings, and
    that each expression resolves to a string. Also verifies the presence and existence of the exiftool executable path.
    """
    tags = cfg.get("image_output", {}).get("metadata_tags", {})
    validate_type(tags, "image_output.metadata_tags", dict, messages)

    # ✅ Ensure all required metadata fields are defined
    required_metadata_fields = [
        "Artist", "Copyright", "Software", "Make", "Model", "SerialNumber", "FirmwareVersion", "ImageDescription",
        "XPComment", "XPKeywords"
    ]
    missing_fields = [field for field in required_metadata_fields if field not in tags]
    if missing_fields:
        log_message(f"Missing required metadata_tags fields: {sorted(missing_fields)}", messages,
                    level="error", error_type=ConfigValidationError, config=cfg)

    # ✅ Validate each field's structure and resolution
    for tag_name, expr in tags.items():
        if isinstance(expr, str):
            try_resolve_config_expression(expr, f"metadata_tags.{tag_name}", cfg, messages, expected_type=str)

        elif isinstance(expr, list):
            for i, item in enumerate(expr):
                validate_type(item, f"metadata_tags.{tag_name}[{i}]", str, messages)
                try_resolve_config_expression(item, f"metadata_tags.{tag_name}[{i}]", cfg, messages, expected_type=str)

        else:
            log_message(f"metadata_tags.{tag_name} must be a string or list of strings", messages,
                        level="error", error_type=ConfigValidationError, config=cfg)

    # ✅ Validate exiftool executable path
    exe_path = cfg.get("executables", {}).get("exiftool", {}).get("exe_path")
    if not exe_path:
        log_message("executables.exiftool.exe_path must be defined", messages, level="error",
                    error_type=ConfigValidationError, config=cfg)
    check_file_exists(exe_path, "executables.exiftool.exe_path", messages)


def validate_tool_geocode_images(cfg, messages=None):
    """
    Validates the geocoding configuration for the image geocoding tool.
    
    Checks that the geocoding method is set to "exiftool" and that the selected database is one of "default",
    "geolocation500", or "geocustom". For "geolocation500" and "geocustom" databases, ensures the corresponding config
    paths are provided and point to existing files. Also verifies that the ExifTool executable path is specified and
    exists.
    """
    geo_cfg = cfg.get("geocoding", {})
    validate_type(geo_cfg, "geocoding", dict, messages)

    method = geo_cfg.get("method", "").lower()
    db = geo_cfg.get("exiftool_geodb", "default").lower()

    # ✅ Validate method is explicitly "exiftool"
    if method != "exiftool":
        log_message("geocoding.method must be 'exiftool'", messages, level="error", error_type=ConfigValidationError,
                    config=cfg)

    # ✅ Validate database selection
    valid_dbs = {"default", "geolocation500", "geocustom"}
    if db not in valid_dbs:
        log_message(f"Unsupported geocoding.exiftool_geodb: {db}. Must be one of: {sorted(valid_dbs)}", messages,
                    level="error", error_type=ConfigValidationError, config=cfg)

    # ✅ Validate external config paths for optional databases
    if db == "geolocation500":
        path_raw = geo_cfg.get("geoloc500_config_path")
        if not path_raw:
            log_message("Missing geolocation500 config path", messages, level="error",
                        error_type=ConfigValidationError, config=cfg)
        path = resolve_relative_to_pyt(path_raw)
        check_file_exists(path, "geocoding.geoloc500_config_path", messages)

    if db == "geocustom":
        path_raw = geo_cfg.get("geocustom_config_path")
        if not path_raw:
            log_message("Missing geocustom config path", messages, level="error",
                        error_type=ConfigValidationError, config=cfg)
        path = resolve_relative_to_pyt(path_raw)
        check_file_exists(path, "geocoding.geocustom_config_path", messages)

    # ✅ Check exiftool executable
    exe_path = cfg.get("executables", {}).get("exiftool", {}).get("exe_path")
    if not exe_path:
        log_message("executables.exiftool.exe_path must be defined", messages, level="error",
                    error_type=ConfigValidationError, config=cfg)
    check_file_exists(exe_path, "executables.exiftool.exe_path", messages)


def validate_tool_build_oid_footprints(cfg, messages=None):
    # ✅ Ensure spatial_ref exists and is a dictionary
    """
    Validates the configuration for the OID footprint building tool.
    
    Checks that the "spatial_ref" section exists and is a dictionary, ensures "pcs_horizontal_wkid" is present and
    resolves to a positive integer, and verifies that "transformation" is a string if defined. Logs errors for missing
    or invalid values.
    """
    validate_config_section(cfg, "spatial_ref", dict, messages)

    sr = cfg.get("spatial_ref", {})

    # ✅ Ensure pcs_horizontal_wkid resolves to a positive integer
    wkid_expr = sr.get("pcs_horizontal_wkid")
    if wkid_expr is None:
        log_message("Missing required key: spatial_ref.pcs_horizontal_wkid", messages,
                    level="error", error_type=ConfigValidationError, config=cfg)

    resolved_wkid: Optional[int] = try_resolve_config_expression(
        wkid_expr, "spatial_ref.pcs_horizontal_wkid", cfg, messages=messages, expected_type=int)

    if resolved_wkid is not None and resolved_wkid <= 0:
        log_message("spatial_ref.pcs_horizontal_wkid must be a positive integer", messages,
                    level="error", error_type=ConfigValidationError, config=cfg)

    # ✅ Validate transformation, if defined
    transform = sr.get("transformation")
    if transform is not None and not isinstance(transform, str):
        log_message("spatial_ref.transformation must be a string if defined", messages,
                    level="error", error_type=ConfigValidationError, config=cfg)


def validate_tool_deploy_lambda_monitor(cfg, messages=None):
    # Validate aws.region and aws.lambda_role_arn
    """
    Validates the configuration for the Lambda monitor deployment tool.
    
    Checks that required AWS, image output, and project fields are present and of the correct types. Logs errors for
    missing or incorrectly typed values.
    """
    validate_config_section(cfg, "aws", dict, messages)
    validate_type(cfg["aws"].get("region"), "aws.region", str, messages)
    validate_type(cfg["aws"].get("lambda_role_arn"), "aws.lambda_role_arn", str, messages)

    # Validate image_output.folders.final
    validate_config_section(cfg, "image_output.folders", dict, messages)
    validate_type(cfg["image_output"]["folders"].get("renamed"), "image_output.folders.renamed", str, messages)

    # Validate project.slug and project.number
    validate_config_section(cfg, "project", dict, messages)
    validate_type(cfg["project"].get("slug"), "project.slug", str, messages)
    validate_type(cfg["project"].get("number"), "project.number", str, messages)


def validate_tool_copy_to_aws(cfg: dict, messages=None):
    """
    Validates the AWS configuration section for the copy-to-AWS tool.
    
    Checks for required AWS keys and their types, validates optional keys if present, ensures `max_workers` is an
    integer or a valid expression, and verifies that `s3_bucket_folder` resolves to a string.
    """
    aws = cfg.get("aws", {})

    required_keys = {
        "region": str,
        "s3_bucket": str,
        "s3_bucket_folder": str
    }

    for key, expected_type in required_keys.items():
        val = aws.get(key)
        if val is None:
            log_message(f"aws.{key} is required", messages, level="error",
                        error_type=ConfigValidationError, config=cfg)
        else:
            validate_type(val, f"aws.{key}", expected_type, messages)

    # Optional keys
    optional_keys = {
        "skip_existing": bool,
        "retries": int,
        "keyring_aws": bool,
        "keyring_service_name": str,
        "access_key": str,
        "secret_key": str
    }

    for key, expected_type in optional_keys.items():
        if key in aws and aws[key] is not None:
            validate_type(aws[key], f"aws.{key}", expected_type, messages)

    # Special handling for max_workers to allow string expressions like "cpu*2"
    max_workers = aws.get("max_workers")
    if max_workers is not None:
        if isinstance(max_workers, int):
            pass  # valid
        elif isinstance(max_workers, str):
            if max_workers.lower().startswith("cpu*"):
                # Let copy_to_aws.py handle dynamic CPU resolution
                pass
            else:
                try:
                    result = try_resolve_config_expression(max_workers, "aws.max_workers", cfg, messages)
                    if not isinstance(result, int):
                        log_message("aws.max_workers must resolve to an int", messages, level="error",
                                    error_type=ConfigValidationError, config=cfg)
                except Exception as e:
                    log_message(f"aws.max_workers could not be resolved: {e}", messages, level="error",
                                error_type=ConfigValidationError, config=cfg)
    else:
        log_message("aws.max_workers must be an int or a resolvable string expression", messages,
                    level="error", error_type=ConfigValidationError, config=cfg)

    # Ensure s3_bucket_folder resolves to a string
    try_resolve_config_expression(aws.get("s3_bucket_folder"), "aws.s3_bucket_folder", cfg, messages, expected_type=str)


def validate_tool_generate_oid_service(cfg, messages=None):
    """
    Validates the configuration for the OID service generation tool.
    
    Checks the presence and types of required and optional keys in the "portal" and "aws" sections, including
    resolution of the "s3_bucket_folder" expression to a string.
    """
    validate_config_section(cfg, "portal", dict, messages)
    portal = cfg.get("portal", {})

    validate_type(portal.get("project_folder"), "portal.project_folder", str, messages)

    if "summary" in portal:
        validate_type(portal["summary"], "portal.summary", str, messages)

    if "portal_tags" in portal:
        validate_type(portal["portal_tags"], "portal.portal_tags", list, messages)

    validate_config_section(cfg, "aws", dict, messages)
    aws = cfg.get("aws", {})

    if "s3_bucket_folder" not in aws:
        log_message("Missing required key: aws.s3_bucket_folder", messages, level="error",
                    error_type=ConfigValidationError, config=cfg)

    try_resolve_config_expression(aws.get("s3_bucket_folder"), "aws.s3_bucket_folder", cfg, messages,
                                  expected_type=str)


TOOL_VALIDATORS = {
    "mosaic_processor": validate_tool_mosaic_processor,
    "build_oid_schema": validate_tool_build_oid_schema,
    "create_oriented_imagery_dataset": validate_tool_create_oriented_imagery_dataset,
    "add_images_to_oid": validate_tool_add_images_to_oid,
    "assign_group_index": validate_tool_assign_group_index,
    "calculate_oid_attributes": validate_tool_calculate_oid_attributes,
    "smooth_gps_noise": validate_tool_smooth_gps_noise,
    "correct_gps_outliers": validate_tool_correct_gps_outliers,
    "update_linear_and_custom": validate_tool_update_linear_and_custom,
    "enhance_images": validate_tool_enhance_images,
    "rename_images": validate_tool_rename_images,
    "apply_exif_metadata": validate_tool_apply_exif_metadata,
    "geocode_images": validate_tool_geocode_images,
    "build_oid_footprints": validate_tool_build_oid_footprints,
    "deploy_lambda_monitor": validate_tool_deploy_lambda_monitor,
    "copy_to_aws": validate_tool_copy_to_aws,
    "generate_oid_service": validate_tool_generate_oid_service
}

# ─────────────────────────────────────────────────────────────────────────────
# TOOL VALIDATOR DISPATCH WRAPPER (Optional Utility)
# ─────────────────────────────────────────────────────────────────────────────


def validate_tool_config(cfg: dict, tool: str, messages=None):
    """
    Validates the configuration for a specified tool using its registered validator.
    
    If the tool name is not recognized, logs an error and signals a configuration validation failure.
    
    Args:
        cfg: The full configuration dictionary to validate.
        tool: The name of the tool whose configuration should be validated.
        messages: Optional message collector for logging validation results.
    
    Raises:
        ConfigValidationError: If the tool name is not registered.
    """
    if tool in TOOL_VALIDATORS:
        TOOL_VALIDATORS[tool](cfg, messages)
    else:
        log_message(f"Unknown tool '{tool}'", messages, level="error", error_type=ConfigValidationError, config=cfg)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN VALIDATOR
# ─────────────────────────────────────────────────────────────────────────────


def validate_full_config(cfg: dict, messages=None):
    """
    Validates the entire configuration for the orchestrator workflow.
    
    Checks schema version support, required top-level sections, and key types. Validates spatial reference expressions
    and delegates to all tool-specific validators. Logs errors for any validation failures and reports success if all
    checks pass.
    """
    schema_version = cfg.get("schema_version")
    try:
        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            log_message(f"Unsupported schema_version '{schema_version}'. Supported versions: "
                        f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}", messages, level="error",
                        error_type=ConfigValidationError, config=cfg)

        validate_type(cfg.get("debug_messages"), "debug_messages", bool, messages)

        required_sections = [
            "logs", "project", "camera", "camera_offset", "spatial_ref", "executables", "oid_schema_template",
            "gps_smoothing", "image_output.filename_settings", "image_output.metadata_tags", "aws", "portal",
            "geocoding"
        ]

        for section in required_sections:
            validate_config_section(cfg, section, messages=messages)

        validate_expression_block(cfg["spatial_ref"],
                                  ["gcs_horizontal_wkid", "vcs_vertical_wkid", "pcs_horizontal_wkid"],
                                  cfg, int, "spatial_ref", messages)

        # Tool-specific validation
        for tool in TOOL_VALIDATORS:
            TOOL_VALIDATORS[tool](cfg, messages)

    except ConfigValidationError as e:
        log_message(f"[Config Validation] {e}", messages, level="error", error_type=ConfigValidationError, config=cfg)

    log_message("\u2705 Full config validation passed.", messages, config=cfg)


if __name__ == "__main__":
    import sys
    from utils.config_loader import load_config
    config_path = sys.argv[1] if len(sys.argv) > 1 else "../configs/config.yaml"
    config = load_config(config_path)
    validate_full_config(config)
