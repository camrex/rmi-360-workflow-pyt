# =============================================================================
# 🧭 Path Resolution Helpers (utils/path_resolver.py)
# -----------------------------------------------------------------------------
# Purpose:             Resolves relative paths against the config file or toolbox root
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Provides utility functions to resolve relative file paths in a consistent and portable way.
#   Supports resolution relative to the source configuration file (`__source__`) or to the
#   toolbox’s root directory for bundled deployment. Ensures platform-independent path handling.
#
# File Location:        /utils/path_resolver.py
# Called By:            config_loader.py, expression_utils.py, deploy_lambda_monitor.py
# Int. Dependencies:    None
# Ext. Dependencies:    pathlib, typing
#
# Documentation:
#   See: docs/UTILITIES.md
#
# Notes:
#   - Uses pathlib for robust cross-platform path operations
#   - Designed to work both in development and inside ArcGIS Pro deployments
# =============================================================================

from pathlib import Path
from typing import Union


def resolve_relative_to_config(config: dict, relative_path: Union[str, Path]) -> str:
    """
    Resolves a path relative to the directory of the loaded configuration file.
    
    If the provided path is absolute, returns it unchanged. Otherwise, combines the parent directory of the config
    file (as indicated by the '__source__' key in the config dictionary) with the given relative path and returns the
    absolute path as a string.
    
    Args:
        config: Configuration dictionary containing a '__source__' key with the config file path.
        relative_path: Path to resolve, either as a string or Path object.
    
    Returns:
        The absolute path as a string.
    """
    base_path = Path(config.get("__source__", ".")).parent
    full_path = Path(relative_path)
    if full_path.is_absolute():
        return str(full_path)
    return str((base_path / full_path).resolve())


def resolve_relative_to_pyt(relative_path: Union[str, Path]) -> str:
    """
    Resolves a path relative to the root directory of the .pyt toolbox.
    
    If the given path is relative, it is resolved against the toolbox's root directory,
    determined by moving two levels up from the current module's location. Returns the
    absolute path as a string.
    
    Args:
        relative_path: The path to resolve, either as a string or Path object.
    
    Returns:
        The absolute path as a string, resolved relative to the toolbox root.
    """
    # If running inside a bundled toolbox (ArcGIS), use this workaround:
    base_path = Path(__file__).resolve().parent.parent  # utils/ → rmi_mosaic_360_tools/
    return str((base_path / relative_path).resolve())
