# =============================================================================
# 🏷️ EXIF Metadata Tagging Logic (utils/apply_exif_metadata.py)
# -----------------------------------------------------------------------------
# Purpose:             Applies EXIF metadata to images using ExifTool, based on dynamic config expressions
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-13
# Last Updated:        2025-05-20
#
# Description:
#   Resolves tag expressions from config for each image in an OID feature class, then generates
#   a batch ExifTool command file. Supports tagging standard and GPS outlier images in-place.
#   Logs resolved metadata and captures success/failure outcomes.
#
# File Location:        /utils/apply_exif_metadata.py
# Validator:            /utils/validators/apply_exif_metadata_validator.py
# Called By:            tools/rename_and_tag_tool.py
# Int. Dependencies:    utils/manager/config_manager, utils/shared/arcpy_utils, utils/shared/expression_utils
# Ext. Dependencies:    arcpy, os, subprocess
# External Tools:       ExifTool (must be installed and available via PATH or config path)
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/rename_and_tag.md
#   (Ensure these docs are current; update if needed.)
#
# Notes:
#   - Supports both string and list-based tag expressions
#   - Uses ExifTool's -@ arg file interface for efficient batch execution
#   - Logs all resolved metadata and batch execution results
# =============================================================================

__all__ = ["update_metadata_from_config"]

import os
import re
import subprocess
import arcpy
from typing import Dict, Any, Union, List

from utils.manager.config_manager import ConfigManager
from utils.shared.expression_utils import resolve_expression
from utils.shared.arcpy_utils import validate_fields_exist
from utils.geoareas_exif_integration import should_use_geoareas, get_geoareas_exif_mapping, get_geoareas_xpkeywords_additions


