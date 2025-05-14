from utils.validators.common_validators import (
    validate_config_section,
    validate_expression_block
)
from utils.manager.config_manager import ConfigManager

def validate(cfg: ConfigManager) -> bool:
    """
    Validates the configuration for the 'create_oriented_imagery_dataset' tool.

    Checks that the 'spatial_ref' section exists and is a dictionary, and that the
    'gcs_horizontal_wkid' and 'vcs_vertical_wkid' keys are present and either integers
    or expressions resolvable to integers.

    Returns:
        bool: True if config passes validation, False otherwise.
    """
    error_count = 0

    if not validate_config_section(cfg, "spatial_ref", expected_type=dict):
        error_count += 1

    sr = cfg.get("spatial_ref", {})
    if not validate_expression_block(sr, keys=["gcs_horizontal_wkid", "vcs_vertical_wkid"], cfg=cfg, expected_type=int,
                                     context="spatial_ref"):
        error_count += 1

    return error_count == 0