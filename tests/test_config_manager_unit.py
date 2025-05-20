# =============================================================================
# 🧪 Unit Tests: ConfigManager
# -----------------------------------------------------------------------------
# Purpose:     Thorough unit tests for ConfigManager (utils/manager/config_manager.py)
# Framework:   Pytest
# Author:      Cascade AI (2025-05-14)
# =============================================================================
import pytest
import tempfile
import os
import yaml
from pathlib import Path
from utils.manager.config_manager import ConfigManager, ConfigValidationError

# --- Minimal valid config for testing ---
MINIMAL_CONFIG = {
    "schema_version": "1.0.1",
    "logs": {"process_log": "log.txt"},
    "project": {"slug": "testslug"}
}

@pytest.fixture
def tmp_config_file(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(MINIMAL_CONFIG, f)
    return str(cfg_path)

@pytest.fixture
def tmp_invalid_yaml_file(tmp_path):
    bad_path = tmp_path / "bad.yaml"
    with open(bad_path, "w", encoding="utf-8") as f:
        f.write(": bad: : :\n")  # invalid YAML
    return str(bad_path)

@pytest.fixture
def tmp_bad_schema_file(tmp_path):
    bad_schema = dict(MINIMAL_CONFIG)
    bad_schema["schema_version"] = "999.9.9"
    bad_path = tmp_path / "bad_schema.yaml"
    with open(bad_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(bad_schema, f)
    return str(bad_path)

# --- Tests ---
def test_load_and_access(tmp_config_file, tmp_path):
    cfg = ConfigManager.from_file(tmp_config_file, project_base=tmp_path)
    assert cfg.get("logs.process_log") == "log.txt"
    assert cfg.get("project.slug") == "testslug"
    assert cfg.get("nonexistent.key", default=123) == 123
    assert cfg.has_section("logs") is True
    assert cfg.has_section("not_a_section") is False
    assert "logs" in cfg.get_sections()
    assert isinstance(cfg.raw, dict)
    assert cfg.source_path.endswith("config.yaml")
    # PathManager and LogManager
    assert cfg.paths is not None
    assert cfg.get_logger() is not None
    assert cfg.get_progressor(total=5) is not None


def test_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(FileNotFoundError):
        ConfigManager.from_file(str(missing), project_base=tmp_path)


def test_invalid_yaml(tmp_invalid_yaml_file, tmp_path):
    with pytest.raises(ValueError):
        ConfigManager.from_file(tmp_invalid_yaml_file, project_base=tmp_path)


def test_bad_schema(tmp_bad_schema_file, tmp_path):
    with pytest.raises(RuntimeError):
        ConfigManager.from_file(tmp_bad_schema_file, project_base=tmp_path)


def test_validate_and_tool_dispatch(tmp_config_file, tmp_path, mocker):
    cfg = ConfigManager.from_file(tmp_config_file, project_base=tmp_path)
    # Patch a validator to check dispatch
    mock_validator = mocker.patch("utils.validators.mosaic_processor_validator.validate")
    cfg.TOOL_VALIDATORS["mosaic_processor"] = mock_validator
    cfg.validate_tool_config("mosaic_processor")
    mock_validator.assert_called_once_with(cfg)
    # Unknown tool
    with pytest.raises(Exception):
        cfg.validate_tool_config("not_a_tool")


def test_resolve_expression(tmp_config_file, tmp_path, mocker):
    cfg = ConfigManager.from_file(tmp_config_file, project_base=tmp_path)
    mock_resolve = mocker.patch("utils.manager.config_manager.resolve_expression", return_value="resolved")
    assert cfg.resolve("logs.process_log") == "resolved"
    mock_resolve.assert_called()


def test_paths_and_logger_exceptions(tmp_config_file, tmp_path):
    cfg = ConfigManager.from_file(tmp_config_file, project_base=tmp_path)
    # Break internals to test exceptions
    cfg._paths = None
    with pytest.raises(RuntimeError):
        _ = cfg.paths
    cfg._lm = None
    with pytest.raises(RuntimeError):
        _ = cfg.get_logger()