def _merge_geoareas_tags(cfg: Any, base_tags: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge geo-areas EXIF tags into base metadata tags when geo-areas method is enabled.
    
    Args:
        cfg: ConfigManager instance
        base_tags: Base metadata tags from configuration
        
    Returns:
        Merged tags dictionary with geo-areas tags integrated
    """
    if not should_use_geoareas(cfg.config):
        return base_tags
        
    logger = cfg.get_logger()
    logger.info("Integrating geo-areas tags into metadata configuration...")
    
    # Get geo-areas tag mappings with config-based fallback strategy
    geoareas_tags = get_geoareas_exif_mapping(cfg.config)
    
    # Deep copy base tags to avoid modifying original
    import copy
    merged_tags = copy.deepcopy(base_tags)
    
    # Merge geo-areas tags, with geo-areas taking precedence for location fields
    for tag_name, tag_value in geoareas_tags.items():
        if isinstance(tag_value, dict):
            # Handle nested tags (XMP-iptcExt, XMP-photoshop, etc.)
            if tag_name not in merged_tags:
                merged_tags[tag_name] = {}
            if isinstance(merged_tags[tag_name], dict):
                merged_tags[tag_name].update(tag_value)
            else:
                # If base has scalar value, replace with dict
                merged_tags[tag_name] = tag_value
        else:
            # Handle scalar tags (City, State, Country, etc.)
            merged_tags[tag_name] = tag_value
    
    # Augment XPKeywords with geo-areas specific keywords
    geoareas_keywords = get_geoareas_xpkeywords_additions(cfg.config)
    if geoareas_keywords:
        if 'XPKeywords' not in merged_tags:
            merged_tags['XPKeywords'] = []
        elif not isinstance(merged_tags['XPKeywords'], list):
            # Convert single value to list
            merged_tags['XPKeywords'] = [merged_tags['XPKeywords']]
        
        # Add geo-areas keywords to the list
        merged_tags['XPKeywords'].extend(geoareas_keywords)
        logger.debug(f"Added {len(geoareas_keywords)} geo-areas keywords to XPKeywords")
    
    logger.debug(f"Added geo-areas tags: {list(geoareas_tags.keys())}")
    return merged_tags


def _extract_required_fields(tags, oid_fc=None):
    required_fields = set()
    def recurse_tags(tag_block):
        if isinstance(tag_block, dict):
            for v in tag_block.values():
                recurse_tags(v)
        elif isinstance(tag_block, list):
            for item in tag_block:
                recurse_tags(item)
        elif isinstance(tag_block, str):
            matches = re.findall(r"field\.([a-zA-Z_][a-zA-Z0-9_]*)", tag_block)
            required_fields.update(matches)
    recurse_tags(tags)
    required_fields.update(["X", "Y"])
    
    # Only require QCFlag if it exists in the feature class
    if oid_fc:
        oid_fields = {f.name for f in arcpy.ListFields(oid_fc)}
        if "QCFlag" in oid_fields:
            required_fields.add("QCFlag")
        
        # For geo-areas fields, only require them if they exist
        geo_fields = ["geo_place", "geo_county", "geo_county_fips", "geo_state", "geo_place_source", 
                     "geo_prev_place", "geo_prev_miles", "geo_next_place", "geo_next_miles", "geo_nearest_place"]
        for field in geo_fields:
            if field in required_fields and field in oid_fields:
                # Field is referenced and exists - keep it
                continue
            elif field in required_fields and field not in oid_fields:
                # Field is referenced but doesn't exist - remove from requirements
                # This handles cases where geo-areas hasn't run yet
                required_fields.discard(field)
                
    return required_fields


def _flatten_tags(prefix: str, tags: dict, cfg: Any, row_dict: dict) -> Dict[str, Any]:
    """
    Recursively flattens nested tag dictionaries for ExifTool, e.g.,
    {'GPano': {'PoseHeadingDegrees': '...'}} -> {'XMP-GPano:PoseHeadingDegrees': value}
    
    Returns dict with either string values or list values (for multi-value tags like XPKeywords)
    """
    logger = cfg.get_logger()
    flat: Dict[str, Any] = {}
    for tag_name, value in tags.items():
        if isinstance(value, dict):
            # Nested dict (e.g., GPano)
            new_prefix = f"{prefix}{tag_name}:" if prefix else f"XMP-{tag_name}:"
            flat.update(_flatten_tags(new_prefix, value, cfg, row_dict))
        elif isinstance(value, list):
            # List of expressions (e.g., XPKeywords) - keep as list for proper multi-value handling
            keywords = []
            for item in value:
                try:
                    val = resolve_expression(item, cfg, row=row_dict)
                    if not isinstance(val, str):
                        val = str(val)
                    keywords.append(val)
                except Exception as e:
                    logger.error(f"Failed to resolve tag {tag_name}: {e}", indent=1)
            flat[f"{prefix}{tag_name}"] = keywords  # Keep as list, don't join
        else:
            # String or numeric expression
            try:
                val = resolve_expression(value, cfg, row=row_dict)
                if not isinstance(val, str):
                    val = str(val)
                flat[f"{prefix}{tag_name}"] = val
            except Exception as e:
                logger.error(f"Failed to resolve tag {tag_name}: {e}", indent=1)
    return flat


def _resolve_tags(cfg: Any, tags: dict, row_dict: dict) -> Dict[str, Union[str, List[str]]]:
    # Handles both flat and nested tags
    return _flatten_tags("", tags, cfg, row_dict)


def _escape_exif_value(value: str) -> str:
    """
    Safely escape ExifTool argument values to handle edge cases.
    
    Args:
        value: Raw tag value
        
    Returns:
        Properly escaped value for ExifTool arg file
    """
    # Handle values with quotes by escaping them
    if '"' in value:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    # Handle values starting with @ or containing newlines
    elif value.startswith('@') or '\n' in value:
        return f'"{value}"'
    else:
        return value


def _write_exiftool_args(cfg, tags, rows, cursor_fields):
    args_file = cfg.paths.get_log_file_path("exiftool_args", cfg)
    log_file = cfg.paths.get_log_file_path("exiftool_logs", cfg)
    lines = []
    log_entries = []
    logger = cfg.get_logger()
    
    # Add global ExifTool configuration at start of file
    lines.extend([
        "-charset filename=UTF8",  # Ensure UTF-8 interpretation
        "-n",                      # Numeric mode for GPS/GPano values
        "-P",                      # Preserve file timestamps
        "-overwrite_original_in_place",  # Global flag instead of per-image
        ""  # Empty line for readability
    ])
    
    for i, row in enumerate(rows):
        # Build row_dict from actual cursor_fields
        row_dict = dict(zip(cursor_fields, row))
        path = row_dict["ImagePath"]
        if not os.path.exists(path):
            logger.warning(f"Image path does not exist: {path}")
            continue

        resolved_tags = _resolve_tags(cfg, tags, row_dict)
        if i == 0:
            logger.debug(f"row_dict for first image: {row_dict}")
            logger.debug(f"resolved_tags for first image: {resolved_tags}")
        
        # Add echo marker for this image (helps with troubleshooting)
        lines.append(f"-echo3 OID={row_dict['OID@']}")
        
        # Process resolved tags with proper EXIF group prefixes and multi-value handling
        for tag_name, value in resolved_tags.items():
            # Add explicit EXIF group for common EXIF tags
            if tag_name in ['Artist', 'Software', 'Make', 'Model', 'ImageDescription', 'Copyright', 'SerialNumber', 'FirmwareVersion']:
                tag_name = f"EXIF:{tag_name}"
            
            if isinstance(value, list):
                # Multi-value tags (XPKeywords, etc.) - emit one line per value
                for item in value:
                    escaped_item = _escape_exif_value(str(item))
                    lines.append(f"-{tag_name}={escaped_item}")
            else:
                # Single value tags
                escaped_value = _escape_exif_value(str(value))
                lines.append(f"-{tag_name}={escaped_value}")

        # Only add GPS_OUTLIER logic if QCFlag is present and matches (case-insensitive)
        if "QCFlag" in row_dict and str(row_dict["QCFlag"]).upper() == "GPS_OUTLIER":
            lat, lon = row_dict["Y"], row_dict["X"]
            # Fix: Use single-letter GPS reference values
            lat_ref = "N" if lat >= 0 else "S"
            lon_ref = "E" if lon >= 0 else "W"
            lines.extend([
                f"-GPSLatitude={abs(lat)}",
                f"-GPSLatitudeRef={lat_ref}",
                f"-GPSLongitude={abs(lon)}",
                f"-GPSLongitudeRef={lon_ref}"
            ])

        lines.extend([
            path.replace('\\', '/'),  # File path (global flags already set)
            "-execute",
            ""  # Empty line between image blocks
        ])
        log_entries.append(f"✅ Tagged OID {row_dict['OID@']} → {os.path.basename(path)}")

    with open(args_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("\n".join(log_entries))


def _run_exiftool(cfg, args_file):
    logger = cfg.get_logger()
    exe_path = cfg.paths.exiftool_exe
    if not cfg.paths.check_exiftool_available():
        logger.error(f"ExifTool not found or not working at: {exe_path}", error_type=RuntimeError, indent=1)
    
    try:
        # Capture both stdout and stderr for better logging and troubleshooting
        result = subprocess.run([exe_path, "-@", args_file], 
                              check=False, capture_output=True, text=True)
        
        # Log stdout (normal ExifTool output including echo3 messages)
        if result.stdout.strip():
            logger.debug("ExifTool output:")
            for line in result.stdout.strip().split('\n'):
                logger.debug(f"  {line}", indent=2)
        
        # Check for errors
        if result.returncode != 0:
            logger.error("ExifTool failed with errors:", indent=1)
            if result.stderr.strip():
                for line in result.stderr.strip().split('\n'):
                    logger.error(f"  {line}", indent=2)
            raise RuntimeError(f"ExifTool exited with code {result.returncode}")
        else:
            logger.success("Metadata tagging completed successfully.", indent=1)
            
    except FileNotFoundError:
        logger.error(f"ExifTool executable not found: {exe_path}", error_type=RuntimeError, indent=1)
    except Exception as e:
        logger.error(f"ExifTool execution failed: {e}", error_type=RuntimeError, indent=1)


def update_metadata_from_config(cfg: ConfigManager, oid_fc: str):
    """
    Updates image metadata for images referenced in a feature class using configuration rules.

    Applies metadata tags to images by evaluating expressions defined in a configuration file or dictionary. Tagging
    is performed in batch using ExifTool, with tag values resolved from feature class fields. Handles GPS metadata
    updates for images flagged as outliers and logs all operations and errors.
    
    When geocoding.method is "geo_areas" or "both", automatically integrates corridor geo-areas
    enrichment tags with standard EXIF/XMP location metadata.
    """
    logger = cfg.get_logger()
    cfg.validate(tool="apply_exif_metadata")

    base_tags = cfg.get("image_output.metadata_tags", {})
    if not base_tags:
        logger.error("No metadata_tags defined in config.yaml.", error_type=ValueError, indent=1)
    
    # Merge geo-areas tags if enabled
    tags = _merge_geoareas_tags(cfg, base_tags)

    required_fields = _extract_required_fields(tags, oid_fc=oid_fc)
    validate_fields_exist(oid_fc, list(required_fields))

    oid_fields = {f.name for f in arcpy.ListFields(oid_fc)}
    base_fields = ["OID@", "ImagePath", "X", "Y"]
    if "QCFlag" in oid_fields:
        base_fields.append("QCFlag")
    cursor_fields = base_fields + [f for f in required_fields if f not in base_fields]

    logger.debug(f"Fields used for SearchCursor: {cursor_fields}")
    with arcpy.da.SearchCursor(oid_fc, cursor_fields) as cursor:
        rows = [row for row in cursor]

    _write_exiftool_args(cfg, tags, rows, cursor_fields)
    _run_exiftool(cfg, cfg.paths.get_log_file_path("exiftool_args", cfg))
