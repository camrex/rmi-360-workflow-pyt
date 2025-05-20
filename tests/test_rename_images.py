import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from utils.rename_images import _resolve_fields, _get_unique_filename, _copy_and_delete

def test_resolve_fields_simple():
    cfg = MagicMock()
    row = {"Name": "img001"}
    parts = {"Name": "field.Name"}
    # Patch resolve_expression to just return the value from row
    with patch("utils.rename_images.resolve_expression", side_effect=lambda expr, cfg, row: row[expr.split(".")[1]]):
        result = _resolve_fields(cfg, row, parts)
    assert result == {"Name": "img001"}

def test_get_unique_filename(tmp_path):
    # Create a file to force a duplicate
    filename = "photo.jpg"
    file_path = tmp_path / filename
    file_path.write_text("test")
    # Should return photo_v1.jpg since photo.jpg exists
    unique = _get_unique_filename(tmp_path, filename)
    assert unique == "photo_v1.jpg"
    # If photo_v1.jpg also exists, should return photo_v2.jpg
    (tmp_path / "photo_v1.jpg").write_text("test2")
    unique2 = _get_unique_filename(tmp_path, filename)
    assert unique2 == "photo_v2.jpg"

def test_copy_and_delete(tmp_path):
    src = tmp_path / "src.jpg"
    dst = tmp_path / "dst.jpg"
    src.write_text("foo")
    # Copy only
    _copy_and_delete(src, dst, delete_originals=False)
    assert dst.read_text() == "foo"
    assert src.exists()
    # Copy and delete
    src2 = tmp_path / "src2.jpg"
    dst2 = tmp_path / "dst2.jpg"
    src2.write_text("bar")
    _copy_and_delete(src2, dst2, delete_originals=True)
    assert dst2.read_text() == "bar"
    assert not src2.exists()
