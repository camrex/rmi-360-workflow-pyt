import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from utils.add_images_to_oid_fc import add_images_to_oid, warn_if_multiple_reel_info

@pytest.fixture
def mock_cfg():
    cfg = MagicMock()
    cfg.get_logger.return_value = MagicMock()
    cfg.get_progressor.return_value.__enter__.return_value = MagicMock()
    cfg.get_progressor.return_value.__exit__.return_value = False
    cfg.paths.original = Path("/mock/images")
    return cfg

def test_warn_if_multiple_reel_info_warns_on_multiple(tmp_path):
    # Create multiple reel_info.json files
    (tmp_path / "reel_info.json").write_text("{}")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "reel_info.json").write_text("{}")
    logger = MagicMock()
    warn_if_multiple_reel_info(tmp_path, logger)
    logger.warning.assert_called_once()

def test_add_images_to_oid_success(monkeypatch, mock_cfg, tmp_path):
    # Setup image folder and OID
    mock_cfg.paths.original = tmp_path
    (tmp_path / "img1.jpg").write_text("data")
    (tmp_path / "img2.jpg").write_text("data")
    monkeypatch.setattr("arcpy.Exists", lambda x: True)
    monkeypatch.setattr("arcpy.oi.AddImagesToOrientedImageryDataset", lambda **kwargs: None)
    with patch("utils.add_images_to_oid_fc.load_field_registry", return_value={"OrientedImageryType": {"oid_default": "360"}}):
        add_images_to_oid(mock_cfg, "mock_oid_fc")
    # Should log info at least once
    assert mock_cfg.get_logger().info.called

def test_add_images_to_oid_missing_oid(monkeypatch, mock_cfg, tmp_path):
    mock_cfg.paths.original = tmp_path
    (tmp_path / "img1.jpg").write_text("data")
    monkeypatch.setattr("arcpy.Exists", lambda x: False)
    with patch("utils.add_images_to_oid_fc.load_field_registry", return_value={"OrientedImageryType": {"oid_default": "360"}}):
        add_images_to_oid(mock_cfg, "mock_oid_fc")
    mock_cfg.get_logger().error.assert_any_call("OID does not exist at path: mock_oid_fc", error_type=FileNotFoundError)

def test_add_images_to_oid_missing_images(monkeypatch, mock_cfg, tmp_path):
    mock_cfg.paths.original = tmp_path
    monkeypatch.setattr("arcpy.Exists", lambda x: True)
    with patch("utils.add_images_to_oid_fc.load_field_registry", return_value={"OrientedImageryType": {"oid_default": "360"}}):
        add_images_to_oid(mock_cfg, "mock_oid_fc")
    mock_cfg.get_logger().error.assert_any_call(f"No .jpg files found in image folder or its subfolders: {tmp_path}", error_type=RuntimeError)
