from utils.manager.config_manager import ConfigManager
from utils.validate_config import ConfigValidationError
from utils.validators.common_validators import (
    validate_type,
    check_required_keys,
    validate_field_block,
    check_duplicate_field_names
)
from utils.expression_utils import load_field_registry

def validate(cfg: ConfigManager) -> bool:
    """
    Validates the configuration for building an OID schema template.

    Checks the presence and structure of the "oid_schema_template" section, including required keys in the "template"
    block and the existence of the field registry. Validates all fields in the registry and user-defined schema blocks
    for correctness and checks for duplicate field names.

    Returns:
        bool: True if config is valid, False otherwise.
    """
    logger = cfg.get_logger()
    error_count = 0

    schema_cfg = cfg.get("oid_schema_template", {})
    template_cfg = cfg.get("oid_schema_template.template", {})
    registry_path = cfg.paths.oid_field_registry

    if not registry_path:
        logger.error("Missing required key: oid_schema_template.esri_default.field_registry",
                     error_type=ConfigValidationError)
        error_count += 1

    if not validate_type(template_cfg, "oid_schema_template.template", dict, cfg):
        error_count += 1

    if not check_required_keys(
        template_cfg,
        ["auto_create_oid_template", "templates_dir", "gdb_path", "template_name"],
        "oid_schema_template.template", cfg):
        error_count += 1

    if not validate_type(
        template_cfg.get("auto_create_oid_template"), "oid_schema_template.template.auto_create_oid_template",
        bool, cfg):
        error_count += 1

    # Load and validate registry fields
    try:
        registry = load_field_registry(cfg)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Failed to load field registry: {e}", error_type=ConfigValidationError)
        return False

    for key, field in registry.items():
        if not validate_field_block(field, cfg, context=f"registry.{key}"):
            error_count += 1

    # Validate user-defined schema blocks
    for block_key in ["mosaic_fields", "linear_ref_fields", "custom_fields"]:
        block = schema_cfg.get(block_key, {})
        if not validate_type(block, f"oid_schema_template.{block_key}", dict, cfg):
            error_count += 1
        for key, field in block.items():
            if not validate_field_block(field, cfg, context=f"{block_key}.{key}"):
                error_count += 1

    duplicates = check_duplicate_field_names(cfg, registry)
    if duplicates:
        error_count += 1

    return error_count == 0
