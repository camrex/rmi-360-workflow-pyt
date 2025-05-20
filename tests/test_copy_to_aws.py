import os
import tempfile
import csv
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from utils.copy_to_aws import (
    collect_upload_tasks,
    parse_uploaded_keys_from_log,
    calculate_summary,
    write_summary_file,
    should_cancel
)

def test_collect_upload_tasks(tmp_path):
    # Create dummy files
    (tmp_path / "a.jpg").write_bytes(b"")
    (tmp_path / "b.jpeg").write_bytes(b"")
    (tmp_path / "c.txt").write_bytes(b"")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "d.jpg").write_bytes(b"")
    bucket_folder = "bucket/folder"
    tasks = collect_upload_tasks(tmp_path, [".jpg", ".jpeg"], bucket_folder)
    s3_keys = [t[1] for t in tasks]
    assert any("a.jpg" in key for key in s3_keys)
    assert any("b.jpeg" in key for key in s3_keys)
    assert any("d.jpg" in key for key in s3_keys)
    assert all(key.startswith(bucket_folder) for key in s3_keys)
    assert not any("c.txt" in key for key in s3_keys)

def test_parse_uploaded_keys_from_log(tmp_path):
    log_file = tmp_path / "log.csv"
    rows = [
        ["timestamp", "local_file", "s3_key", "status", "error", "size_bytes", "duration_sec"],
        ["t1", "f1", "s3key1", "uploaded", "", "100", "1.2"],
        ["t2", "f2", "s3key2", "skipped", "", "100", "1.2"],
        ["t3", "f3", "s3key3", "uploaded", "", "100", "1.2"]
    ]
    with open(log_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    logger = MagicMock()
    keys = parse_uploaded_keys_from_log(str(log_file), logger)
    assert "s3key1" in keys
    assert "s3key3" in keys
    assert "s3key2" not in keys
    logger.info.assert_called()

def test_calculate_summary():
    # log_rows: (timestamp, f_path, s3_key, status, error, size_bytes, duration)
    log_rows = [
        ("t1", "f1", "s3key1", "uploaded", "", 100, 2.0),
        ("t2", "f2", "s3key2", "skipped", "from prior log", 50, 0.0),
        ("t3", "f3", "s3key3", "skipped", "", 30, 0.0),
        ("t4", "f4", "s3key4", "error", "err", 0, 0.0)
    ]
    total = 2  # only 2 real upload tasks
    import time
    start_time = time.time() - 10  # pretend 10 seconds elapsed
    stats = calculate_summary(log_rows, total, start_time)
    assert stats["uploaded"] == 1
    assert stats["skipped"] == 2
    assert stats["skipped_from_log"] == 1
    assert stats["failed"] == 1
    assert stats["elapsed_time"] >= 10
    assert stats["total_size_bytes"] == 180
    assert "avg_time_per_image" in stats
    assert "avg_speed" in stats
    assert "total_size_mb" in stats

def test_write_summary_file(tmp_path):
    stats = {
        "uploaded": 2,
        "skipped": 1,
        "skipped_from_log": 1,
        "failed": 1,
        "elapsed_time": 5.5,
        "total_size_bytes": 123456,
        "avg_time_per_image": 2.75,
        "avg_speed": 1.2,
        "total_size_mb": 0.12
    }
    summary_file = tmp_path / "summary.csv"
    write_summary_file(str(summary_file), stats)
    with open(summary_file, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert any("Uploaded" in row for row in rows)
    assert any("Average Speed (MB/sec)" in row for row in rows)

def test_should_cancel(tmp_path):
    # ArcGIS event
    class Msg:
        def isCanceled(self):
            return True
    assert should_cancel(Msg(), False, tmp_path / "cancel_copy.txt")
    # File trigger
    cancel_file = tmp_path / "cancel_copy.txt"
    cancel_file.write_text("")
    assert should_cancel(object(), True, cancel_file)
    # Neither
    assert not should_cancel(object(), False, cancel_file)
