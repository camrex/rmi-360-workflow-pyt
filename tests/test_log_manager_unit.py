import pytest
from utils.manager.log_manager import LogManager
from pathlib import Path

class DummyPathManager:
    def __init__(self, tmpdir):
        self.tmpdir = Path(tmpdir)
    @property
    def logs(self):
        logs_dir = self.tmpdir / "logs"
        logs_dir.mkdir(exist_ok=True)
        return logs_dir
    def get_log_file_path(self, name):
        return self.tmpdir / f"{name}.txt"
    def get_html_log_file_path(self, name):
        return self.tmpdir / f"{name}.html"
    def get_json_log_file_path(self, name):
        return self.tmpdir / f"{name}.json"

@pytest.fixture
def dummy_path_manager(tmp_path):
    return DummyPathManager(tmp_path)

@pytest.fixture
def minimal_config():
    return {"logs": {"log_folder": "logs"}}


def test_init_default():
    lm = LogManager()
    assert lm.config == {}
    assert lm.path_manager is None


def test_init_with_path_manager(dummy_path_manager):
    lm = LogManager(path_manager=dummy_path_manager)
    assert lm.path_manager is dummy_path_manager


def test_info_and_debug_logging(caplog):
    lm = LogManager(config={"debug_messages": True})
    with caplog.at_level("INFO"):
        lm.info("Hello info!")
        lm.debug("Hello debug!")
    # Should appear in internal log buffer
    assert any("Hello info!" in r for r in lm.entries)
    assert any("Hello debug!" in r for r in lm.entries)


def test_warning_and_error_logging(caplog):
    lm = LogManager()
    with caplog.at_level("WARNING"):
        lm.warning("Warn!")
        with pytest.raises(RuntimeError):
            lm.error("Err!")
    assert any("Warn!" in r for r in lm.entries)
    # Error log raises, so we do not check for its presence in entries here


def test_context_and_indentation():
    lm = LogManager()
    lm.push("tool")
    lm.info("Start", context={"tool": "enhance"})
    lm.pop()
    assert "tool" in str(lm.entries) or "tool" in str(lm.records)


def test_file_output(tmp_path, dummy_path_manager):
    lm = LogManager(path_manager=dummy_path_manager, enable_file_output=True)
    lm.info("Write to file")
    # Just check that log buffer contains the message
    assert any("Write to file" in r for r in lm.entries)


def test_party_and_success_methods():
    lm = LogManager()
    lm.party()
    lm.success()
    assert any("party" in r.lower() or "success" in r.lower() for r in lm.entries)


def test_empty_config():
    lm = LogManager(config=None)
    lm.info("No config")
    assert any("No config" in r for r in lm.entries)
