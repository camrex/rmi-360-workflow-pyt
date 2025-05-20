import pytest
from unittest.mock import MagicMock, patch
from utils import create_oid_feature_class

@patch('utils.schema_validator.load_field_registry')
@patch('arcpy.ListFields')
@patch('arcpy.Exists')
@patch('arcpy.oi.CreateOrientedImageryDataset')
def test_create_oriented_imagery_dataset_success(mock_create_oid, mock_exists, mock_list_fields, mock_load_registry):
    mock_exists.return_value = False
    mock_list_fields.return_value = [type('Field', (), {'name': 'FIELD1'})(), type('Field', (), {'name': 'FIELD2'})()]
    mock_load_registry.return_value = {
        'field1': {'name': 'FIELD1', 'category': 'standard'},
        'field2': {'name': 'FIELD2', 'category': 'not_applicable'}
    }
    cfg = MagicMock()
    cfg.get_logger.return_value = MagicMock()
    cfg.validate.return_value = True
    cfg.get.side_effect = lambda k, d=None: {"spatial_ref.gcs_horizontal_wkid": 4326, "spatial_ref.vcs_vertical_wkid": 5703}.get(k, d)
    cfg.paths = MagicMock()
    output_fc_path = 'somegdb.gdb/oid_fc'
    # Pass an int for spatial_reference to avoid isinstance issues
    result = create_oid_feature_class.create_oriented_imagery_dataset(cfg, output_fc_path, spatial_reference=4326)
    mock_create_oid.assert_called_once()
    assert result == output_fc_path

@patch('arcpy.Exists')
def test_create_oriented_imagery_dataset_already_exists(mock_exists):
    mock_exists.return_value = True
    cfg = MagicMock()
    logger = MagicMock()
    cfg.get_logger.return_value = logger
    cfg.validate.return_value = True
    cfg.paths = MagicMock()
    output_fc_path = 'somegdb.gdb/oid_fc'
    result = create_oid_feature_class.create_oriented_imagery_dataset(cfg, output_fc_path)
    logger.error.assert_called()
    assert result == output_fc_path
