from utils.validators.common_validators import (
    validate_field_block,
    validate_type, check_file_exists
)
from utils.manager.config_manager import ConfigManager
from utils.validate_config import ConfigValidationError
from utils.expression_utils import load_field_registry

def validate(cfg: ConfigManager):
    """
    Validates the configuration for the 'calculate_oid_attributes' tool.

    Checks the presence and structure of required OID fields in the field registry, enforces correct types and required
    defaults, and validates the orientation format. Ensures required mosaic and linear reference fields are present and
    valid. Validates the 'camera_offset' section and its sub-blocks for correct types and resolvable expressions.
    """
    logger = cfg.get_logger()

    template = cfg.get("oid_schema_template", {})
    esri_cfg = template.get("esri_default", {})
    registry_path = esri_cfg.get("field_registry")

    if not registry_path:
        logger.error("Missing required key: oid_schema_template.esri_default.field_registry",
                     error_type=ConfigValidationError)

    registry = load_field_registry(cfg)

    # Required OID fields (some must have oid_default)
    required_fields = [
        "CameraPitch", "CameraRoll", "NearDistance", "FarDistance", "CameraHeight", "SRS", "X", "Y", "Z"
    ]

    for key in required_fields:
        field = registry.get(key)
        if not field:
            logger.error(f"Missing required field: {key}", error_type=ConfigValidationError)
        else:
            validate_field_block(field, context=f"registry.{key}", messages=messages)

            if key in ["CameraPitch", "CameraRoll", "NearDistance", "FarDistance"]:
                validate_type(field.get("oid_default"), f"{key}.oid_default", (int, float), messages)

    # Orientation format check
    orientation_type = registry.get("CameraOrientation", {}).get("orientation_format")
    validate_type(orientation_type, "CameraOrientation.orientation_format", str, messages)
    if orientation_type != "type1_short":
        logger.error("CameraOrientation.orientation_format must be 'type1_short'", error_type=ConfigValidationError)

    # Validate required mosaic_fields
    mosaic = template.get("mosaic_fields", {})
    for key in ["mosaic_reel", "mosaic_frame"]:
        if key not in mosaic:
            logger.error(f"Missing required mosaic field: {key}", error_type=ConfigValidationError)
        else:
            validate_field_block(mosaic[key], context=f"mosaic_fields.{key}", messages=messages)

    # Validate required linear_ref_fields
    linear = template.get("linear_ref_fields", {})
    for key in ["route_identifier", "route_measure"]:
        if key not in linear:
            logger.error(f"Missing required linear_ref field: {key}", error_type=ConfigValidationError)
        else:
            validate_field_block(linear[key], context=f"linear_ref_fields.{key}", messages=messages)

    # ✅ Validate camera_offset blocks
    offset_cfg = cfg.get("camera_offset", {})
    validate_type(offset_cfg, "camera_offset", dict, messages)

    for group in ["z", "camera_height"]:
        path = f"camera_offset.{group}"
        validate_config_section(cfg, path, expected_type=dict, messages=messages)

        block = offset_cfg.get(group, {})
        validate_expression_block(block, list(block.keys()), cfg, (int, float), path, messages)