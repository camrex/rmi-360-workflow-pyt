import csv
import importlib.util
import pathlib
import sys
import types
from unittest.mock import MagicMock


_MISSING = object()


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

utils_mod = types.ModuleType("utils")
manager_mod = types.ModuleType("utils.manager")
manager_cfg_mod = types.ModuleType("utils.manager.config_manager")
shared_mod = types.ModuleType("utils.shared")
shared_aws_mod = types.ModuleType("utils.shared.aws_utils")
shared_paths_mod = types.ModuleType("utils.shared.oid_storage_paths")
# The status tracker is pure stdlib: load the real one (the heartbeat is under test).
_tracker_spec = importlib.util.spec_from_file_location(
    "utils.shared.s3_status_tracker",
    pathlib.Path(__file__).resolve().parents[1] / "utils" / "shared" / "s3_status_tracker.py")
shared_tracker_mod = importlib.util.module_from_spec(_tracker_spec)
_tracker_spec.loader.exec_module(shared_tracker_mod)


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
    return cfg.get("aws.s3_bucket_panos_unsecured", "")


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

_STUBBED_MODULE_NAMES = [
    "boto3",
    "boto3.s3",
    "boto3.s3.transfer",
    "botocore",
    "botocore.config",
    "botocore.exceptions",
    "utils",
    "utils.manager",
    "utils.manager.config_manager",
    "utils.shared",
    "utils.shared.aws_utils",
    "utils.shared.oid_storage_paths",
    "utils.shared.s3_status_tracker",
]
_snapshots = {name: sys.modules.get(name, _MISSING) for name in _STUBBED_MODULE_NAMES}
try:
    sys.modules["boto3"] = boto3_mod
    sys.modules["boto3.s3"] = boto3_s3_mod
    sys.modules["boto3.s3.transfer"] = boto3_transfer_mod
    sys.modules["botocore"] = botocore_mod
    sys.modules["botocore.config"] = botocore_config_mod
    sys.modules["botocore.exceptions"] = botocore_ex_mod

    sys.modules["utils"] = utils_mod
    sys.modules["utils.manager"] = manager_mod
    sys.modules["utils.manager.config_manager"] = manager_cfg_mod
    sys.modules["utils.shared"] = shared_mod
    sys.modules["utils.shared.aws_utils"] = shared_aws_mod
    sys.modules["utils.shared.oid_storage_paths"] = shared_paths_mod
    sys.modules["utils.shared.s3_status_tracker"] = shared_tracker_mod

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    module_path = repo_root / "utils" / "copy_to_aws.py"
    spec = importlib.util.spec_from_file_location("copy_to_aws_under_test", module_path)
    copy_to_aws_mod = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(copy_to_aws_mod)
finally:
    for _name, _prior in _snapshots.items():
        if _prior is _MISSING:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _prior

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
                "aws.secured_delivery.enabled": False,
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
        raise AssertionError("Expected FileNotFoundError")
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


def _client_error(code):
    err = ClientError(code)
    err.response = {"Error": {"Code": code}}
    return err


def test_object_exists_true_when_head_succeeds():
    s3 = MagicMock()
    assert copy_to_aws_mod.object_exists(s3, "rmi-360-prod", "RMI1/a.jpg") is True
    s3.head_object.assert_called_once_with(Bucket="rmi-360-prod", Key="RMI1/a.jpg")


def test_object_exists_false_on_404():
    for code in ("404", "NoSuchKey", "NotFound"):
        s3 = MagicMock()
        s3.head_object.side_effect = _client_error(code)
        assert copy_to_aws_mod.object_exists(s3, "b", "k") is False


def test_object_exists_raises_on_other_errors():
    # A 403 must not be read as "absent": that would risk an overwrite.
    s3 = MagicMock()
    s3.head_object.side_effect = _client_error("403")
    try:
        copy_to_aws_mod.object_exists(s3, "b", "k")
    except ClientError:
        pass
    else:
        raise AssertionError("expected ClientError")


def _client_error_status(code, status):
    err = ClientError(code)
    err.response = {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}}
    return err


def test_put_if_absent_sends_if_none_match(tmp_path):
    f = tmp_path / "a.jpg"; f.write_bytes(b"jpeg")
    s3 = MagicMock()
    assert copy_to_aws_mod.put_if_absent(s3, "b", "RMI1/a.jpg", str(f)) is True
    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["IfNoneMatch"] == "*" and kwargs["Key"] == "RMI1/a.jpg"
    assert kwargs["ContentType"] == "image/jpeg"


def test_put_if_absent_412_means_already_there(tmp_path):
    f = tmp_path / "a.jpg"; f.write_bytes(b"jpeg")
    for err in (_client_error_status("PreconditionFailed", 412), _client_error_status("", 412)):
        s3 = MagicMock(); s3.put_object.side_effect = err
        assert copy_to_aws_mod.put_if_absent(s3, "b", "k", str(f)) is False


