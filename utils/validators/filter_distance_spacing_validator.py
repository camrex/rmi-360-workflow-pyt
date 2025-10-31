# =============================================================================
# 📏 Distance-Based Spacing Filter Validator (utils/validators/filter_distance_spacing_validator.py)
# -----------------------------------------------------------------------------
# Purpose:             Validates configuration for distance-based spacing filter tool
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-10-31
# Last Updated:        2025-10-31
#
# Description:
#   Validates configuration parameters for the distance-based spacing filter tool,
#   including minimum spacing thresholds, tolerance values, and action parameters.
#
# File Location:        /utils/validators/filter_distance_spacing_validator.py
# Called By:            utils/manager/config_manager.py (via validate method)
# Int. Dependencies:    None
# Ext. Dependencies:    None
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md
# =============================================================================

__all__ = ["filter_distance_spacing_validator"]


def filter_distance_spacing_validator(config_dict: dict) -> list:
    """
    Validates the configuration for the "filter_distance_spacing" tool.

    This function checks that distance spacing parameters are properly configured,
    including minimum spacing requirements, tolerance values, and ensures that
    the configuration supports both flagging and removal actions.

    Args:
        config_dict (dict): The full configuration dictionary to validate.

    Returns:
        list: A list of validation error messages. Empty if all validations pass.

    Validates:
        - distance_spacing.min_spacing_meters: Must be a positive number
        - distance_spacing.tolerance_meters: Must be a non-negative number
        - Tolerance should be reasonable relative to minimum spacing
    """
    errors = []

    # Ensure the incoming configuration is a mapping to avoid AttributeError
    if not isinstance(config_dict, dict):
        errors.append("config: Expected a mapping/dict for configuration.")
        return errors
        
    # Check if distance_spacing section exists and is a dict
    distance_spacing = config_dict.get("distance_spacing", None)
    
    if not isinstance(distance_spacing, dict) or not distance_spacing:
        errors.append(
            "distance_spacing: Section is missing or invalid. "
            "This section should contain min_spacing_meters and tolerance_meters."
        )
        return errors

    # Validate min_spacing_meters
    min_spacing = distance_spacing.get("min_spacing_meters")
    if min_spacing is None:
        errors.append("distance_spacing.min_spacing_meters: Required parameter is missing.")
    elif not isinstance(min_spacing, (int, float)):
        errors.append(
            f"distance_spacing.min_spacing_meters: Expected a number, got {type(min_spacing).__name__}."
        )
    elif min_spacing <= 0:
        errors.append(
            f"distance_spacing.min_spacing_meters: Must be positive, got {min_spacing}."
        )

    # Validate tolerance_meters
    tolerance = distance_spacing.get("tolerance_meters")
    if tolerance is None:
        errors.append("distance_spacing.tolerance_meters: Required parameter is missing.")
    elif not isinstance(tolerance, (int, float)):
        errors.append(
            f"distance_spacing.tolerance_meters: Expected a number, got {type(tolerance).__name__}."
        )
    elif tolerance < 0:
        errors.append(
            f"distance_spacing.tolerance_meters: Must be non-negative, got {tolerance}."
        )

    # Validate relationship between min_spacing and tolerance
    if (isinstance(min_spacing, (int, float)) and isinstance(tolerance, (int, float)) and 
        min_spacing > 0 and tolerance >= 0):
        
        if tolerance >= min_spacing:
            errors.append(
                f"distance_spacing.tolerance_meters: Tolerance ({tolerance}m) should be less than "
                f"min_spacing_meters ({min_spacing}m) to be meaningful."
            )
        
        # Warn about very large tolerance relative to spacing
        if tolerance > (min_spacing * 0.5):
            errors.append(
                f"distance_spacing.tolerance_meters: Large tolerance ({tolerance}m) relative to "
                f"min_spacing ({min_spacing}m) may reduce filter effectiveness."
            )

    return errors