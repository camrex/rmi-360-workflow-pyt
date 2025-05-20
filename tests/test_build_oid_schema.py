from unittest.mock import MagicMock
from utils import build_oid_schema


def test_create_oid_schema_template_success():
    # Mocks for arcpy management functions
    arcpy_mod = MagicMock()
    arcpy_mod.Exists.side_effect = [False, True, False, False]
    arcpy_mod.management.CreateFileGDB.return_value = None
    arcpy_mod.management.CreateTable.return_value = None
    arcpy_mod.management.AddField.return_value = None
    arcpy_mod.management.Rename.return_value = None
    arcpy_mod.ListFields.return_value = []
    # Registry loader mock
    registry_loader = MagicMock(return_value={
        'field1': {'name': 'FIELD1', 'type': 'TEXT', 'category': 'standard'},
        'field2': {'name': 'FIELD2', 'type': 'DOUBLE', 'category': 'not_applicable'}
    })
    # OS mock
    os_mod = MagicMock()
    os_mod.path.exists.return_value = False
    os_mod.makedirs.return_value = None
    os_mod.path.basename.side_effect = lambda p: p.split('/')[-1]
    # Config mock
    cfg = MagicMock()
    logger = MagicMock()
    cfg.get_logger.return_value = logger
    cfg.validate.return_value = True
    cfg.get.side_effect = lambda k, d=None: {'oid_schema_template.esri_default': {'standard': True, 'not_applicable': True}}.get(k, d)
    cfg.paths.templates = 'templates_dir'
    cfg.paths.oid_schema_gdb = 'templates_dir/oid_schema.gdb'
    cfg.paths.oid_schema_template_path = 'templates_dir/oid_schema.gdb/oid_schema_template'
    cfg.paths.oid_schema_template_name = 'oid_schema_template'
    result = build_oid_schema.create_oid_schema_template(
        cfg,
        arcpy_mod=arcpy_mod,
        os_mod=os_mod,
        registry_loader=registry_loader,
        logger=logger
    )
    assert arcpy_mod.management.CreateTable.called
    assert arcpy_mod.management.AddField.call_count >= 2
    assert result == cfg.paths.oid_schema_template_path

def test_create_oid_schema_template_add_field_error():
    arcpy_mod = MagicMock()
    arcpy_mod.Exists.side_effect = [False, True, False, False]
    arcpy_mod.management.CreateFileGDB.return_value = None
    arcpy_mod.management.CreateTable.return_value = None
    arcpy_mod.management.AddField.side_effect = Exception('fail')
    arcpy_mod.management.Rename.return_value = None
    arcpy_mod.ListFields.return_value = []
    registry_loader = MagicMock(return_value={
        'field1': {'name': 'FIELD1', 'type': 'TEXT', 'category': 'standard'},
    })
    os_mod = MagicMock()
    os_mod.path.exists.return_value = False
    os_mod.makedirs.return_value = None
    os_mod.path.basename.side_effect = lambda p: p.split('/')[-1]
    cfg = MagicMock()
    logger = MagicMock()
    cfg.get_logger.return_value = logger
    cfg.validate.return_value = True
    cfg.get.side_effect = lambda k, d=None: {'oid_schema_template.esri_default': {'standard': True, 'not_applicable': True}}.get(k, d)
    cfg.paths.templates = 'templates_dir'
    cfg.paths.oid_schema_gdb = 'templates_dir/oid_schema.gdb'
    cfg.paths.oid_schema_template_path = 'templates_dir/oid_schema.gdb/oid_schema_template'
    cfg.paths.oid_schema_template_name = 'oid_schema_template'
    result = build_oid_schema.create_oid_schema_template(
        cfg,
        arcpy_mod=arcpy_mod,
        os_mod=os_mod,
        registry_loader=registry_loader,
        logger=logger
    )
    assert logger.warning.called
    assert result == cfg.paths.oid_schema_template_path
