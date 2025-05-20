import sys
import types
# Create arcpy package and submodules in sys.modules
arcpy_mod = types.ModuleType("arcpy")
arcpy_da = types.ModuleType("arcpy.da")
arcpy_mgmt = types.ModuleType("arcpy.management")
sys.modules["arcpy"] = arcpy_mod
sys.modules["arcpy.da"] = arcpy_da
sys.modules["arcpy.management"] = arcpy_mgmt

import pytest
from unittest.mock import patch, MagicMock
from utils.calculate_oid_attributes import enrich_oid_attributes

@pytest.fixture
def mock_cfg():
    cfg = MagicMock()
    cfg.get_logger.return_value = MagicMock()
    cfg.get_progressor.return_value.__enter__.return_value = MagicMock(update=lambda i: None)
    cfg.get_progressor.return_value.__exit__.return_value = False
    cfg.get.return_value = {}
    cfg.validate.return_value = True
    return cfg

def make_field(name):
    f = MagicMock()
    f.name = name
    return f

def test_enrich_oid_attributes_success(monkeypatch, mock_cfg):
    # Setup registry and config
    registry = {
        "CameraPitch": {"name": "CameraPitch", "oid_default": 90, "category": "standard"},
        "CameraRoll": {"name": "CameraRoll", "oid_default": 0, "category": "standard"},
        "NearDistance": {"name": "NearDistance", "oid_default": 2, "category": "standard"},
        "FarDistance": {"name": "FarDistance", "oid_default": 50, "category": "standard"},
        "CameraHeight": {"name": "CameraHeight", "oid_default": 1.5, "category": "standard"},
        "SRS": {"name": "SRS", "category": "standard"},
        "X": {"name": "X", "category": "standard"},
        "Y": {"name": "Y", "category": "standard"},
        "Z": {"name": "Z", "category": "standard"},
        "CameraOrientation": {"name": "CameraOrientation", "category": "standard"},
        "CameraHeading": {"name": "CameraHeading", "category": "standard"},
        "ImagePath": {"name": "ImagePath", "category": "standard"},
    }
    mosaic_fields = {"Reel": {"name": "Reel"}, "Frame": {"name": "Frame"}}
    mock_cfg.get.side_effect = lambda k, d=None: {"oid_schema_template.esri_default": {}, "oid_schema_template": {"mosaic_fields": mosaic_fields}, "camera_offset.z": {"a": 10}, "camera_offset.camera_height": {"a": 150}, "spatial_ref.gcs_horizontal_wkid": 4326, "spatial_ref.vcs_vertical_wkid": 5703}.get(k, d)
    
    # Patch field registry loader
    monkeypatch.setattr("utils.calculate_oid_attributes.load_field_registry", lambda cfg: registry)
    # Patch check_oid_fov_defaults to do nothing
    monkeypatch.setattr("utils.calculate_oid_attributes.check_oid_fov_defaults", lambda *a, **kw: None)
    # Patch extract helpers
    monkeypatch.setattr("utils.calculate_oid_attributes.extract_reel_from_path", lambda path: "1234")
    monkeypatch.setattr("utils.calculate_oid_attributes.extract_frame_from_filename", lambda path: "000001")
    monkeypatch.setattr("utils.calculate_oid_attributes.load_reel_from_info_file", lambda path, logger: (None, None))
    # Patch arcpy
    fields = ["OID@", "SHAPE@X", "SHAPE@Y", "SHAPE@Z", "CameraHeading", "ImagePath", "CameraPitch", "CameraRoll", "NearDistance", "FarDistance", "X", "Y", "Z", "SRS", "CameraHeight", "CameraOrientation", "Reel", "Frame"]
    data = [
        [1, 100.0, 200.0, 10.0, 45.0, " /path/to/img_000001.jpg ", None, None, None, None, None, None, None, None, None, None, None, None],
    ]
    field_to_index = {name: i for i, name in enumerate(fields)}
    class FakeUpdateCursor:
        def __init__(self, rows): self.rows = rows; self.idx = 0
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb): return False
        def __iter__(self): return iter(self.rows)
        def updateRow(self, row): self.rows[0] = row
    class FakeSearchCursor:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb): return False
        def __iter__(self): return iter([["/path/to/img_000001.jpg"]])
    monkeypatch.setattr("arcpy.da.UpdateCursor", lambda fc, flds: FakeUpdateCursor(data))
    monkeypatch.setattr("arcpy.da.SearchCursor", lambda fc, flds, where_clause=None: FakeSearchCursor())
    monkeypatch.setattr("arcpy.management.GetCount", lambda fc: [1])
    # Run
    enrich_oid_attributes(mock_cfg, "mock_oid_fc")
    logger = mock_cfg.get_logger()
    assert logger.info.called

