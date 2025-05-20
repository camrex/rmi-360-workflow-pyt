import pytest
from unittest.mock import patch, MagicMock
from utils.assign_group_index import assign_group_index

@pytest.fixture
def mock_cfg():
    cfg = MagicMock()
    cfg.get_logger.return_value = MagicMock()
    cfg.get.return_value = "GroupIndex"
    cfg.validate.return_value = True
    return cfg

def test_assign_group_index_success(monkeypatch, mock_cfg):
    # Patch arcpy and cursor
    features = [
        {"AcquisitionDate": "2024-01-01", "GroupIndex": None, "OBJECTID": 1},
        {"AcquisitionDate": "2024-01-02", "GroupIndex": None, "OBJECTID": 2},
        {"AcquisitionDate": "2024-01-03", "GroupIndex": None, "OBJECTID": 3},
        {"AcquisitionDate": "2024-01-04", "GroupIndex": None, "OBJECTID": 4},
    ]
    class FakeCursor:
        def __init__(self, feats):
            self.feats = feats
            self.idx = 0
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb): return False
        def __iter__(self): return iter(self.feats)
        def updateRow(self, feat): pass
    monkeypatch.setattr("arcpy.da.UpdateCursor", lambda fc, fields: FakeCursor(features))
    monkeypatch.setattr("arcpy.ListFields", lambda fc: [MagicMock(name="GroupIndex")])
    assign_group_index(mock_cfg, "mock_oid_fc", group_size=2)
    logger = mock_cfg.get_logger()
    assert logger.info.called

def test_assign_group_index_invalid_group_size(mock_cfg):
    assign_group_index(mock_cfg, "mock_oid_fc", group_size=0)
    logger = mock_cfg.get_logger()
    logger.error.assert_called_with("Group size must be a positive integer, got 0", error_type=ValueError)

def test_assign_group_index_missing_field(monkeypatch, mock_cfg):
    # Patch ListFields to return no GroupIndex field
    monkeypatch.setattr("arcpy.ListFields", lambda fc: [])
    assign_group_index(mock_cfg, "mock_oid_fc", group_size=2)
    logger = mock_cfg.get_logger()
    logger.error.assert_any_call("Field 'GroupIndex' not found in feature class. Please ensure it is included in your schema.", error_type=RuntimeError)

def test_assign_group_index_null_dates(monkeypatch, mock_cfg):
    # Patch cursor to have null AcquisitionDate
    features = [
        {"AcquisitionDate": None, "GroupIndex": None, "OBJECTID": 1},
    ]
    class FakeCursor:
        def __init__(self, feats): self.feats = feats
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb): return False
        def __iter__(self): return ((f["OBJECTID"], f["AcquisitionDate"]) for f in self.feats)
        def updateRow(self, feat): pass
    monkeypatch.setattr("arcpy.da.UpdateCursor", lambda fc, fields: FakeCursor(features))
    monkeypatch.setattr("arcpy.da.SearchCursor", lambda fc, fields: FakeCursor(features))
    field = MagicMock()
    field.name = "GroupIndex"
    monkeypatch.setattr("arcpy.ListFields", lambda fc: [field])
    assign_group_index(mock_cfg, "mock_oid_fc", group_size=2)
    logger = mock_cfg.get_logger()
    logger.error.assert_any_call(
        "1 features have null AcquisitionDate values: [1]",
        error_type=ValueError
    )
