# =============================================================================
# ⚙️ Executable Availability Checker (utils/executable_utils.py)
# -----------------------------------------------------------------------------
# Purpose:             Verifies availability of external command-line tools (e.g., ExifTool)
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Attempts to invoke a given executable with test arguments (e.g., `-ver`) to determine
#   availability and proper installation. Used to validate dependencies such as ExifTool
#   or FFmpeg before launching tagging or enhancement workflows.
#
# File Location:        /utils/executable_utils.py
# Called By:            apply_exif_metadata.py, enhance_images.py
# Int. Dependencies:    None
# Ext. Dependencies:    subprocess, typing
#
# Documentation:
#   See: docs/UTILITIES.md
#
# Notes:
#   - Handles FileNotFoundError, PermissionError, and general OS errors gracefully
# =============================================================================

import subprocess
from typing import Optional


def is_executable_available(exe_path: str, test_args: Optional[list[str]] = None) -> bool:
    """
    Check whether a given executable runs successfully with a basic test command.

    This function attempts to execute the provided executable with the specified test arguments.
    It returns True if the command completes successfully (exit code 0), indicating that the
    executable is available and functional.

    Args:
        exe_path (str): Full path to the executable (e.g., "C:/Program Files/ExifTool/exiftool.exe").
        test_args (Optional[list[str]]): Command-line arguments used to test the executable.
            Defaults to ["-ver"], commonly used for tools like ExifTool or FFmpeg.

    Returns:
        bool: True if the executable runs and returns exit code 0; False otherwise.
    """
    if test_args is None:
        test_args = ["-ver"]

    try:
        result = subprocess.run([exe_path] + test_args,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                                check=False)
        return result.returncode == 0
    except (FileNotFoundError, PermissionError, OSError):
        return False
