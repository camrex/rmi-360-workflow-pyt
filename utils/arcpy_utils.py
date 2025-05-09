# =============================================================================
# 📎 ArcPy Utilities & Messaging (utils/arcpy_utils.py)
# -----------------------------------------------------------------------------
# Purpose:             Reusable helpers for ArcGIS messaging, field validation, and logging
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Centralizes common ArcGIS Pro operations such as logging, messaging, and field
#   existence validation. Also includes tools for boolean/value coercion and OID backup.
#
# File Location:        /utils/arcpy_utils.py
# Called By:            Multiple tools and utilities throughout the pipeline
# Int. Dependencies:    path_utils
# Ext. Dependencies:    arcpy, datetime, pathlib, typing
#
# Documentation:
#   See: docs/UTILITIES.md and internal docstrings
#
# Notes:
#   - log_message supports emoji-prefixed logging with exception raising
#   - OID backups automatically name and store snapshots per step
# =============================================================================

import arcpy
from pathlib import Path
from datetime import datetime
from typing import Optional, Type

from utils.path_utils import get_log_path


def validate_fields_exist(feature_class, required_fields, messages=None):
    """
    Checks that all required fields are present in a feature class.
    
    Raises a ValueError if any required fields are missing. If a messages object is provided, adds an error message
    before raising.
    """
    existing_fields = {f.name for f in arcpy.ListFields(feature_class)}
    missing = [f for f in required_fields if f not in existing_fields]

    if missing:
        msg = f"Missing required field(s) in {feature_class}: {', '.join(missing)}"
        if messages:
            messages.addErrorMessage(msg)
        raise ValueError(msg)


def log_message(
    msg: str,
    messages: Optional[object] = None,
    level: str = "info",
    error_type: Optional[Type[Exception]] = None,
    config: Optional[dict] = None,
    log_to_file: bool = True
):
    """
    Logs a message with a timestamp and severity level to ArcGIS Pro, the console, and optionally a persistent log file.
    
    If a messages object is provided, the message is sent using the appropriate ArcPy messaging method; otherwise, it
    is printed to the console. Supports log levels "debug", "info", "warning", and "error", with emoji prefixes. Debug
    messages are only logged if enabled in the config. If level is "error" and a valid error_type is provided, the
    function raises that exception immediately after logging. Optionally writes the message to a project log file; file
    write errors are logged as warnings but do not interrupt execution.
    
    Args:
        msg: The message to log or display.
        messages: Optional ArcGIS messaging interface (e.g., from script tools) for logging.
        level: The severity level ("debug", "info", "warning", or "error").
        error_type: If provided and level is "error", this exception type will be raised with the message.
        config: Used to control debug message visibility and log file path.
        log_to_file: If True, appends the message to a persistent log file.
    
    Raises:
        Exception: If level is "error" and a valid error_type is provided, that exception is raised with the message.
    """
    # Validate level argument
    valid_levels = {"debug", "info", "warning", "error"}
    if level not in valid_levels:
        # Log it as info and give a warning
        log_message(f"⚠️ Invalid log level '{level}'. Defaulting to 'info'.", messages, level="warning", config=config)
        level = "info"  # Treat invalid level as "info"

    if level == "debug" and (config is None or not config.get("debug_messages", False)):
        return

    prefix = {
        "debug": "🛠️", "info": "ℹ️",
        "warning": "⚠️", "error": "❌"
    }.get(level, "")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {prefix} {msg}"

    if messages:
        if level == "warning" and hasattr(messages, "addWarningMessage"):
            messages.addWarningMessage(full_msg)
        elif level == "error" and hasattr(messages, "addErrorMessage"):
            messages.addErrorMessage(full_msg)
        elif hasattr(messages, "addMessage"):
            messages.addMessage(full_msg)
    else:
        print(full_msg)

    # File output
    if log_to_file and config:
        try:
            log_file_path = get_log_path("process_log", config)

            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(full_msg + "\n")

        except Exception as e:
            # If log file write fails, don't interrupt main process
            if messages and hasattr(messages, "addWarningMessage"):
                messages.addWarningMessage(f"[WARNING] Failed to write to log file: {e}")
            else:
                print(f"⚠️ [WARNING] Failed to write to log file: {e}")

    if level == "error" and error_type:
        if isinstance(error_type, type) and issubclass(error_type, Exception):
            raise error_type(full_msg)
        else:
            if messages and hasattr(messages, "addErrorMessage"):
                messages.addErrorMessage(f"Invalid error_type passed to log_message: {error_type}")
            else:
                print(f"❌ Invalid error_type passed to log_message: {error_type}")
            raise RuntimeError(f"Invalid error_type passed to log_message: {error_type}")


