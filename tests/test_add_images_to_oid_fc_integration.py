import pytest
import shutil
from pathlib import Path
from utils.manager.config_manager import ConfigManager
from utils.add_images_to_oid_fc import add_images_to_oid
from unittest.mock import patch

CONFIG_FILE = str(Path(__file__).parent.parent / "configs" / "config.sample.yaml")

@pytest.fixture
def sample_cfg(tmp_path):
    # Copy sample config to temp dir
    cfg_path = tmp_path / "config.yaml"
    shutil.copy(CONFIG_FILE, cfg_path)
    # Patch project_base and config path
    cfg = ConfigManager.from_file(str(cfg_path), project_base=tmp_path)
    # Patch paths.original to a temp image folder using patch.object
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    patcher = patch.object(type(cfg.paths), 'original', new=property(lambda self: images_dir))
    patcher.start()
    try:
        yield cfg
    finally:
        patcher.stop()

def test_add_images_to_oid_with_sample_config(tmp_path, sample_cfg, monkeypatch):
    # Create a fake OID feature class path
    oid_fc_path = tmp_path / "mock_oid_fc.gdb" / "oid_fc"
    oid_fc_path.parent.mkdir()
    oid_fc_path.touch()
    # Add some jpgs to the images directory
    (sample_cfg.paths.original / "img1.jpg").write_text("data")
    (sample_cfg.paths.original / "img2.jpg").write_text("data")
    # Patch arcpy
    monkeypatch.setattr("arcpy.Exists", lambda x: True)
    monkeypatch.setattr("arcpy.oi.AddImagesToOrientedImageryDataset", lambda **kwargs: None)
    # Patch logger
    from unittest.mock import MagicMock
    logger = MagicMock()
    with patch.object(sample_cfg, "get_logger", return_value=logger):
        with patch("utils.add_images_to_oid_fc.load_field_registry", return_value={"OrientedImageryType": {"oid_default": "360"}}):
            add_images_to_oid(sample_cfg, str(oid_fc_path))
        assert logger.info.called

def test_add_images_to_oid_with_sample_config_missing_images(tmp_path, sample_cfg, monkeypatch):
    # No images in images_dir
    oid_fc_path = tmp_path / "mock_oid_fc.gdb" / "oid_fc"
    oid_fc_path.parent.mkdir()
    oid_fc_path.touch()
    monkeypatch.setattr("arcpy.Exists", lambda x: True)
    from unittest.mock import MagicMock
    logger = MagicMock()
    with patch.object(sample_cfg, "get_logger", return_value=logger):
        with patch("utils.add_images_to_oid_fc.load_field_registry", return_value={"OrientedImageryType": {"oid_default": "360"}}):
            add_images_to_oid(sample_cfg, str(oid_fc_path))
        logger.error.assert_any_call(
            f"No .jpg files found in image folder or its subfolders: {sample_cfg.paths.original}",
            error_type=RuntimeError
        )
