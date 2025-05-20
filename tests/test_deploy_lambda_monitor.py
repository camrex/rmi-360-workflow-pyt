import types
import io
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from pathlib import Path

from utils.deploy_lambda_monitor import get_final_image_files, count_final_images, build_progress_json

def test_get_final_image_files(tmp_path):
    # Create dummy JPEG and non-JPEG files
    (tmp_path / "img1.jpg").write_bytes(b"")
    (tmp_path / "img2.jpeg").write_bytes(b"")
    (tmp_path / "doc.txt").write_bytes(b"")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "img3.JPG").write_bytes(b"")  # Should be found (case-insensitive)
    files = get_final_image_files(tmp_path)
    paths = [str(f.name).lower() for f in files]
    assert "img1.jpg" in paths
    assert "img2.jpeg" in paths
    assert "img3.jpg" in paths
    assert "doc.txt" not in paths
    assert len(files) == 3

def test_get_final_image_files_no_folder(tmp_path):
    # Folder does not exist
    non_existent = tmp_path / "doesnotexist"
    files = get_final_image_files(non_existent)
    assert files == []

def test_count_final_images_found(tmp_path):
    # Patch cfg to use tmp_path
    class DummyPaths:
        renamed = tmp_path
    cfg = MagicMock()
    cfg.paths = DummyPaths()
    logger = MagicMock()
    cfg.get_logger.return_value = logger
    (tmp_path / "img1.jpg").write_bytes(b"")
    (tmp_path / "img2.jpeg").write_bytes(b"")
    count = count_final_images(cfg)
    assert count == 2
    logger.info.assert_called_with(f"Found 2 JPEG images in {tmp_path}")

def test_count_final_images_none(tmp_path):
    class DummyPaths:
        renamed = tmp_path
    cfg = MagicMock()
    cfg.paths = DummyPaths()
    logger = MagicMock()
    cfg.get_logger.return_value = logger
    count = count_final_images(cfg)
    assert count == 0
    logger.warning.assert_called_with(f"No JPEG images found in {tmp_path}")

def test_build_progress_json_defaults():
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: {
        "project.number": "123",
        "project.slug": "myslug",
        "project.client": "myclient",
        "project.rr_name": "rrname",
        "project.rr_mark": "rrmark",
        "project.description": "desc",
        "camera.make": "Canon",
        "camera.model": "5D",
        "camera.sn": "SN123",
        "camera.firmware": "1.0",
        "camera.software": "soft",
        "aws.s3_bucket": "bucket",
        "aws.s3_bucket_folder": "folder",
        "aws.region": "us-west-2"
    }[k]
    now = datetime(2025, 5, 14, 17, 35, 0, tzinfo=timezone.utc)
    result = build_progress_json(cfg, 42, now=now)
    assert result["project_slug"] == "myslug"
    assert result["last_updated"] == now.isoformat()
    assert result["expected_total"] == 42
    assert result["cloud_info"]["bucket"] == "bucket"
    assert result["cloud_info"]["region"] == "us-west-2"
    assert result["camera_info"]["make"] == "Canon"
    assert result["project_info"]["number"] == "123"
