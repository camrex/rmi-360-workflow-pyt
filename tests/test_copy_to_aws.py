import csv
import importlib.util
import pathlib
import sys
import types
from unittest.mock import MagicMock


# Lightweight stubs so utils/copy_to_aws.py can load without full runtime deps.
boto3_mod = types.ModuleType("boto3")
boto3_s3_mod = types.ModuleType("boto3.s3")
boto3_transfer_mod = types.ModuleType("boto3.s3.transfer")
botocore_mod = types.ModuleType("botocore")
botocore_config_mod = types.ModuleType("botocore.config")
botocore_ex_mod = types.ModuleType("botocore.exceptions")


class TransferConfig:  # pragma: no cover - import stub
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


def create_transfer_manager(*args, **kwargs):  # pragma: no cover - import stub
    return MagicMock()


class Config:  # pragma: no cover - import stub
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class ClientError(Exception):
    pass


class NoCredentialsError(Exception):
    pass


boto3_transfer_mod.TransferConfig = TransferConfig
boto3_transfer_mod.create_transfer_manager = create_transfer_manager
botocore_config_mod.Config = Config
botocore_ex_mod.ClientError = ClientError
botocore_ex_mod.NoCredentialsError = NoCredentialsError

sys.modules["boto3"] = boto3_mod
sys.modules["boto3.s3"] = boto3_s3_mod
sys.modules["boto3.s3.transfer"] = boto3_transfer_mod
sys.modules["botocore"] = botocore_mod
sys.modules["botocore.config"] = botocore_config_mod
sys.modules["botocore.exceptions"] = botocore_ex_mod

utils_mod = types.ModuleType("utils")
manager_mod = types.ModuleType("utils.manager")
manager_cfg_mod = types.ModuleType("utils.manager.config_manager")
shared_mod = types.ModuleType("utils.shared")
shared_aws_mod = types.ModuleType("utils.shared.aws_utils")
shared_paths_mod = types.ModuleType("utils.shared.oid_storage_paths")


class ConfigManager:  # pragma: no cover - typing-only import target
    pass


def get_boto3_session(_cfg):  # pragma: no cover - import stub
    return MagicMock()


def is_secured_storage_enabled(_cfg):
    return False


def build_oid_object_key(cfg, filename, secured_mode=False):
    prefix = cfg.get("aws.s3_bucket_folder", "")
    return f"{prefix.rstrip('/')}/{filename}" if prefix else filename


def resolve_oid_key_prefix(cfg, secured_mode=False):
    return cfg.get("aws.s3_bucket_folder", "")


def resolve_oid_target_bucket(cfg, secured_mode=False):
    return cfg.get("aws.s3_bucket", "")


manager_cfg_mod.ConfigManager = ConfigManager
shared_aws_mod.get_boto3_session = get_boto3_session
shared_paths_mod.is_secured_storage_enabled = is_secured_storage_enabled
shared_paths_mod.build_oid_object_key = build_oid_object_key
shared_paths_mod.resolve_oid_key_prefix = resolve_oid_key_prefix
shared_paths_mod.resolve_oid_target_bucket = resolve_oid_target_bucket

utils_mod.manager = manager_mod
utils_mod.shared = shared_mod
manager_mod.config_manager = manager_cfg_mod
shared_mod.aws_utils = shared_aws_mod
shared_mod.oid_storage_paths = shared_paths_mod

sys.modules["utils"] = utils_mod
sys.modules["utils.manager"] = manager_mod
sys.modules["utils.manager.config_manager"] = manager_cfg_mod
sys.modules["utils.shared"] = shared_mod
sys.modules["utils.shared.aws_utils"] = shared_aws_mod
sys.modules["utils.shared.oid_storage_paths"] = shared_paths_mod

