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
import tempfile
import shutil
from pathlib import Path
from utils.manager.config_manager import ConfigManager

# === Configurable Inputs ===
CONFIG_FILE = str(Path(__file__).parent.parent / "configs" / "config.sample.yaml")

@pytest.fixture
def temp_dir():
    dir = tempfile.mkdtemp()
    yield dir
    shutil.rmtree(dir)

@pytest.mark.integration
def test_config_manager_full(temp_dir):
    messages = []

    # Initialize
    cfg = ConfigManager.from_file(CONFIG_FILE, project_base=temp_dir, messages=messages)

    # --- Schema Validation ---
    cfg.validate(tool="enhance_images")

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

@pytest.mark.integration
def test_config_manager_invalid_config(temp_dir):
    messages = []
    invalid_config = Path(temp_dir) / "invalid_config.yaml"
    with open(invalid_config, "w") as f:
        f.write("Invalid YAML")

    with pytest.raises((ValueError, RuntimeError)):
        ConfigManager.from_file(invalid_config, project_base=temp_dir, messages=messages)

@pytest.mark.integration
def test_config_manager_missing_config(temp_dir):
    messages = []
    missing_config = Path(temp_dir) / "missing_config.yaml"

    with pytest.raises(FileNotFoundError):
        ConfigManager.from_file(missing_config, project_base=temp_dir, messages=messages)

@pytest.mark.integration
def test_config_manager_invalid_schema(temp_dir):
    messages = []
    invalid_schema_config = Path(temp_dir) / "invalid_schema_config.yaml"
    with open(invalid_schema_config, "w") as f:
        f.write("schema: invalid")

    cfg = ConfigManager.from_file(invalid_schema_config, project_base=temp_dir, messages=messages)

    with pytest.raises(RuntimeError):
        cfg.validate(tool="enhance_images")
