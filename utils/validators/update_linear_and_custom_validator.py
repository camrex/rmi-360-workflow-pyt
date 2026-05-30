# =============================================================================
# 🔄 Update Linear and Custom Validator (utils/validators/update_linear_and_custom_validator.py)
# -----------------------------------------------------------------------------
# Purpose:             Validates linear reference and custom fields in the OID schema template
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
# Last Updated:        2025-05-15
#
# Description:
#   Ensures that the 'linear_ref_fields' and 'custom_fields' sections exist, are dictionaries, and that all field
#   blocks are valid. Checks that the 'route_measure' field in 'linear_ref_fields' has type 'DOUBLE'.
#
# File Location:        /utils/validators/update_linear_and_custom_validator.py
# Called By:            OID schema update and field validation workflows
# Notes:                Used for validation of schema changes and custom field additions to OID templates.
# =============================================================================

from utils.shared.rmi_exceptions import ConfigValidationError
from utils.validators.common_validators import (
    validate_config_section,
    validate_field_block,
    validate_keys_with_types,
    validate_type,
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

    sequence_cfg = cfg.get("sequence_order", {})
    if sequence_cfg:
        if not validate_type(sequence_cfg, "sequence_order", dict, cfg):
            error_count += 1
        else:
            optional_keys = {
                "enabled": bool,
                "field_name": str,
                "acquisition_datetime_field": str,
                "lr_prefix_field": str,
                "lr_mile_field": str,
                "prefix_order": list,
                "descending_prefixes": list,
                "null_milepost_position": str,
            }
            error_count += validate_keys_with_types(cfg, sequence_cfg, optional_keys, "sequence_order", required=False)

            null_position = sequence_cfg.get("null_milepost_position", "end")
            if isinstance(null_position, str) and null_position.lower() not in {"start", "end"}:
                logger.error("sequence_order.null_milepost_position must be 'start' or 'end'", error_type=ConfigValidationError)
                error_count += 1

            for key in ("prefix_order", "descending_prefixes"):
                values = sequence_cfg.get(key, [])
                if isinstance(values, list):
                    for i, value in enumerate(values):
                        if not isinstance(value, str):
                            logger.error(f"sequence_order.{key}[{i}] must be a string", error_type=ConfigValidationError)
                            error_count += 1

    return error_count == 0