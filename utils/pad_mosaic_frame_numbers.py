# =============================================================================
# 🔢 Frame Number Padding Utility (utils/pad_mosaic_frame_numbers.py)
# -----------------------------------------------------------------------------
# Purpose:             Renames image files to use zero-padded 6-digit frame numbers for consistency
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Recursively walks a folder structure and renames all `.jpg` files that match a frame
#   naming pattern ending in `_###.jpg`, padding each frame number to 6 digits. Used to
#   normalize Mosaic Processor outputs prior to enhancement and OID population.
#
# File Location:        /utils/pad_mosaic_frame_numbers.py
# Called By:            utils/mosaic_processor.py
# Int. Dependencies:    arcpy_utils
# Ext. Dependencies:    os, re
#
# Documentation:
#   See: docs_legacy/UTILITIES.md
#
# Notes:
#   - Skips files already correctly padded
#   - Logs renaming steps and count via `log_message`
# =============================================================================

__all__ = ["pad_frame_numbers"]

import os
import re
from utils.arcpy_utils import log_message


def pad_frame_numbers(output_dir: str, messages=None) -> int:
    """
    Recursively renames JPG files to zero-pad numeric frame numbers to 6 digits.
    
    Scans the specified directory and its subdirectories for JPG files whose names end with an underscore followed by a
    numeric frame number. Files with frame numbers shorter than 6 digits are renamed to use zero-padded 6-digit numbers.
    Returns the total number of files renamed.
    
    Args:
        output_dir: Root directory to search for JPG files.
        messages: Optional ArcPy-compatible message object for logging.
    
    Returns:
        The number of files that were renamed.
    """
    renamed_count = 0

    log_message(f"Checking for frame number padding in: {output_dir}", messages)

    for root, dirs, files in os.walk(output_dir):
        for f in files:
            if f.lower().endswith(".jpg"):
                match = re.match(r"^(.*_)(\d+)\.jpg$", f)
                if match:
                    prefix, num = match.groups()
                    if len(num) < 6:
                        padded = num.zfill(6)
                        new_name = f"{prefix}{padded}.jpg"
                        old_path = os.path.join(root, f)
                        new_path = os.path.join(root, new_name)
                        os.rename(old_path, new_path)
                        renamed_count += 1
                        log_message(f"Renamed: {f} → {new_name}", messages, level="debug")

    log_message(f"Total files renamed: {renamed_count}", messages)
    return renamed_count
