# =============================================================================
# 💾 Disk Space Checker (utils/check_disk_space.py)
# -----------------------------------------------------------------------------
# Purpose:             Verifies available disk space before performing workflow operations
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.3.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-13
# Last Updated:        2025-10-30
#
# Description:
#   Estimates required disk space from the images the OID actually references (i.e.
#   exactly what Rename copies — the manifest's kept set in pre-thin mode, NOT the full
#   source 'original' folder), applies a configurable buffer ratio, and compares it
#   against free space on the renamed-output drive. Prevents out-of-space failures
#   during image-intensive steps in the pipeline.
#
# File Location:        /utils/check_disk_space.py
# Called By:            tools/enhance_images_tool.py, tools/rename_images_tool.py
# Int. Dependencies:    utils/manager/config_manager
# Ext. Dependencies:    arcpy, os, shutil, pathlib, typing
#
# Documentation:
#   See: docs_legacy/UTILITIES.md and docs_legacy/tools/enhance_images.md
#   (Ensure these docs are current; update if needed.)
#
# Notes:
#   - Automatically resolves the base folder from any image path in the OID
#   - Raises RuntimeError if insufficient space is detected
# =============================================================================

from __future__ import annotations
import arcpy
import os
import shutil
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from utils.manager.config_manager import ConfigManager


def find_base_dir(dir_path: str, token: str) -> Optional[str]:
    """
    Finds the base directory in dir_path containing the token (case-insensitive).
    Returns the path up to and including the token, or None if not found.
    """
    idx = dir_path.lower().find(token.lower())
    return dir_path[: idx + len(token)] if idx != -1 else None


def get_folder_size(path: str, config: "ConfigManager") -> int:
    """
    Calculates the total size of all files within a directory, including subdirectories.

    Args:
        path: Path to the directory whose total file size will be computed.
        config (ConfigManager): ConfigManager instance.

    Returns:
        The cumulative size in bytes of all files contained in the directory and its subdirectories.
    """
    total = 0
    all_files = list(Path(path).rglob("*"))
    files_only = [f for f in all_files if f.is_file()]
    with config.get_progressor(total=len(files_only), label="Calculating folder size...") as prog:
        for i, file in enumerate(files_only, start=1):
            total += file.stat().st_size
            prog.update(i)
    return total


def check_sufficient_disk_space(
    oid_fc: str,
    cfg: "ConfigManager",
    cursor_factory=None,
    disk_usage_func=None,
    folder_size_func=None
) -> bool:
    """
    Verify available disk space against the configured original image folder.

    Determines the total size of the feature-class-linked original image directory,
    applies the configured safety buffer ratio, and compares required space to the
    drive's available free space.

    Parameters:
        oid_fc (str): Path to the Oriented Imagery Dataset feature class.
        cfg (ConfigManager): Configuration manager providing settings and logger.
        cursor_factory (callable, optional): Injectable search-cursor factory used
            to read ImagePath values (primarily for testing).
        disk_usage_func (callable, optional): Injectable function used to retrieve
            disk usage (primarily for testing).
        folder_size_func (callable, optional): Injectable function used to compute
            folder size (primarily for testing).

    Returns:
        bool: True when validation succeeds.

    Raises:
        ValueError: If required config/path-derived values are invalid (for example,
            missing ImagePath values or missing configured original-folder token in
            the image path).
        RuntimeError: If available disk space is insufficient, or if disk/folder
            size checks fail and a RuntimeError is raised by internal/propagated
            checks.

    Notes:
        Exceptions from injected dependencies and internal checks are allowed to
        propagate so callers can handle them.
    """
    logger = cfg.get_logger()

    if not cfg.get("disk_space.check_enabled", True):
        logger.info("Disk space check is disabled via config.")
        return True

    buffer_ratio: float = cfg.get("disk_space.min_buffer_ratio", 1.1)

    # Dependency injection for testability
    cursor_factory = cursor_factory or (lambda fc, fields: arcpy.da.SearchCursor(fc, fields))
    disk_usage_func = disk_usage_func or shutil.disk_usage

    # Size ONLY the images the OID actually references — i.e. exactly what Rename
    # copies. In pre-thin (manifest) mode the OID holds just the kept set, while the
    # source `original/` folder holds the FULL un-thinned set; sizing the folder would
    # over-estimate by the thinning ratio and falsely fail this check.
    total_bytes = 0
    counted = 0
    missing = 0
    sample_path: Optional[str] = None
    with cursor_factory(oid_fc, ["ImagePath"]) as cursor:
        for row in cursor:
            image_path = row[0]
            if not image_path:
                continue
            if sample_path is None:
                sample_path = image_path
            try:
                total_bytes += os.path.getsize(image_path)
                counted += 1
            except OSError:
                missing += 1

    if counted == 0:
        logger.error(
            f"No readable image files referenced by the OID feature class: {oid_fc}",
            error_type=ValueError, indent=1)
        raise ValueError(f"No readable image files referenced by the OID feature class: {oid_fc}")
    if missing:
        logger.warning(
            f"{missing:,} OID ImagePath(s) were not found on disk while sizing; "
            "the estimate excludes them.", indent=1)

    estimated_required = int(total_bytes * buffer_ratio)

    # Free space is needed where Rename WRITES the copies (cfg.paths.renamed); fall
    # back to the source-image drive if the renamed path can't be resolved.
    drive_root: Optional[str] = None
    try:
        drive_root = Path(str(cfg.paths.renamed)).anchor
    except Exception:
        drive_root = None
    if not drive_root:
        drive_root = Path(os.path.dirname(sample_path)).anchor
    free_space = disk_usage_func(drive_root).free

    logger.debug(f"Disk check drive: {drive_root}", indent=1)
    logger.debug(f"OID images sized: {counted:,} ({total_bytes / 1e9:.2f} GB)", indent=1)
    logger.debug(f"Estimated required: {estimated_required / 1e9:.2f} GB (x{buffer_ratio} buffer)", indent=1)
    logger.debug(f"Available: {free_space / 1e9:.2f} GB", indent=1)

    if free_space < estimated_required:
        logger.error("Insufficient disk space.", indent=1)
        logger.error(f"Needed (with buffer): {estimated_required / 1e9:.2f} GB", indent=2)
        logger.error(f"Available: {free_space / 1e9:.2f} GB", indent=2)
        logger.error("Cannot continue.", indent=1, error_type=RuntimeError)

    return True