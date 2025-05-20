from types import SimpleNamespace
from utils.validators.validate_full_config import validate_full_config
from utils.shared.rmi_exceptions import ConfigValidationError

class DummyLogger:
    def __init__(self):
        self.errors = []
        self.infos = []
    def error(self, msg, error_type=None):
        self.errors.append((msg, error_type))
    def info(self, msg):
        self.infos.append(msg)

class DummyConfigManager(dict):
    def __init__(self, values, tool_validators=None):
        super().__init__(values)
        self._logger = DummyLogger()
        self.TOOL_VALIDATORS = tool_validators or {}
    def get_logger(self):
        return self._logger
    def get(self, key, default=None):
        return self[key] if key in self else default

# Mocks for imported validators
import sys
mod = sys.modules
mod['utils.manager.config_manager'] = SimpleNamespace(SUPPORTED_SCHEMA_VERSIONS={'1.0.0', '1.0.1'})
class DummyConfigValidationError(Exception):
    pass
mod['utils.exceptions'] = SimpleNamespace(ConfigValidationError=DummyConfigValidationError)

def dummy_validate_type(val, name, typ, cfg):
    if name == "debug_messages" and not isinstance(val, bool):
        raise ConfigValidationError("debug_messages must be bool")

def dummy_validate_config_section(cfg, section, _):
    # Simulate missing section by checking if section exists in cfg
    if section not in cfg:
        raise ConfigValidationError(f"Missing section: {section}")

def dummy_validate_expression_block(block, fields, cfg, typ, section):
    if block is None:
        raise ConfigValidationError("spatial_ref missing")

# Patch the validators in the target module
def patch_validators(monkeypatch):
    monkeypatch.setattr('utils.validate_full_config.validate_type', dummy_validate_type)
    monkeypatch.setattr('utils.validate_full_config.validate_config_section', dummy_validate_config_section)
    monkeypatch.setattr('utils.validate_full_config.validate_expression_block', dummy_validate_expression_block)

def test_valid_config(monkeypatch):
    patch_validators(monkeypatch)
    cfg = DummyConfigManager({
        'schema_version': '1.0.0',
        'debug_messages': True,
        'spatial_ref': {'gcs_horizontal_wkid': 1, 'vcs_vertical_wkid': 2, 'pcs_horizontal_wkid': 3},
        'logs': {}, 'project': {}, 'camera': {}, 'camera_offset': {}, 'executables': {}, 'oid_schema_template': {},
        'gps_smoothing': {}, 'image_output.filename_settings': {}, 'image_output.metadata_tags': {}, 'aws': {}, 'portal': {}, 'geocoding': {}
    })
    assert validate_full_config(cfg, logger=cfg.get_logger()) is True
    assert any('Full config validation passed' in msg for msg in cfg.get_logger().infos)

def test_invalid_schema_version(monkeypatch):
    patch_validators(monkeypatch)
    cfg = DummyConfigManager({'schema_version': 'bad', 'debug_messages': True, 'spatial_ref': {}, 'logs': {}, 'project': {}, 'camera': {}, 'camera_offset': {}, 'executables': {}, 'oid_schema_template': {}, 'gps_smoothing': {}, 'image_output.filename_settings': {}, 'image_output.metadata_tags': {}, 'aws': {}, 'portal': {}, 'geocoding': {}})
    assert validate_full_config(cfg, logger=cfg.get_logger()) is False
    assert any('Unsupported schema_version' in msg for msg, _ in cfg.get_logger().errors)

def test_debug_messages_type_error(monkeypatch):
    patch_validators(monkeypatch)
    cfg = DummyConfigManager({'schema_version': '1.0.0', 'debug_messages': 'not_bool', 'spatial_ref': {}, 'logs': {}, 'project': {}, 'camera': {}, 'camera_offset': {}, 'executables': {}, 'oid_schema_template': {}, 'gps_smoothing': {}, 'image_output.filename_settings': {}, 'image_output.metadata_tags': {}, 'aws': {}, 'portal': {}, 'geocoding': {}})
    assert validate_full_config(cfg, logger=cfg.get_logger()) is False
    assert any('debug_messages must be bool' in msg for msg, _ in cfg.get_logger().errors)

def test_missing_section(monkeypatch):
    patch_validators(monkeypatch)
    # Omit 'geocoding' section to simulate missing section
    cfg = DummyConfigManager({'schema_version': '1.0.0', 'debug_messages': True, 'spatial_ref': {}, 'logs': {}, 'project': {}, 'camera': {}, 'camera_offset': {}, 'executables': {}, 'oid_schema_template': {}, 'gps_smoothing': {}, 'image_output.filename_settings': {}, 'image_output.metadata_tags': {}, 'aws': {}, 'portal': {}})  # missing 'geocoding'
    assert validate_full_config(cfg, logger=cfg.get_logger()) is False
    assert any('Missing section' in msg for msg, _ in cfg.get_logger().errors)

def test_spatial_ref_error(monkeypatch):
    patch_validators(monkeypatch)
    cfg = DummyConfigManager({'schema_version': '1.0.0', 'debug_messages': True, 'spatial_ref': None, 'logs': {}, 'project': {}, 'camera': {}, 'camera_offset': {}, 'executables': {}, 'oid_schema_template': {}, 'gps_smoothing': {}, 'image_output.filename_settings': {}, 'image_output.metadata_tags': {}, 'aws': {}, 'portal': {}, 'geocoding': {}})
    assert validate_full_config(cfg, logger=cfg.get_logger()) is False
    assert any('spatial_ref missing' in msg for msg, _ in cfg.get_logger().errors)

def test_tool_validator_error(monkeypatch):
    patch_validators(monkeypatch)
    from utils.exceptions import ConfigValidationError
    def bad_validator(cfg):
        raise ConfigValidationError("tool failed")
    tool_validators = {'bad_tool': bad_validator}
    cfg = DummyConfigManager({'schema_version': '1.0.0', 'debug_messages': True, 'spatial_ref': {}, 'logs': {}, 'project': {}, 'camera': {}, 'camera_offset': {}, 'executables': {}, 'oid_schema_template': {}, 'gps_smoothing': {}, 'image_output.filename_settings': {}, 'image_output.metadata_tags': {}, 'aws': {}, 'portal': {}, 'geocoding': {}}, tool_validators=tool_validators)
    assert validate_full_config(cfg, logger=cfg.get_logger()) is False
    assert any('tool failed' in msg for msg, _ in cfg.get_logger().errors)
