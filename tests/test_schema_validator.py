import pytest
from unittest.mock import MagicMock, patch
from utils import schema_validator

class DummyConfigValidationError(Exception):
    pass

def make_cfg(extra_get=None, auto_create=False):
    cfg = MagicMock()
    cfg.get_logger.return_value = MagicMock()
    def get_side_effect(k, d=None):
        base = {'oid_schema_template.esri_default.not_applicable': True,
                'oid_schema_template.template.auto_create_oid_template': auto_create}
        if extra_get:
            base.update(extra_get)
        return base.get(k, d)
    cfg.get.side_effect = get_side_effect
    cfg.paths.oid_schema_template_path = 'some_path/oid_schema_template'
    cfg.get_progressor.return_value.__enter__.return_value = MagicMock()
    cfg.get_progressor.return_value.__exit__.return_value = None
    return cfg

@patch('arcpy.Exists')
@patch('arcpy.ListFields')
@patch('utils.schema_validator.load_field_registry')
def test_validate_oid_template_schema_missing_fields(mock_load_registry, mock_list_fields, mock_exists):
    mock_exists.return_value = True
    mock_list_fields.return_value = [type('Field', (), {'name': 'FIELD1'})(), type('Field', (), {'name': 'FIELD2'})()]
    mock_load_registry.return_value = {
        'field1': {'name': 'FIELD1', 'category': 'standard'},
        'field2': {'name': 'FIELD2', 'category': 'not_applicable'},
        'field3': {'name': 'FIELD3', 'category': 'standard'}
    }
    cfg = make_cfg()
    with patch('utils.schema_validator.ConfigValidationError', DummyConfigValidationError):
        with pytest.raises(DummyConfigValidationError):
            schema_validator.validate_oid_template_schema(cfg)

@patch('arcpy.Exists')
@patch('arcpy.ListFields')
@patch('utils.schema_validator.load_field_registry')
def test_validate_oid_template_schema_all_fields_present(mock_load_registry, mock_list_fields, mock_exists):
    mock_exists.return_value = True
    mock_list_fields.return_value = [type('Field', (), {'name': 'FIELD1'})(), type('Field', (), {'name': 'FIELD2'})(), type('Field', (), {'name': 'FIELD3'})()]
    mock_load_registry.return_value = {
        'field1': {'name': 'FIELD1', 'category': 'standard'},
        'field2': {'name': 'FIELD2', 'category': 'not_applicable'},
        'field3': {'name': 'FIELD3', 'category': 'standard'}
    }
    cfg = make_cfg()
    result = schema_validator.validate_oid_template_schema(cfg)
    assert result is True

@patch('arcpy.Exists')
def test_validate_oid_template_schema_missing_template(mock_exists):
    mock_exists.return_value = False
    cfg = make_cfg()
    with patch('utils.schema_validator.ConfigValidationError', DummyConfigValidationError):
        with pytest.raises(FileNotFoundError):
            schema_validator.validate_oid_template_schema(cfg)

@patch('arcpy.Exists')
@patch('arcpy.ListFields')
@patch('utils.schema_validator.load_field_registry')
@patch('utils.schema_validator.create_oid_schema_template')
def test_ensure_valid_oid_schema_template_auto_create(mock_create, mock_load_registry, mock_list_fields, mock_exists):
    # Fail first, then succeed after auto-create
    mock_exists.side_effect = [False, True]
    mock_list_fields.return_value = [type('Field', (), {'name': 'FIELD1'})(), type('Field', (), {'name': 'FIELD2'})(), type('Field', (), {'name': 'FIELD3'})()]
    mock_load_registry.return_value = {
        'field1': {'name': 'FIELD1', 'category': 'standard'},
        'field2': {'name': 'FIELD2', 'category': 'not_applicable'},
        'field3': {'name': 'FIELD3', 'category': 'standard'}
    }
    cfg = make_cfg(auto_create=True)
    with patch('utils.schema_validator.ConfigValidationError', DummyConfigValidationError):
        schema_validator.ensure_valid_oid_schema_template(cfg)
    assert mock_create.called

@patch('arcpy.Exists')
@patch('arcpy.ListFields')
@patch('utils.schema_validator.load_field_registry')
def test_ensure_valid_oid_schema_template_no_auto_create(mock_load_registry, mock_list_fields, mock_exists):
    mock_exists.return_value = False
    mock_list_fields.return_value = []
    mock_load_registry.return_value = {}
    cfg = make_cfg(auto_create=False)
    with patch('utils.schema_validator.ConfigValidationError', DummyConfigValidationError):
        schema_validator.ensure_valid_oid_schema_template(cfg)
    # Should not raise, just log error and return
    assert cfg.get_logger.return_value.error.called, "Error should be logged when template is missing and auto_create is False"
