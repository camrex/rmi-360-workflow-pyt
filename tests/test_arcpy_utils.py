import pytest
from utils.shared import arcpy_utils
from unittest.mock import MagicMock

def test_validate_fields_exist_all_present():
    arcpy_mod = MagicMock()
    arcpy_mod.ListFields.return_value = [MagicMock(name='A'), MagicMock(name='B')]
    for f, n in zip(arcpy_mod.ListFields.return_value, ['A', 'B']):
        f.name = n
    # Should not raise
    arcpy_utils.validate_fields_exist('fake_fc', ['A', 'B'], arcpy_mod=arcpy_mod)

def test_validate_fields_exist_missing():
    arcpy_mod = MagicMock()
    arcpy_mod.ListFields.return_value = [MagicMock(name='A')]
    arcpy_mod.ListFields.return_value[0].name = 'A'
    with pytest.raises(ValueError) as exc:
        arcpy_utils.validate_fields_exist('fake_fc', ['A', 'B'], arcpy_mod=arcpy_mod)
    assert 'Missing required field' in str(exc.value)

def test_validate_fields_exist_logger():
    arcpy_mod = MagicMock()
    arcpy_mod.ListFields.return_value = [MagicMock(name='A')]
    arcpy_mod.ListFields.return_value[0].name = 'A'
    logger = MagicMock()
    arcpy_utils.validate_fields_exist('fake_fc', ['A', 'B'], logger=logger, arcpy_mod=arcpy_mod)
    logger.error.assert_called()

def test_str_to_bool():
    assert arcpy_utils.str_to_bool(True) is True
    assert arcpy_utils.str_to_bool(False) is False
    assert arcpy_utils.str_to_bool('true') is True
    assert arcpy_utils.str_to_bool('YES') is True
    assert arcpy_utils.str_to_bool('0') is False
    assert arcpy_utils.str_to_bool('off') is False
    assert arcpy_utils.str_to_bool(None) is False

def test_str_to_value_basic_types():
    assert arcpy_utils.str_to_value('123', int) == 123
    assert arcpy_utils.str_to_value('3.14', float) == 3.14
    assert arcpy_utils.str_to_value('bad', int) is None
    assert arcpy_utils.str_to_value(None, int) is None

def test_str_to_value_spatial_reference_success():
    arcpy_mod = MagicMock()
    DummySRType = type('SpatialReference', (), {})
    sr_instance = DummySRType()
    # Should return value if already a spatial reference
    assert arcpy_utils.str_to_value(sr_instance, 'spatial_reference', arcpy_mod=arcpy_mod, spatial_ref_type=DummySRType) is sr_instance
    # Should create new spatial reference from value
    arcpy_mod.SpatialReference.return_value = sr_instance
    result = arcpy_utils.str_to_value('4326', 'spatial_reference', arcpy_mod=arcpy_mod, spatial_ref_type=DummySRType)
    assert result == sr_instance

def test_str_to_value_spatial_reference_fail():
    arcpy_mod = MagicMock()
    DummySRType = type('SpatialReference', (), {})
    arcpy_mod.SpatialReference.side_effect = ValueError('fail')
    logger = MagicMock()
    result = arcpy_utils.str_to_value('bad', 'spatial_reference', logger=logger, arcpy_mod=arcpy_mod, spatial_ref_type=DummySRType)
    assert result is None
    logger.debug.assert_called()

def test_backup_oid_success():
    arcpy_mod = MagicMock()
    arcpy_mod.management.CreateFileGDB.return_value = None
    arcpy_mod.management.Copy.return_value = None
    arcpy_mod.Describe.return_value.name = 'test_fc'
    path_mod = MagicMock()
    path_mod.return_value.stem = 'test_fc'
    datetime_mod = MagicMock()
    datetime_mod.now.return_value.strftime.return_value = '20250514_1234'
    cfg = MagicMock()
    logger = MagicMock()
    backup_gdb = MagicMock()
    backup_gdb.parent.mkdir.return_value = None
    backup_gdb.exists.return_value = False
    backup_gdb.name = 'gdb_name'
    cfg.paths.backup_gdb = backup_gdb
    cfg.get_logger.return_value = logger
    arcpy_utils.backup_oid('fc', 'step', cfg, arcpy_mod=arcpy_mod, path_mod=path_mod, datetime_mod=datetime_mod, logger=logger)
    arcpy_mod.management.CreateFileGDB.assert_called()
    arcpy_mod.management.Copy.assert_called()
    logger.info.assert_called()

def test_backup_oid_exception():
    arcpy_mod = MagicMock()
    arcpy_mod.management.CreateFileGDB.side_effect = Exception('fail')
    path_mod = MagicMock()
    datetime_mod = MagicMock()
    cfg = MagicMock()
    logger = MagicMock()
    backup_gdb = MagicMock()
    backup_gdb.parent.mkdir.return_value = None
    backup_gdb.exists.return_value = False
    backup_gdb.name = 'gdb_name'
    cfg.paths.backup_gdb = backup_gdb
    cfg.get_logger.return_value = logger
    arcpy_utils.backup_oid('fc', 'step', cfg, arcpy_mod=arcpy_mod, path_mod=path_mod, datetime_mod=datetime_mod, logger=logger)
    logger.warning.assert_called()
