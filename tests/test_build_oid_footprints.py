from unittest.mock import MagicMock, patch
from utils.build_oid_footprints import (
    resolve_spatial_reference,
    resolve_geographic_transformation,
    get_output_path
)

def test_resolve_spatial_reference_valid(monkeypatch):
    cfg = MagicMock()
    logger = MagicMock()
    cfg.get.return_value = "3857"
    monkeypatch.setattr("utils.build_oid_footprints.resolve_expression", lambda expr, cfg: 3857)
    class FakeSpatialReference:
        def __init__(self, wkid):
            self.wkid = wkid
    monkeypatch.setattr("utils.build_oid_footprints.arcpy.SpatialReference", FakeSpatialReference)
    sr = resolve_spatial_reference(cfg, logger)
    assert sr.wkid == 3857
    logger.info.assert_called_with("📐 Using projected coordinate system: WKID 3857")

def test_resolve_spatial_reference_missing(monkeypatch):
    cfg = MagicMock()
    logger = MagicMock()
    cfg.get.return_value = None
    sr = resolve_spatial_reference(cfg, logger)
    assert sr is None
    logger.error.assert_called()

def test_resolve_geographic_transformation():
    cfg = MagicMock()
    logger = MagicMock()
    cfg.get.return_value = "WGS_1984_(ITRF00)_To_NAD_1983"
    result = resolve_geographic_transformation(cfg, logger)
    assert result == "WGS_1984_(ITRF00)_To_NAD_1983"
    logger.info.assert_called_with("🌍 Applying geographic transformation: WGS_1984_(ITRF00)_To_NAD_1983")

def test_get_output_path():
    class FakeDesc:
        path = "/tmp/gdb"
        baseName = "myOID"
    with patch("utils.build_oid_footprints.arcpy.Describe", return_value=FakeDesc()):
        output_path, out_dataset_path, out_dataset_name = get_output_path("/tmp/gdb/myOID")
        import os
        assert output_path == os.path.join("/tmp/gdb", "myOID_Footprint")
        assert out_dataset_path == "/tmp/gdb"
        assert out_dataset_name == "myOID_Footprint"
