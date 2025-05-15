# =============================================================================
# 🧪 Test Script: test_path_manager_resolution.py
# -----------------------------------------------------------------------------
# Purpose:     Integration test to verify path resolution using PathManager.
#
# Description:
#   - Loads config from a test project folder
#   - Initializes PathManager
#   - Resolves and prints all core paths
#   - Ensures each path property is accessible and well-formed
#
# Framework:   Pytest
# Author:      RMI Valuation, LLC
# Created:     2025-05-10
# =============================================================================

import pytest
from pathlib import Path
from utils.manager.path_manager import PathManager
from utils.manager.config_manager import ConfigManager

# === Configurable Inputs ===
CONFIG_FILE = r"D:\RMI Valuation LLC\RMI - Development\RMI Mosaic 360 Tools Test AGP\Project\config2.yaml"
PROJECT_FOLDER = r"D:\RMI Valuation LLC\RMI - Development\RMI Mosaic 360 Tools Test AGP\Project"

@pytest.mark.integration
def test_path_manager_resolution():
    messages = []

    cfg = ConfigManager.from_file(
        path=CONFIG_FILE,
        project_base=PROJECT_FOLDER,
        messages=messages
    )

    pm = PathManager(project_base=Path(PROJECT_FOLDER), config=cfg)

    attributes = [
    "script_base", "project_base",
    "templates", "configs", "lambdas",
    "primary_config_path", "fallback_config_path",
    "backups", "backup_gdb", "logs", "report",
    "panos", "original", "enhanced", "renamed",
    "oid_schema_gdb", "oid_field_registry", "oid_schema_template_name",
    "geoloc500_config_path", "geocustom_config_path",
    "exiftool_exe", "mosaic_processor_exe", "mosaic_processor_grp"
    ]

    print("\n✅ PathManager Resolution Test Output:")
    for attr in attributes:
        try:
            val = getattr(pm, attr)
            assert val is None or isinstance(val, (str, Path)), f"{attr} has invalid type"
            print(f"{attr:30}: {val}")
        except Exception as e:
            print(f"{attr:30}: ERROR - {e}")
            assert False, f"Failed to resolve {attr}: {e}"
    # Optional additional checks
    assert isinstance(pm.get_log_file_path("enhance_log"), Path)
    assert isinstance(pm.check_exiftool_available(), bool)
    assert isinstance(pm.check_mosaic_processor_available(), bool)


    if messages:
        print("\nMessages:")
        for m in messages:
            print("-", m)
