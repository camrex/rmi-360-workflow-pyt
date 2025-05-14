import string
from utils.manager.config_manager import ConfigManager
from utils.exceptions import ConfigValidationError
from utils.validators.common_validators import (
    validate_config_section,
    validate_type,
    try_resolve_config_expression
)


def validate(cfg: ConfigManager) -> bool:
    """
    Validates the configuration for the image renaming tool's filename settings.

    Checks that the filename format string and parts dictionary are present and of correct types, ensures all
    placeholders in the format have corresponding part definitions, warns on unused parts, and validates that each part
    expression resolves to a string.

    Returns:
        bool: True if validation passes, False otherwise.
    """
    logger = cfg.get_logger()
    error_count = 0

    if not validate_config_section(cfg, "image_output.filename_settings", dict):
        error_count += 1

    fmt = cfg.get("image_output.filename_settings.format")
    if not validate_type(fmt, "image_output.filename_settings.format", str, cfg):
        error_count += 1

    parts = cfg.get("image_output.filename_settings.parts")
    if not validate_type(parts, "image_output.filename_settings.parts", dict, cfg):
        error_count += 1

    # ✅ Parse placeholders in format string
    placeholders = {fname for _, fname, _, _ in string.Formatter().parse(fmt) if fname}
    part_keys = set(parts.keys())

    # ✅ Check that all placeholders have matching part definitions
    missing = placeholders - part_keys
    extra = part_keys - placeholders

    if missing:
        logger.error(f"Filename format includes undefined placeholder(s): {sorted(missing)}",
                     error_type=ConfigValidationError)
        error_count += 1

    if extra:
        logger.warning(f"Parts contain unused definitions: {sorted(extra)}")

    if not placeholders:
        logger.error("Filename format must include at least one placeholder (e.g. '{segment_id}')",
                     error_type=ConfigValidationError)
        error_count += 1

    # ✅ Validate that each part expression (if string) resolves to a string (config or mixed)
    for part_name, expr in parts.items():
        if isinstance(expr, str):
            if not try_resolve_config_expression(expr, f"filename_settings.parts.{part_name}", cfg,
                                                 expected_type=str):
                error_count += 1

    return error_count == 0
