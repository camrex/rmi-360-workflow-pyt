
from utils.validators.common_validators import (
    validate_config_section,
    validate_expression_block
)

def validate(cfg: "ConfigManager") -> bool:
    from utils.manager.config_manager import ConfigManager
    """
    Validates the configuration for the "correct_gps_outliers" tool.

    Checks that the "spatial_ref" section exists and is a dictionary, and that the keys
    "gcs_horizontal_wkid" and "vcs_vertical_wkid" are present and are either integers or
    expressions resolving to integers.

    Returns:
        bool: True if validation passes, False otherwise.
    """
    error_count = 0

    if not validate_config_section(cfg, "spatial_ref", expected_type=dict):
        error_count += 1

    sr = cfg.get("spatial_ref", {})
    if not validate_expression_block(block=sr, keys=["gcs_horizontal_wkid", "vcs_vertical_wkid"], cfg=cfg,
                              expected_type=int, context="spatial_ref"):
        error_count += 1

    return error_count == 0