# =============================================================================
# 🧠 Expression & Field Resolver (utils/expression_utils.py)
# -----------------------------------------------------------------------------
# Purpose:             Resolves dynamic expressions from config and row data into final values
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Provides utility functions to resolve expressions defined in YAML config or field registry.
#   Supports nested dot-path lookups, type conversion, formatting modifiers, concatenation,
#   and special keywords like `now.year`. Also loads and validates OID field registry schemas.
#
# File Location:        /utils/expression_utils.py
# Called By:            config_loader.py, validate_config.py, most workflow steps
# Int. Dependencies:    path_resolver
# Ext. Dependencies:    os, yaml, datetime, typing, contextlib
#
# Documentation:
#   See: docs/UTILITIES.md and docs/config_schema_reference.md
#
# Notes:
#   - Supports modifiers: strip(), float(), int, date(), upper, lower
#   - Resolves both row-based and config-based expressions recursively
# =============================================================================

import os
import yaml
import contextlib
from datetime import datetime
from typing import Union, Optional, Any
from utils.path_resolver import resolve_relative_to_pyt


REQUIRED_REGISTRY_KEYS = {"name", "type", "length", "alias", "category", "expr", "oid_default", "orientation_format"}


def load_field_registry(registry_path: str, config: Optional[dict] = None, category_filter: Optional[str] = None) \
        -> dict:
    """
    Loads and validates a field registry from a YAML file.

    The registry is checked for required keys in each field entry and optionally filtered by category. Raises an error
    if the file is missing, cannot be parsed as a dictionary, or if required keys are absent.

    Args:
        registry_path: Path to the registry YAML file.
        config: Optional configuration dictionary, used for message logging or contextual validation.
        category_filter: If provided, only fields matching this category are included.

    Returns:
        A dictionary of validated field entries from the registry.

    Raises:
        FileNotFoundError: If the registry file does not exist.
        ValueError: If the file cannot be parsed as a dictionary or required keys are missing.
    """
    if config is not None:
        registry_path = resolve_relative_to_pyt(registry_path)

    if not os.path.exists(registry_path):
        raise FileNotFoundError(f"Field registry file not found: {registry_path}")

    with open(registry_path, "r", encoding="utf-8") as f:
        registry = yaml.safe_load(f)

    if not isinstance(registry, dict):
        raise ValueError(f"Field registry did not parse as a dictionary: {registry_path}")

    validated = {}
    for key, field in registry.items():
        if not isinstance(field, dict):
            raise ValueError(f"Field '{key}' must be a dictionary")

        missing = REQUIRED_REGISTRY_KEYS - set(field.keys())
        if missing:
            # expr and oid_default are optional, but we validate they exist for uniformity
            for opt in ["expr", "oid_default", "orientation_format"]:
                missing.discard(opt)
            if missing:
                raise ValueError(f"Field '{key}' missing required keys: {sorted(missing)}")

        if category_filter and field.get("category") != category_filter:
            continue

        validated[key] = field

    return validated


def resolve_expression(expr: Union[str, float, int], config: dict, row: Optional[dict] = None) -> Any:
    """
    Resolves an expression string using values from a configuration and optional data row.
    
    Supports field lookups, config value retrieval, concatenation of sub-expressions, quoted literals, and the special
    "now.year" expression for the current year. Returns the resolved value as a string or the original value if no
    resolution is performed.
    
    Args:
        expr: The expression to evaluate, which may be a string, float, or integer.
        config: Configuration dictionary used to resolve config-based expressions.
        row: Optional dictionary representing a data row, used to resolve field-based expressions (e.g., {FieldName}).
    
    Returns:
        The resolved value as a string, or the original value if not a string expression.
    """
    if not isinstance(expr, str):
        return str(expr)

    if " + " in expr:
        parts = [resolve_expression(p.strip(), row=row, config=config) for p in expr.split("+")]
        return "".join(str(p) for p in parts)

    if expr.startswith("field.") and row is not None:
        return _resolve_field_expr(expr[6:], row)

    if expr.startswith("config."):
        return _resolve_config_expr(expr[7:], config)

    if expr == "now.year":
        return str(datetime.now().year)

    if (expr.startswith("'") and expr.endswith("'")) or (expr.startswith('"') and expr.endswith('"')):
        return expr[1:-1]

    return expr


def _resolve_field_expr(expr: str, row: dict) -> str:
    """
    Resolves a field expression from a row dictionary, applying optional modifiers.
    
    Supports modifiers such as float formatting, integer conversion, date formatting, character stripping, and case
    transformations. Returns the final formatted string value.
    """
    base, *mods = expr.split(".")
    value = row.get(base)

    for mod in mods:
        if mod.startswith("float("):
            precision = int(mod[6:-1])
            try:
                value = float(value)
                value = f"{value:.{precision}f}"
            except (ValueError, TypeError):
                value = str(value)
        elif mod == "int":
            value = int(float(value))
        elif mod.startswith("date("):
            fmt = mod[5:-1]
            if isinstance(value, datetime):
                value = value.strftime(fmt)
        elif mod.startswith("strip("):
            char = mod[6:-1]
            value = str(value).replace(char, "")
        elif mod == "upper":
            value = str(value).upper()
        elif mod == "lower":
            value = str(value).lower()

    return value


def _resolve_config_expr(expr: str, config: dict) -> str:
    """
    Resolves a value from a nested configuration dictionary with optional formatting modifiers.
    
    Supports dot-separated keys for nested lookup and applies modifiers such as stripping characters, date formatting,
    float precision, integer conversion, and case transformations. Raises KeyError if a specified key or attribute is
    missing or invalid.
    
    Args:
        expr: Dot-separated expression specifying the config key and optional modifiers (e.g., "project.number.strip(-)").
        config: The configuration dictionary to resolve values from.
    
    Returns:
        The resolved and formatted configuration value as a string.
    """
    if expr == "now.year":
        return str(datetime.now().year)

    base, *mods = expr.split(".")
    value = config
    try:
        for part in [base] + [m for m in mods if not _is_modifier(m)]:
            value = value.get(part) if isinstance(value, dict) else getattr(value, part)
    except (KeyError, AttributeError, TypeError):
        raise KeyError(f"Missing or invalid key in config: {expr}") from None

    for mod in mods:
        if mod.startswith("strip("):
            char = mod[6:-1]
            value = str(value).replace(char, "")
        elif mod.startswith("date("):
            fmt = mod[5:-1]
            if isinstance(value, datetime):
                value = value.strftime(fmt)
        elif mod.startswith("float("):
            precision = int(mod[6:-1])
            with contextlib.suppress(Exception):
                value = round(float(value), precision)
        elif mod == "int":
            value = int(float(value))
        elif mod == "upper":
            value = str(value).upper()
        elif mod == "lower":
            value = str(value).lower()

    return value


def _is_modifier(mod: str) -> bool:
    """
    Determines if a string represents a recognized expression modifier.
    
    Returns:
        True if the input string is a supported modifier (e.g., strip, date, float, int, upper, lower); otherwise, False.
    """
    return (
        mod.startswith("strip(") or
        mod.startswith("date(") or
        mod.startswith("float(") or
        mod in {"int", "upper", "lower"}
    )