def test_enrich_oid_attributes_missing_fields(monkeypatch, mock_cfg):
    # Setup registry missing CameraHeading
    registry = {
        "CameraPitch": {"name": "CameraPitch", "oid_default": 90, "category": "standard"},
        "CameraRoll": {"name": "CameraRoll", "oid_default": 0, "category": "standard"},
        "ImagePath": {"name": "ImagePath", "category": "standard"},
    }
    mosaic_fields = {}
    mock_cfg.get.side_effect = lambda k, d=None: {"oid_schema_template.esri_default": {}, "oid_schema_template": {"mosaic_fields": mosaic_fields}, "camera_offset.z": {"a": 10}, "camera_offset.camera_height": {"a": 150}, "spatial_ref.gcs_horizontal_wkid": 4326, "spatial_ref.vcs_vertical_wkid": 5703}.get(k, d)
    monkeypatch.setattr("utils.calculate_oid_attributes.load_field_registry", lambda cfg: registry)
    monkeypatch.setattr("utils.calculate_oid_attributes.check_oid_fov_defaults", lambda *a, **kw: None)
    monkeypatch.setattr("utils.calculate_oid_attributes.extract_reel_from_path", lambda path: None)
    monkeypatch.setattr("utils.calculate_oid_attributes.extract_frame_from_filename", lambda path: None)
    monkeypatch.setattr("utils.calculate_oid_attributes.load_reel_from_info_file", lambda path, logger: (None, None))
    fields = ["OID@", "SHAPE@X", "SHAPE@Y", "SHAPE@Z", "ImagePath", "CameraPitch", "CameraRoll"]
    data = [
        [1, 100.0, 200.0, 10.0, "/path/to/img_000001.jpg", None, None],
    ]
    class FakeUpdateCursor:
        def __init__(self, rows): self.rows = rows
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb): return False
        def __iter__(self): return iter(self.rows)
        def updateRow(self, row): pass
    class FakeSearchCursor:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb): return False
        def __iter__(self): return iter([["/path/to/img_000001.jpg"]])
    monkeypatch.setattr("arcpy.da.UpdateCursor", lambda fc, flds: FakeUpdateCursor(data))
    monkeypatch.setattr("arcpy.da.SearchCursor", lambda fc, flds, where_clause=None: FakeSearchCursor())
    monkeypatch.setattr("arcpy.management.GetCount", lambda fc: [1])
    enrich_oid_attributes(mock_cfg, "mock_oid_fc")
    logger = mock_cfg.get_logger()
    logger.warning.assert_any_call("Missing CameraHeading for row 1, skipping row.")

def test_enrich_oid_attributes_empty_oid(monkeypatch, mock_cfg):
    registry = {"CameraHeading": {"name": "CameraHeading", "category": "standard"}, "ImagePath": {"name": "ImagePath", "category": "standard"}}
    mosaic_fields = {}
    mock_cfg.get.side_effect = lambda k, d=None: {"oid_schema_template.esri_default": {}, "oid_schema_template": {"mosaic_fields": mosaic_fields}, "camera_offset.z": {"a": 10}, "camera_offset.camera_height": {"a": 150}, "spatial_ref.gcs_horizontal_wkid": 4326, "spatial_ref.vcs_vertical_wkid": 5703}.get(k, d)
    monkeypatch.setattr("utils.calculate_oid_attributes.load_field_registry", lambda cfg: registry)
    monkeypatch.setattr("utils.calculate_oid_attributes.check_oid_fov_defaults", lambda *a, **kw: None)
    monkeypatch.setattr("utils.calculate_oid_attributes.extract_reel_from_path", lambda path: None)
    monkeypatch.setattr("utils.calculate_oid_attributes.extract_frame_from_filename", lambda path: None)
    monkeypatch.setattr("utils.calculate_oid_attributes.load_reel_from_info_file", lambda path, logger: (None, None))
    fields = ["OID@", "SHAPE@X", "SHAPE@Y", "SHAPE@Z", "CameraHeading", "ImagePath"]
    data = [[1, 100.0, 200.0, 10.0, 45.0, None]]
    class FakeUpdateCursor:
        def __init__(self, rows): self.rows = rows
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb): return False
        def __iter__(self): return iter(self.rows)
        def updateRow(self, row): pass
    class FakeSearchCursor:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb): return False
        def __iter__(self): return iter([[None]])
    monkeypatch.setattr("arcpy.da.UpdateCursor", lambda fc, flds: FakeUpdateCursor(data))
    monkeypatch.setattr("arcpy.da.SearchCursor", lambda fc, flds, where_clause=None: FakeSearchCursor())
    monkeypatch.setattr("arcpy.management.GetCount", lambda fc: [1])
    enrich_oid_attributes(mock_cfg, "mock_oid_fc")
    logger = mock_cfg.get_logger()
    logger.error.assert_any_call("No images found in the OID dataset. Skipping OID attribute calculation.")
