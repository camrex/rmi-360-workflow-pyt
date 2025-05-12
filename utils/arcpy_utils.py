# =============================================================================
# 📎 ArcPy Utilities (utils/arcpy_utils.py)
# -----------------------------------------------------------------------------
# Purpose:             Reusable helpers for field validation, and OID backup.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.1
# Author:              RMI Valuation, LLC
# Created:             2025-05-11
#
# Description:
#   Centralizes common ArcGIS Pro field existence validation.
#   Also includes tools for boolean/value coercion and OID backup.
#
# File Location:        /utils/arcpy_utils.py
# Called By:            Multiple tools and utilities throughout the pipeline
# Int. Dependencies:    ConfigManager, LogManager
# Ext. Dependencies:    arcpy, datetime, pathlib, typing
#
# Documentation:
#   See: docs_legacy/UTILITIES.md and internal docstrings
#
# Notes:
#   - OID backups automatically name and store snapshots per step
# =============================================================================

import arcpy
from pathlib import Path
from datetime import datetime
from typing import Union

from utils.manager.config_manager import ConfigManager
from utils.manager.log_manager import LogManager


def validate_fields_exist(feature_class: str, required_fields: list[str], logger: LogManager = None):
    """
    Checks that all required fields are present in a feature class.

    Logs a ValueError (via LogManager) and raises it automatically if any are missing.

    Args:
        feature_class (str): The feature class path to validate.
        required_fields (list[str]): List of field names that must exist.
        logger (LogManager, optional): Optional logger to use for reporting missing fields.

    Raises:
        ValueError – if any required field is missing (automatically raised via LogManager if used)
    """
    existing_fields = {f.name for f in arcpy.ListFields(feature_class)}
    missing = [f for f in required_fields if f not in existing_fields]

    if missing:
        msg = f"Missing required field(s) in {feature_class}: {', '.join(missing)}"
        if logger:
            logger.error(msg, error_type=ValueError)
        else:
            raise ValueError(msg)


def str_to_bool(val) -> bool:
    """
    Converts a value to a native Python boolean.
    
    Accepts boolean values directly. For strings, returns True if the value is one of
    "true", "1", "yes", or "on" (case-insensitive); returns False otherwise.
    """
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "on")
    return False


def str_to_value(value, value_type: Union[str, type], logger: LogManager = None):
    """
    Converts a value to a specified type, with special handling for spatial references.
    
    Args:
        value: The input value to convert.
        value_type: A type (e.g., int, float) or the string 'spatial_reference'
        logger: Optional LogManager instance for debug/error output.
    
    Returns:
        The converted value, or None if the input is invalid or conversion fails.
    """
    if value is None:
        return None

    if value_type == "spatial_reference":
        import arcpy
        if isinstance(value, arcpy.SpatialReference):
            return value
        try:
            return arcpy.SpatialReference(value)
        except (ValueError, TypeError, arcpy.ExecuteError) as e:
            if logger:
                logger.debug(f"Failed to convert '{value}' to spatial_reference: {e}")
            return None

    try:
        return value_type(value)
    except (ValueError, TypeError) as e:
        if logger:
            logger.debug(f"Failed to convert '{value}' to {value_type}: {e}")
        return None


def backup_oid(oid_fc: str, step_key: str, cfg: ConfigManager) -> None:
    """
    Creates a timestamped backup of the Oriented Imagery Dataset feature class before a processing step.

    Args:
        oid_fc (str): Input feature class path.
        step_key (str): Step name for labeling the snapshot.
        cfg (ConfigManager): Loaded configuration manager.
    """
    logger = cfg.get_logger()  # Initialize early to ensure scope during exception handling

    try:
        gdb_path = cfg.paths.backup_gdb
        gdb_path.parent.mkdir(parents=True, exist_ok=True)

        if not gdb_path.exists():
            arcpy.management.CreateFileGDB(str(gdb_path.parent), gdb_path.name)

        oid_desc = arcpy.Describe(oid_fc)
        oid_name = Path(oid_desc.name).stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        out_fc_name = f"{oid_name}_before_{step_key}_{timestamp}"
        out_fc_path = str(gdb_path / out_fc_name)

        logger.info(f"📁 Backing up OID before step '{step_key}' → {out_fc_name}")
        arcpy.management.Copy(oid_fc, out_fc_path)

    except Exception as e:
        logger.warning(f"OID backup before step '{step_key}' failed: {e}")