repo_root = pathlib.Path(__file__).resolve().parents[1]
module_path = repo_root / "utils" / "copy_to_aws.py"
spec = importlib.util.spec_from_file_location("copy_to_aws_under_test", module_path)
copy_to_aws_mod = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(copy_to_aws_mod)

collect_upload_tasks = copy_to_aws_mod.collect_upload_tasks
collect_upload_tasks_from_manifest = copy_to_aws_mod.collect_upload_tasks_from_manifest
parse_uploaded_keys_from_log = copy_to_aws_mod.parse_uploaded_keys_from_log
calculate_summary = copy_to_aws_mod.calculate_summary
write_summary_file = copy_to_aws_mod.write_summary_file
should_cancel = copy_to_aws_mod.should_cancel

def test_collect_upload_tasks(tmp_path):
    # Create dummy files
    (tmp_path / "a.jpg").write_bytes(b"")
    (tmp_path / "b.jpeg").write_bytes(b"")
    (tmp_path / "c.txt").write_bytes(b"")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "d.jpg").write_bytes(b"")
    class DummyCfg:
        def get(self, key, default=None):
            values = {
                "secured_storage.enabled": False,
                "aws.s3_bucket_folder": "bucket/folder",
                "project.slug": "proj",
            }
            return values.get(key, default)

        def resolve(self, value):
            return value

    cfg = DummyCfg()
    tasks = collect_upload_tasks(tmp_path, [".jpg", ".jpeg"], cfg, secured_mode=False)
    s3_keys = [t[1] for t in tasks]
    assert any("a.jpg" in key for key in s3_keys)
    assert any("b.jpeg" in key for key in s3_keys)
    assert any("d.jpg" in key for key in s3_keys)
    assert all(key.startswith("bucket/folder") for key in s3_keys)
    assert not any("c.txt" in key for key in s3_keys)


def test_collect_upload_tasks_from_manifest_prefers_local_path(tmp_path):
    renamed = tmp_path / "renamed"
    renamed.mkdir()
    direct = tmp_path / "a.jpg"
    direct.write_bytes(b"")
    fallback = renamed / "b.jpg"
    fallback.write_bytes(b"")
    ignored = tmp_path / "ignore.txt"
    ignored.write_bytes(b"")

    manifest = tmp_path / "manifest.csv"
    with open(manifest, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["local_path", "filename"])
        writer.writeheader()
        writer.writerow({"local_path": str(direct), "filename": ""})
        writer.writerow({"local_path": "", "filename": "b.jpg"})
        writer.writerow({"local_path": str(ignored), "filename": "ignore.txt"})
        writer.writerow({"local_path": str(direct), "filename": ""})  # duplicate row

    class DummyCfg:
        def __init__(self, renamed_path):
            self.paths = types.SimpleNamespace(renamed=renamed_path)

        def get(self, key, default=None):
            values = {
                "aws.s3_bucket_folder": "bucket/folder",
            }
            return values.get(key, default)

    cfg = DummyCfg(renamed)
    tasks = collect_upload_tasks_from_manifest(manifest, [".jpg", ".jpeg"], cfg, secured_mode=False)
    task_paths = sorted(pathlib.Path(t[0]).name for t in tasks)
    task_keys = sorted(t[1] for t in tasks)

    assert task_paths == ["a.jpg", "b.jpg"]
    assert all(key.startswith("bucket/folder/") for key in task_keys)


def test_collect_upload_tasks_from_manifest_missing_file_raises(tmp_path):
    class DummyCfg:
        def __init__(self, renamed_path):
            self.paths = types.SimpleNamespace(renamed=renamed_path)

        def get(self, key, default=None):
            return default

    cfg = DummyCfg(tmp_path)
    missing = tmp_path / "missing_manifest.csv"

    try:
        collect_upload_tasks_from_manifest(missing, [".jpg", ".jpeg"], cfg, secured_mode=False)
        assert False, "Expected FileNotFoundError"
    except FileNotFoundError:
        assert True

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
    logger.custom.assert_called()

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
