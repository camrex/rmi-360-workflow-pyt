# =============================================================================
# 🧪 Test Script: test_config_manager.py
# -----------------------------------------------------------------------------
# Purpose:     Full integration test for ConfigManager
#
# Description:
#   - Verifies loading, validation, key access, and expression resolution
#   - Tests has_section, get_sections, and PathManager/LogManager access
#
# Framework:   Pytest
# Author:      RMI Valuation, LLC
# Created:     2025-05-11
# =============================================================================

import pytest
from pathlib import Path
from utils.manager.config_manager import ConfigManager

# === Configurable Inputs ===
CONFIG_FILE = r"D:\RMI Valuation LLC\RMI - Development\RMI Mosaic 360 Tools Test AGP\Project\config2.yaml"
PROJECT_FOLDER = r"D:\RMI Valuation LLC\RMI - Development\RMI Mosaic 360 Tools Test AGP\Project"

@pytest.mark.integration
def test_config_manager_full():
    messages = []

    # Initialize
    cfg = ConfigManager.from_file(CONFIG_FILE, project_base=PROJECT_FOLDER, messages=messages, debug=True)

    # --- Schema Validation ---
    cfg.validate(tool="enhance_images", messages=messages)

    # --- Key Resolution ---
    assert isinstance(cfg.get("logs.process_log"), str)
    assert cfg.get("nonexistent.key", default="fallback") == "fallback"

    # --- Expression Resolution ---
    assert isinstance(cfg.resolve("config.project.slug"), str)

    # --- Section Checks ---
    assert cfg.has_section("logs") is True
    assert cfg.has_section("this_should_not_exist") is False

    sections = cfg.get_sections()
    assert isinstance(sections, list)
    assert "logs" in sections

    # --- PathManager Access ---
    pm = cfg.paths
    assert isinstance(pm.logs, Path)
    assert isinstance(pm.primary_config_path, Path)

    # --- LogManager Access ---
    log = cfg.get_logger(messages=messages)
    log.info("✅ ConfigManager test suite passed")

    print("\n✅ ConfigManager Test Output:")
    print("logs.process_log:", cfg.get("logs.process_log"))
    print("Resolved slug:", cfg.resolve("config.project.slug"))
    print("Available sections:", sections)

    if messages:
        print("\nMessages:")
        for m in messages:
            print("-", m)
