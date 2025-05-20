import pytest
from utils.shared.check_disk_space import check_sufficient_disk_space, find_base_dir

class DummyLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []
        self.errors = []
        self.debugs = []
    def info(self, msg):
        self.infos.append(msg)
    def warning(self, msg):
        self.warnings.append(msg)
    def error(self, msg, error_type=None):
        self.errors.append((msg, error_type))
        raise error_type(msg) if error_type else Exception(msg)
    def debug(self, msg):
        self.debugs.append(msg)

class DummyConfigManager:
    def __init__(self, logger=None, config=None):
        self._logger = logger or DummyLogger()
        self._config = config or {}
    def get_logger(self):
        return self._logger
    def get(self, key, default=None):
        return self._config.get(key, default)
    def get_progressor(self, total, label):
        class DummyProg:
            def __enter__(self_): return self_
            def __exit__(self_, exc_type, exc_val, exc_tb): return None
            def update(self_, i): pass
        return DummyProg()

# --- find_base_dir tests ---
def test_find_base_dir_found():
    path = r"C:/foo/bar/original/xyz"
    assert find_base_dir(path, "original") == r"C:/foo/bar/original"
    assert find_base_dir(path, "ORIGINAL") == r"C:/foo/bar/original"

def test_find_base_dir_not_found():
    path = r"C:/foo/bar/xyz"
    assert find_base_dir(path, "original") is None

# --- check_sufficient_disk_space tests ---

def test_disk_space_check_success(monkeypatch):
    logger = DummyLogger()
    cfg = DummyConfigManager(logger=logger, config={
        "disk_space.check_enabled": True,
        "disk_space.min_buffer_ratio": 1.1,
        "image_output.folders.original": "original",
        "image_output.folders.enhanced": "enhanced"
    })
    # Simulate a cursor returning a valid image path
    def fake_cursor(fc, fields):
        class DummyCursor:
            def __enter__(self_): return iter([[r"C:/foo/bar/original/xyz.jpg"]])
            def __exit__(self_, exc_type, exc_val, exc_tb): return None
        return DummyCursor()
    # Simulate folder size and disk usage
    def fake_folder_size(path, cfg): return 100
    class DummyDisk:
        free = 200
    def fake_disk_usage(drive): return DummyDisk()
    # Simulate folder exists
    monkeypatch.setattr("os.path.exists", lambda path: True)
    assert check_sufficient_disk_space(
        "dummy_fc", cfg,
        cursor_factory=fake_cursor,
        disk_usage_func=fake_disk_usage,
        folder_size_func=fake_folder_size
    ) is True

def test_disk_space_check_disabled():
    logger = DummyLogger()
    cfg = DummyConfigManager(logger=logger, config={"disk_space.check_enabled": False})
    assert check_sufficient_disk_space("dummy_fc", cfg) is True
    assert "Disk space check is disabled" in logger.infos[0]

def test_disk_space_insufficient(monkeypatch):
    logger = DummyLogger()
    cfg = DummyConfigManager(logger=logger, config={
        "disk_space.check_enabled": True,
        "disk_space.min_buffer_ratio": 2.0,
        "image_output.folders.original": "original",
        "image_output.folders.enhanced": "enhanced"
    })
    def fake_cursor(fc, fields):
        class DummyCursor:
            def __enter__(self_): return iter([[r"C:/foo/bar/original/xyz.jpg"]])
            def __exit__(self_, exc_type, exc_val, exc_tb): return None
        return DummyCursor()
    def fake_folder_size(path, cfg): return 100
    class DummyDisk:
        free = 100  # Not enough!
    def fake_disk_usage(drive): return DummyDisk()
    monkeypatch.setattr("os.path.exists", lambda path: True)
    with pytest.raises(RuntimeError):
        check_sufficient_disk_space(
            "dummy_fc", cfg,
            cursor_factory=fake_cursor,
            disk_usage_func=fake_disk_usage,
            folder_size_func=fake_folder_size
        )

def test_no_valid_image_path(monkeypatch):
    logger = DummyLogger()
    cfg = DummyConfigManager(logger=logger)
    def fake_cursor(fc, fields):
        class DummyCursor:
            def __enter__(self_): return iter([[None]])
            def __exit__(self_, exc_type, exc_val, exc_tb): return None
        return DummyCursor()
    monkeypatch.setattr("os.path.exists", lambda path: True)
    with pytest.raises(ValueError):
        check_sufficient_disk_space(
            "dummy_fc", cfg,
            cursor_factory=fake_cursor,
            disk_usage_func=lambda x: type("Dummy", (), {"free": 1000})(),
            folder_size_func=lambda x, y: 1
        )

def test_base_dir_not_found(monkeypatch):
    logger = DummyLogger()
    cfg = DummyConfigManager(logger=logger, config={"image_output.folders.original": "original"})
    def fake_cursor(fc, fields):
        class DummyCursor:
            def __enter__(self_): return iter([[r"C:/foo/bar/xyz.jpg"]])
            def __exit__(self_, exc_type, exc_val, exc_tb): return None
        return DummyCursor()
    monkeypatch.setattr("os.path.exists", lambda path: True)
    with pytest.raises(ValueError):
        check_sufficient_disk_space(
            "dummy_fc", cfg,
            cursor_factory=fake_cursor,
            disk_usage_func=lambda x: type("Dummy", (), {"free": 1000})(),
            folder_size_func=lambda x, y: 1
        )

def test_base_dir_does_not_exist(monkeypatch):
    logger = DummyLogger()
    cfg = DummyConfigManager(logger=logger, config={"image_output.folders.original": "original"})
    def fake_cursor(fc, fields):
        class DummyCursor:
            def __enter__(self_): return iter([[r"C:/foo/bar/original/xyz.jpg"]])
            def __exit__(self_, exc_type, exc_val, exc_tb): return None
        return DummyCursor()
    monkeypatch.setattr("os.path.exists", lambda path: False)
    with pytest.raises(FileNotFoundError):
        check_sufficient_disk_space(
            "dummy_fc", cfg,
            cursor_factory=fake_cursor,
            disk_usage_func=lambda x: type("Dummy", (), {"free": 1000})(),
            folder_size_func=lambda x, y: 1
        )
