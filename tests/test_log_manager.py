import pytest
from utils.manager.log_manager import LogManager
from utils.manager.path_manager import PathManager
import json


@pytest.fixture
def tmp_log_manager(tmp_path):
    pm = PathManager(project_base=tmp_path)
    log = LogManager(config={"debug_messages": True}, path_manager=pm)
    return log, pm


def test_basic_logging(tmp_log_manager):
    log, _ = tmp_log_manager
    log.info("Hello world", context={"tool": "test"})
    assert any("Hello world" in msg for msg in log.get_messages())


def test_push_pop_structure(tmp_log_manager):
    log, _ = tmp_log_manager
    log.push("Start Block")
    log.info("Inside block")
    log.pop("End Block")

    msgs = log.get_messages()
    assert any("Start Block" in m for m in msgs)
    assert any("Inside block" in m for m in msgs)
    assert any("End Block" in m for m in msgs)


def test_step_context(tmp_log_manager):
    log, _ = tmp_log_manager
    with log.step("Sample Step"):
        log.debug("Doing stuff")
    assert any("Sample Step" in m and "Elapsed" in m for m in log.get_messages())


def test_export_all_creates_files(tmp_log_manager):
    log, pm = tmp_log_manager
    log.info("Export me!")

    log.export_all("logtest")
    logs_dir = pm.logs

    assert (logs_dir / "logtest.txt").exists()
    assert (logs_dir / "logtest.json").exists()
    assert (logs_dir / "logtest.html").exists()

    # Check JSON structure
    with open(logs_dir / "logtest.json", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert data[0]["message"] == "Export me!"


def test_no_path_manager_warning(capfd):
    log = LogManager(config={"debug_messages": True})
    log.export_all("testlog")
    out, _ = capfd.readouterr()
    assert "No PathManager" in out
