import pytest
from pathlib import Path
from utils.manager.path_manager import PathManager

@pytest.fixture
def tmp_script_base(tmp_path):
    # Simulate repo root with required pyt file
    script_base = tmp_path / "repo"
    script_base.mkdir()
    (script_base / "rmi_360_workflow.pyt").touch()
    (script_base / "configs").mkdir()
    (script_base / "aws_lambdas").mkdir()
    (script_base / "templates").mkdir()
    return script_base

@pytest.fixture
def minimal_config():
    return {
        "oid_schema_template": {
            "template": {
                "templates_dir": "templates"
            }
        },
        "orchestrator": {
            "backup_folder": "backups"
        },
        "logs": {
            "log_folder": "logs"
        }
    }

def test_init_valid_script_base(tmp_script_base, minimal_config):
    pm = PathManager(project_base=tmp_script_base, config=minimal_config, script_base=tmp_script_base)
    assert pm.script_base == tmp_script_base
    assert pm.project_base == tmp_script_base

def test_init_invalid_script_base(tmp_path, minimal_config):
    # No rmi_360_workflow.pyt present
    bad_base = tmp_path / "bad_repo"
    bad_base.mkdir()
    with pytest.raises(ValueError):
        PathManager(project_base=bad_base, config=minimal_config, script_base=bad_base)

def test_templates_path(tmp_script_base, minimal_config):
    pm = PathManager(project_base=tmp_script_base, config=minimal_config, script_base=tmp_script_base)
    assert pm.templates == tmp_script_base / "templates"

def test_configs_path(tmp_script_base, minimal_config):
    pm = PathManager(project_base=tmp_script_base, config=minimal_config, script_base=tmp_script_base)
    assert pm.configs == tmp_script_base / "configs"

def test_lambdas_path(tmp_script_base, minimal_config):
    pm = PathManager(project_base=tmp_script_base, config=minimal_config, script_base=tmp_script_base)
    assert pm.lambdas == tmp_script_base / "aws_lambdas"

def test_primary_config_path(tmp_script_base, minimal_config):
    pm = PathManager(project_base=tmp_script_base, config=minimal_config, script_base=tmp_script_base)
    assert pm.primary_config_path == tmp_script_base / "configs" / "config.yaml"

def test_fallback_config_path(tmp_script_base, minimal_config):
    pm = PathManager(project_base=tmp_script_base, config=minimal_config, script_base=tmp_script_base)
    assert pm.fallback_config_path == tmp_script_base / "configs" / "config.sample.yaml"

def test_backups_path(tmp_script_base, minimal_config):
    pm = PathManager(project_base=tmp_script_base, config=minimal_config, script_base=tmp_script_base)
    assert pm.backups == tmp_script_base / "backups"

def test_config_overrides(tmp_script_base):
    # Override templates and backups via config
    config = {
        "oid_schema_template": {"template": {"templates_dir": "custom_templates"}},
        "orchestrator": {"backup_folder": "custom_backups"}
    }
    pm = PathManager(project_base=tmp_script_base, config=config, script_base=tmp_script_base)
    assert pm.templates == tmp_script_base / "custom_templates"
    assert pm.backups == tmp_script_base / "custom_backups"

def test_empty_config(tmp_script_base):
    pm = PathManager(project_base=tmp_script_base, config={}, script_base=tmp_script_base)
    # Should fallback to defaults
    assert pm.templates == tmp_script_base / "templates"
    assert pm.backups == tmp_script_base / "backups"
