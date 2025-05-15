
from utils.exceptions import ConfigValidationError
from utils.validators.common_validators import (
    validate_config_section,
    validate_field_block
)

def validate(cfg: "ConfigManager") -> bool:
    from utils.manager.config_manager import ConfigManager
    """
    Validates the 'linear_ref_fields' and 'custom_fields' sections of the OID schema template.

    Checks that both sections exist and are dictionaries. Validates each field block within these sections for correct
    structure and types. Ensures that the 'route_measure' field in 'linear_ref_fields' has type 'DOUBLE'.

    Returns:
        bool: True if validation passes, False otherwise.
    """
    logger = cfg.get_logger()
    error_count = 0

    if not validate_config_section(cfg, "oid_schema_template.linear_ref_fields", dict):
        error_count += 1
    if not validate_config_section(cfg, "oid_schema_template.custom_fields", dict):
        error_count += 1

    linear_ref = cfg.get("oid_schema_template.linear_ref_fields")
    custom_fields = cfg.get("oid_schema_template.custom_fields")

    for key, field in linear_ref.items():
        if not validate_field_block(field, cfg, context=f"linear_ref_fields.{key}"):
            error_count += 1
        if key == "route_measure" and field.get("type") != "DOUBLE":
            logger.error("oid_schema_template.linear_ref_fields.route_measure.type must be 'DOUBLE'",
                         error_type=ConfigValidationError)
            error_count += 1

    for key, field in custom_fields.items():
        if not validate_field_block(field, cfg, context=f"custom_fields.{key}"):
            error_count += 1

    return error_count == 0