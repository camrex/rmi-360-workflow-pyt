# =============================================================================
# 📁 Folder Statistics Utility (utils/folder_stats.py)
# -----------------------------------------------------------------------------
# Purpose:             Calculates file counts and total size of image directories for reporting
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Recursively walks a given directory to count image files (default: .jpg) and compute their
#   cumulative size. Formats byte totals into human-readable strings using `humanize`. Used for
#   reporting logs and disk space estimation in enhancement and renaming steps.
#
# File Location:        /utils/folder_stats.py
# Called By:            utils/check_disk_space.py, reporting
# Int. Dependencies:    None
# Ext. Dependencies:    os, humanize, pathlib
#
# Documentation:
#   See: docs_legacy/UTILITIES.md
#
# Notes:
#   - Recursively matches any extensions provided via argument (default: ['.jpg'])
#   - Skips invalid or missing folders gracefully (returns 0 count and "0 B")
# =============================================================================


import os
import humanize
from pathlib import Path


def folder_stats(path, extensions=None):
    """
    Calculate statistics for JPG files in a directory.

    Args:
        path (str): Path to the directory to analyze
        extensions (list, optional): List of file extensions to include (default: ['.jpg'])

    Returns:
        tuple: (number_of_files, human_readable_size)
            - number_of_files (int): Count of matching files
            - human_readable_size (str): Total size in human-readable format
    """
    if not path or not os.path.exists(path):
        return 0, "0 B"

    if extensions is None:
        extensions = ['.jpg']
    p = Path(path)
    jpg_files = []
    for ext in extensions:
        jpg_files.extend(list(p.rglob(f"*{ext}")))  # ✅ Recursively find all .jpg files
    total_size = sum(f.stat().st_size for f in jpg_files)
    return len(jpg_files), humanize.naturalsize(total_size, binary=True)
