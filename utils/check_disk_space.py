# =============================================================================
# 💾 Disk Space Checker (utils/check_disk_space.py)
# -----------------------------------------------------------------------------
# Purpose:             Verifies available disk space before performing image enhancement or export
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Estimates required disk space using the size of the base imagery folder (original or enhanced),
#   applies a configurable buffer ratio, and compares it against available space on the drive.
#   Prevents out-of-space failures during image-intensive steps in the pipeline.
#
# File Location:        /utils/check_disk_space.py
# Called By:            tools/enhance_images_tool.py, tools/rename_images_tool.py
# Int. Dependencies:    arcpy_utils
# Ext. Dependencies:    arcpy, os, shutil
#
# Documentation:
#   See: docs/UTILITIES.md and docs/tools/enhance_images.md
#
# Notes:
#   - Automatically resolves the base folder from any image path in the OID
#   - Raises RuntimeError if insufficient space is detected
# =============================================================================

import arcpy
import os
import shutil
from utils.arcpy_utils import log_message


def check_sufficient_disk_space(oid_fc, config=None, buffer_ratio=1.1, verbose=False, messages=None):
    """
    Checks if sufficient disk space is available for image operations on an Oriented Imagery Dataset.
    
    Estimates the required disk space by calculating the size of the relevant 'original' or 'enhanced' image directory
    and applying a safety buffer. Raises an error if the available space on the drive is less than the estimated
    requirement.
    
    Args:
        oid_fc: Path to the Oriented Imagery Dataset feature class.
        config: Optional configuration dictionary that may specify disk space settings and folder names.
        buffer_ratio: Safety multiplier applied to the estimated required space. Defaults to 1.1.
        verbose: If True, logs detailed messages.
        messages: Optional ArcGIS Pro message interface or None for CLI.
    
    Raises:
        ValueError: If no valid image path is found or if the image path does not include expected folder names.
        FileNotFoundError: If the base image directory does not exist.
        RuntimeError: If available disk space is insufficient.
    
    Returns:
        True if sufficient disk space is available.
    """

    if config is None:
        config = {}

    # Read from config if available
    if config:
        disk_cfg = config.get("disk_space", {})
        if not disk_cfg.get("check_enabled", True):
            if verbose:
                log_message("Disk space check is disabled via config.", messages, config=config)
            return True
        buffer_ratio = disk_cfg.get("min_buffer_ratio", buffer_ratio)

    # Get one valid ImagePath from the FC
    with arcpy.da.SearchCursor(oid_fc, ["ImagePath"]) as cursor:
        image_path = next((row[0] for row in cursor if row[0]), None)

    if not image_path:
        log_message("No valid ImagePath found in the OID feature class.", messages, level="error",
                    error_type=ValueError, config=config)

    # Determine target folder from ImagePath
    target_dir = os.path.dirname(image_path)
    drive_root = os.path.splitdrive(target_dir)[0] + os.sep

    # Get folder names from config
    img_folders = config.get("image_output", {}).get("folders", {})
    original_folder = img_folders.get("original", "original").lower()
    enhanced_folder = img_folders.get("enhanced", "enhanced").lower()

    # Identify which folder we're in (preserving case but allowing case-insensitive match)
    def _find_base(d: str, token: str) -> str | None:
        idx = d.lower().find(token.lower())
        return d[: idx + len(token)] if idx != -1 else None

    base_dir = _find_base(target_dir, original_folder) or _find_base(target_dir, enhanced_folder)

    if not base_dir:
        log_message(f"ImagePath does not include '{original_folder}' or '{enhanced_folder}' folder.", messages,
                    level="error", error_type=ValueError, config=config)

    if not os.path.exists(base_dir):
        log_message(f"Base folder not found: {base_dir}", messages, level="error", error_type=FileNotFoundError,
                    config=config)

    # Calculate total existing size
    def get_folder_size(path):
        """
        Calculates the total size of all files within a directory, including subdirectories.
        
        Args:
            path: Path to the directory whose total file size will be computed.
        
        Returns:
            The cumulative size in bytes of all files contained in the directory and its subdirectories.
        """
        total = 0
        for root, _, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                if os.path.isfile(fp):
                    total += os.path.getsize(fp)
        return total

    folder_size = get_folder_size(base_dir)
    estimated_required = int(folder_size * buffer_ratio)

    # Get available space on drive
    free_space = shutil.disk_usage(drive_root).free

    if verbose:
        log_message(f"Checking disk space on drive: {drive_root}", messages, config=config)
        log_message(f"Checking space in folder: {base_dir}", messages, config=config)
        log_message(f"Base folder size (used): {folder_size / 1e9:.2f} GB", messages, config=config)
        log_message(f"Estimated required: {estimated_required / 1e9:.2f} GB (with buffer)", messages, config=config)
        log_message(f"Available: {free_space / 1e9:.2f} GB", messages, config=config)

    if free_space < estimated_required:
        log_message(f"❌ Insufficient disk space.\n"
                    f"Needed (with buffer): {estimated_required / 1e9:.2f} GB\n"
                    f"Available: {free_space / 1e9:.2f} GB",
                    messages, level="error", error_type=RuntimeError, config=config)

    return True
