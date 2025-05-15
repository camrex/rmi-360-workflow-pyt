# =============================================================================
# 🏷️ Apply EXIF Metadata Validator (utils/validators/apply_exif_metadata_validator.py)
# -----------------------------------------------------------------------------
# Purpose:             Validates configuration for applying EXIF metadata to images
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
# Last Updated:        2025-05-15
#
# Description:
#   Checks required EXIF metadata tags, validates their structure and resolvable expressions, and ensures
#   the ExifTool executable path is present and valid for image processing.
#
# File Location:        /utils/validators/apply_exif_metadata_validator.py
# Called By:            EXIF metadata application workflows
# Notes:                Ensures all required EXIF tags and tool paths are set for downstream processing.
# =============================================================================
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.manager.config_manager import ConfigManager

from utils.shared.exceptions import ConfigValidationError
from utils.validators.common_validators import (
    validate_type,
    try_resolve_config_expression
)

def validate(cfg: "ConfigManager") -> bool:
    """
    Validates the configuration for applying EXIF metadata to images.

    Checks that all required metadata tags are present and correctly structured as strings or lists of strings, and
    that each expression resolves to a string. Also verifies the presence and existence of the exiftool executable path.

    Returns:
        bool: True if validation passes, False otherwise.
    """
    logger = cfg.get_logger()
    error_count = 0

    tags = cfg.get("image_output.metadata_tags", {})
    if not validate_type(tags, "image_output.metadata_tags", dict, cfg):
        error_count += 1

    # ✅ Ensure all required metadata fields are defined
    required_metadata_fields = [
        "Artist", "Copyright", "Software", "Make", "Model", "SerialNumber", "FirmwareVersion", "ImageDescription",
        "XPComment", "XPKeywords"
    ]
    missing_fields = [field for field in required_metadata_fields if field not in tags]
    if missing_fields:
        logger.error(f"Missing required metadata_tags fields: {sorted(missing_fields)}",
                     error_type=ConfigValidationError)
        error_count += 1

    extra_tags = set(tags.keys()) - set(required_metadata_fields)
    if extra_tags:
        logger.warning(f"Found extra metadata_tags fields not in required list: {sorted(extra_tags)}")

    # ✅ Validate each field's structure and resolution
    for tag_name, expr in tags.items():
        if isinstance(expr, str):
            if not try_resolve_config_expression(expr, f"metadata_tags.{tag_name}", cfg, expected_type=str):
                error_count += 1

        elif isinstance(expr, list):
            for i, item in enumerate(expr):
                if not validate_type(item, f"metadata_tags.{tag_name}[{i}]", str, cfg):
                    error_count += 1
                if not try_resolve_config_expression(item, f"metadata_tags.{tag_name}[{i}]", cfg,
                                                     expected_type=str):
                    error_count += 1

        else:
            logger.error(f"metadata_tags.{tag_name} must be a string or list of strings",
                         error_type=ConfigValidationError)
            error_count += 1

    # ✅ Validate exiftool executable path
    exe_path = cfg.paths.exiftool_exe
    if not cfg.paths.check_exiftool_available():
        logger.error(f"ExifTool not available or not found at path: {exe_path}", error_type=ConfigValidationError)
        error_count += 1

    return error_count == 0