def str_to_bool(val):
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


def str_to_value(value, value_type):
    """
    Converts a value to a specified type, with special handling for spatial references.
    
    If the target type is "spatial_reference", attempts to convert the value to an arcpy.SpatialReference object. For
    other types (e.g., int, float, str), performs a standard type conversion. Returns None if the conversion fails or
    if the input value is None.
    
    Args:
        value: The input value to convert.
        value_type: The target type or the string "spatial_reference".
    
    Returns:
        The converted value, or None if conversion is unsuccessful.
    """
    if value is None:
        return None

    if value_type == "spatial_reference":
        import arcpy
        if isinstance(value, arcpy.SpatialReference):
            return value
        try:
            return arcpy.SpatialReference(value)
        except (ValueError, TypeError, arcpy.ExecuteError):
            return None

    try:
        return value_type(value)
    except (ValueError, TypeError):
        return None


def infer_project_root_from_oid(
    oid_fc: str,
    config: dict,
    messages=None
) -> str:
    """
    Infers the project root directory from the ImagePath field of the first image in an Oriented Imagery Dataset.
    
    Examines the ImagePath of the first record in the provided feature class and searches for configured folder tags
    (such as "enhanced", "original", or "renamed"). Returns the directory two levels above the matched folder tag.
    Raises a ValueError if no suitable folder tag is found in the path.
    """
    folders_cfg = config.get("image_output", {}).get("folders", {})
    candidates = [folders_cfg.get("enhanced"), folders_cfg.get("original"), folders_cfg.get("renamed")]

    with arcpy.da.SearchCursor(oid_fc, ["ImagePath"], where_clause="ImagePath IS NOT NULL") as cursor:
        for row in cursor:
            image_path = Path(row[0])
            for tag in filter(None, candidates):
                if tag in image_path.parts:
                    idx = image_path.parts.index(tag)
                    if idx < 1:
                        log_message("Cannot infer project root - folder tag is at top level.", messages,
                                    level="error", error_type=ValueError, config=config)
                        return ""
                    return str(Path(*image_path.parts[:idx - 1]))
            break

    searched_tags = [tag for tag in filter(None, candidates)]
    log_message(f"❌ Unable to infer project root from OID image paths. Searched for tags: {searched_tags}",
                messages, level="error", error_type=ValueError, config=config)
    return ""


def backup_oid(oid_fc: str, step_key: str, config: dict, messages=None):
    """
    Creates a timestamped backup of the Oriented Imagery Dataset feature class before a processing step.
    
    The backup is saved in a centralized file geodatabase specified by the configuration, with the backup feature
    class named to indicate the step and time. If the backup operation fails, a warning is logged but no exception is
    raised.
    """
    try:
        # Resolve backup path
        project_root = config.get("__project_root__", ".")
        gdb_rel_path = config.get("orchestrator", {}).get("oid_backup_fgdb", "backups/oid_snapshots.gdb")
        gdb_path = Path(project_root) / gdb_rel_path
        gdb_path.parent.mkdir(parents=True, exist_ok=True)

        # Create the FGDB if it doesn't exist
        if not gdb_path.exists():
            arcpy.management.CreateFileGDB(str(gdb_path.parent), gdb_path.name)

        # Describe the original FC
        oid_desc = arcpy.Describe(oid_fc)
        oid_name = Path(oid_desc.name).stem

        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        out_fc_name = f"{oid_name}_before_{step_key}_{timestamp}"
        out_fc_path = str(gdb_path / out_fc_name)

        # Perform the backup
        log_message(f"📁 Backing up OID before step '{step_key}' → {out_fc_name}", messages, config=config)
        arcpy.management.Copy(oid_fc, out_fc_path)

    except Exception as e:
        log_message(f"[WARNING] OID backup before step '{step_key}' failed: {e}", messages, level="warning",
                    config=config)

