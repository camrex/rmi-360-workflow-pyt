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
# Last Modified: 2025-05-20
# =============================================================================

import pytest
import os
from pathlib import Path
from utils.manager.path_manager import PathManager
from utils.manager.config_manager import ConfigManager

# === Configurable Inputs ===
TEST_DATA_DIR = Path(__file__).parent / "test_data"
CONFIG_FILE = os.getenv("TEST_CONFIG_PATH", str(TEST_DATA_DIR / "test_config.yaml"))
PROJECT_FOLDER = os.getenv("TEST_PROJECT_PATH", str(TEST_DATA_DIR))

@pytest.mark.integration
def test_path_manager_resolution():
    """
    Integration test that verifies PathManager resolves core project paths and tool availability.
    
    Loads configuration for the test project, instantiates PathManager, and iterates a set of core attributes asserting each attribute is either None or a str/Path. Also asserts that exiftool and mosaic processor availability checks return a boolean. Prints each resolved attribute and any diagnostic messages collected during configuration loading.
    """
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
    "panos", "original", "renamed",
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
            raise AssertionError(f"Failed to resolve {attr}: {e}") from e
    # Optional additional checks
    assert isinstance(pm.check_exiftool_available(), bool)
    assert isinstance(pm.check_mosaic_processor_available(), bool)


    if messages:
        print("\nMessages:")
        for m in messages:
            print("-", m)