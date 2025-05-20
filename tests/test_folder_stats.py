import os
import tempfile
import shutil
import stat
from pathlib import Path
from utils import folder_stats

def test_folder_stats_empty(tmp_path):
    count, size = folder_stats.folder_stats(str(tmp_path))
    assert count == 0
    assert size in ('0 B', '0 Bytes')

def test_folder_stats_missing():
    count, size = folder_stats.folder_stats('nonexistent_folder')
    assert count == 0
    assert size == '0 B'

def test_folder_stats_basic(tmp_path):
    # Create .jpg and .JPG files, and a .txt file
    (tmp_path / 'a.jpg').write_bytes(b'x' * 1024)
    (tmp_path / 'b.JPG').write_bytes(b'x' * 2048)
    (tmp_path / 'c.txt').write_bytes(b'x' * 4096)
    count, size = folder_stats.folder_stats(str(tmp_path))
    # Should match both .jpg and .JPG
    assert count == 2
    assert '1.0' in size or '2.0' in size or '3.0' in size  # Should be >1 KB

def test_folder_stats_with_extensions(tmp_path):
    (tmp_path / 'a.png').write_bytes(b'x' * 512)
    (tmp_path / 'b.JPG').write_bytes(b'x' * 256)
    count, size = folder_stats.folder_stats(str(tmp_path), extensions=['.png', '.JPG'])
    assert count == 2


def test_folder_stats_skips_unstatable(tmp_path):
    # Create a file and make it unreadable
    f = tmp_path / 'bad.jpg'
    f.write_bytes(b'x' * 512)
    f.chmod(0)
    try:
        count, size = folder_stats.folder_stats(str(tmp_path))
        assert count == 1  # File is still counted
        assert '0 B' in size or '512' in size or 'bytes' in size
    finally:
        # Restore permissions so tmp_path can be cleaned up
        f.chmod(stat.S_IWRITE | stat.S_IREAD)
