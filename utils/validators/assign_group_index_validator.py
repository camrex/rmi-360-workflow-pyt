from utils.validators.common_validators import (
    validate_type,
    validate_field_block
)
from utils.manager.config_manager import ConfigManager

def validate(cfg: ConfigManager) -> bool:
    """
    Validates the 'grp_idx_fields' section of the configuration for group index assignment.

    Checks that 'grp_idx_fields' exists under 'oid_schema_template' and is a dictionary. Validates each field block
    within for correct structure and types.

    Returns:
        bool: True if all validations pass, False otherwise.
    """
    error_count = 0

    grp_idx = cfg.get("oid_schema_template.grp_idx_fields", {})
    if not validate_type(grp_idx, "oid_schema_template.grp_idx_fields", dict, cfg):
        error_count += 1

    for key, field in grp_idx.items():
        if not validate_field_block(field, cfg, context=f"grp_idx_fields.{key}"):
            error_count += 1

    return error_count == 0