def test_put_if_absent_raises_other_errors(tmp_path):
    f = tmp_path / "a.jpg"; f.write_bytes(b"jpeg")
    s3 = MagicMock(); s3.put_object.side_effect = _client_error_status("AccessDenied", 403)
    try:
        copy_to_aws_mod.put_if_absent(s3, "b", "k", str(f))
    except ClientError:
        pass
    else:
        raise AssertionError("expected ClientError")


def test_find_duplicate_keys():
    tasks = [("a/x.jpg", "P/x.jpg"), ("b/x.jpg", "P/x.jpg"), ("c/y.jpg", "P/y.jpg")]
    assert copy_to_aws_mod.find_duplicate_keys(tasks) == {"P/x.jpg": ["a/x.jpg", "b/x.jpg"]}


# --- end to end: copy_to_aws() against a fake S3 --------------------------------------

class _Progressor:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def update(self, *a, **k):
        pass


def _run_copy(tmp_path, monkeypatch, files, existing=(), raced=(), extra=None, heartbeat_fails=False,
              progressor_error=None, prior_log_keys=()):
    """Run copy_to_aws over ``files`` (relative paths). ``existing`` keys answer HeadObject 200;
    ``raced`` keys pass HeadObject but are refused by the conditional put (412)."""
    src = tmp_path / "renamed"
    for rel in files:
        p = src / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"jpeg")
    values = {"aws.s3_bucket_folder": "RMI1", "aws.s3_bucket_panos_unsecured": "prod",
              "aws.upload_batch_size": 10, "aws.max_workers": 4, "aws.retries": 2,
              "aws.use_acceleration": False, "aws.skip_existing": True,
              "aws.allow_cancel_file_trigger": False, **(extra or {})}
    cfg = MagicMock()
    cfg.get.side_effect = lambda k, d=None: values.get(k, d)
    cfg.get_progressor.return_value = _Progressor()
    if progressor_error is not None:
        cfg.get_progressor.side_effect = progressor_error
    cfg.paths.project_base = tmp_path
    cfg.paths.get_log_file_path.side_effect = lambda name, _cfg: tmp_path / f"{name}.csv"
    if prior_log_keys:
        with open(tmp_path / "aws_upload_log.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["timestamp", "local_file", "s3_key", "status", "error", "size_bytes", "duration_sec"])
            for k in prior_log_keys:
                w.writerow(["t", "f", k, "uploaded", "", 4, 0.1])
    s3 = MagicMock()
    s3.meta.service_model.operation_model.return_value.input_shape.members = {"IfNoneMatch": object()}
    s3.head_object.side_effect = lambda Bucket, Key: (None if Key in existing else
                                                      (_ for _ in ()).throw(_client_error("404")))
    put_keys, heartbeats = [], []

    def put_object(**kw):
        if kw["Key"].startswith("status/"):
            if heartbeat_fails:
                raise _client_error_status("AccessDenied", 403)
            heartbeats.append(kw)
            return
        put_keys.append(kw["Key"])
        if kw["Key"] in raced:
            raise _client_error_status("PreconditionFailed", 412)
    s3.put_object.side_effect = put_object
    session = MagicMock(); session.client.return_value = s3
    monkeypatch.setattr(copy_to_aws_mod, "get_boto3_session", lambda _cfg: session)
    result = copy_to_aws_mod.copy_to_aws(cfg, local_dir=str(src))
    _run_copy.heartbeats = heartbeats
    _run_copy.logger = cfg.get_logger.return_value
    return result, put_keys, s3


def test_copy_never_overwrites(tmp_path, monkeypatch):
    result, put_keys, s3 = _run_copy(tmp_path, monkeypatch, ["a.jpg", "b.jpg", "c.jpg"],
                                     existing={"RMI1/a.jpg"}, raced={"RMI1/b.jpg"})
    assert result["status"] == "completed"
    assert sorted(put_keys) == ["RMI1/b.jpg", "RMI1/c.jpg"]       # a.jpg never sent
    assert result["uploaded"] == 1 and result["skipped"] == 2 and result["failed"] == 0
    assert all(c.kwargs["IfNoneMatch"] == "*" for c in s3.put_object.call_args_list)


def test_copy_stops_on_duplicate_keys(tmp_path, monkeypatch):
    result, put_keys, _ = _run_copy(tmp_path, monkeypatch, ["reel1/x.jpg", "reel2/x.jpg", "y.jpg"])
    assert result["status"] == "error" and "more than one local file" in result["message"]
    assert put_keys == []


HEARTBEAT_CFG = {"aws.s3_bucket_raw": "rmi-360-raw", "project.slug": "RMI1"}


def test_heartbeat_published_to_status_prefix(tmp_path, monkeypatch):
    import json
    result, put_keys, _ = _run_copy(tmp_path, monkeypatch, ["a.jpg", "b.jpg"], extra=HEARTBEAT_CFG)
    assert result["status"] == "completed" and sorted(put_keys) == ["RMI1/a.jpg", "RMI1/b.jpg"]
    beats = _run_copy.heartbeats
    assert beats, "no heartbeat written"
    assert {b["Bucket"] for b in beats} == {"rmi-360-raw"}
    assert {b["Key"] for b in beats} == {"status/RMI1/upload_progress.json"}
    assert all(b["ServerSideEncryption"] == "AES256" for b in beats)
    final = json.loads(beats[-1]["Body"].decode("utf-8"))
    assert final["phase"] == "complete" and final["completed_at"]
    assert final["totals"]["uploaded"] == 2 and final["meta"]["project"] == "RMI1"
    assert (tmp_path / "aws_upload_status.json").exists()        # local copy too


def test_heartbeat_failure_does_not_fail_upload(tmp_path, monkeypatch):
    result, put_keys, _ = _run_copy(tmp_path, monkeypatch, ["a.jpg"], extra=HEARTBEAT_CFG, heartbeat_fails=True)
    assert result["status"] == "completed" and put_keys == ["RMI1/a.jpg"]
    warned = " ".join(str(c.args[0]) for c in _run_copy.logger.warning.call_args_list)
    assert "heartbeat could not be written" in warned


def test_no_heartbeat_without_raw_bucket_or_slug(tmp_path, monkeypatch):
    result, _, _ = _run_copy(tmp_path, monkeypatch, ["a.jpg"])
    assert result["status"] == "completed" and _run_copy.heartbeats == []


def test_put_if_absent_retries_409_conflict(tmp_path, monkeypatch):
    monkeypatch.setattr(copy_to_aws_mod.time, "sleep", lambda s: None)
    f = tmp_path / "a.jpg"; f.write_bytes(b"jpeg")
    s3 = MagicMock()
    s3.put_object.side_effect = [_client_error_status("ConditionalRequestConflict", 409), None]
    assert copy_to_aws_mod.put_if_absent(s3, "b", "k", str(f)) is True
    assert s3.put_object.call_count == 2
    # a 409 that resolves to "already there" on retry is a skip, not a failure
    s3 = MagicMock()
    s3.put_object.side_effect = [_client_error_status("ConditionalRequestConflict", 409),
                                 _client_error_status("PreconditionFailed", 412)]
    assert copy_to_aws_mod.put_if_absent(s3, "b", "k", str(f)) is False


def test_put_if_absent_gives_up_after_repeated_409(tmp_path, monkeypatch):
    monkeypatch.setattr(copy_to_aws_mod.time, "sleep", lambda s: None)
    f = tmp_path / "a.jpg"; f.write_bytes(b"jpeg")
    s3 = MagicMock()
    s3.put_object.side_effect = _client_error_status("ConditionalRequestConflict", 409)
    try:
        copy_to_aws_mod.put_if_absent(s3, "b", "k", str(f))
    except ClientError:
        pass
    else:
        raise AssertionError("expected ClientError")
    assert s3.put_object.call_count == copy_to_aws_mod.CONFLICT_RETRIES + 1


def test_supports_conditional_put():
    s3 = MagicMock()
    s3.meta.service_model.operation_model.return_value.input_shape.members = {"IfNoneMatch": 1}
    assert copy_to_aws_mod.supports_conditional_put(s3) is True
    s3.meta.service_model.operation_model.return_value.input_shape.members = {"Bucket": 1}
    assert copy_to_aws_mod.supports_conditional_put(s3) is False


def test_copy_stops_when_botocore_lacks_conditional_put(tmp_path, monkeypatch):
    real = copy_to_aws_mod.supports_conditional_put
    monkeypatch.setattr(copy_to_aws_mod, "supports_conditional_put", lambda s3: False)
    try:
        result, put_keys, _ = _run_copy(tmp_path, monkeypatch, ["a.jpg"])
    finally:
        monkeypatch.setattr(copy_to_aws_mod, "supports_conditional_put", real)
    assert result["status"] == "error" and "conditional writes" in result["message"]
    assert put_keys == []


def test_heartbeat_thread_stops_when_upload_raises(tmp_path, monkeypatch):
    import json, threading
    try:
        _run_copy(tmp_path, monkeypatch, ["a.jpg"], extra=HEARTBEAT_CFG,
                  progressor_error=RuntimeError("boom"))
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")
    alive = [th for th in threading.enumerate() if th.name == "status-heartbeat" and th.is_alive()]
    assert alive == []
    status = json.loads((tmp_path / "aws_upload_status.json").read_text(encoding="utf-8"))
    assert status["phase"] == "error"


def test_resume_with_nothing_left_still_publishes_final_heartbeat(tmp_path, monkeypatch):
    import json
    result, put_keys, _ = _run_copy(tmp_path, monkeypatch, ["a.jpg", "b.jpg"], extra=HEARTBEAT_CFG,
                                    prior_log_keys=["RMI1/a.jpg", "RMI1/b.jpg"])
    assert result["status"] == "completed" and result["skipped_from_log"] == 2
    assert put_keys == []
    final = json.loads(_run_copy.heartbeats[-1]["Body"].decode("utf-8"))
    assert final["phase"] == "complete" and final["meta"]["skipped_from_log"] == 2
