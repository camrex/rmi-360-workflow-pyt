import pytest
from unittest.mock import Mock, patch
from utils.step_runner import run_steps

class DummyLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []
        self.errors = []
        self.step_calls = []
    def info(self, msg):
        self.infos.append(msg)
    def warning(self, msg):
        self.warnings.append(msg)
    def error(self, msg, error_type=None):
        self.errors.append((msg, error_type))
    def step(self, label):
        # Context manager for 'with logger.step(label)'
        self.step_calls.append(label)
        class DummyCtx:
            def __enter__(self_): return None
            def __exit__(self_, exc_type, exc_val, exc_tb): return None
        return DummyCtx()

class DummyConfigManager:
    def __init__(self, logger=None):
        self._logger = logger or DummyLogger()
    def get_logger(self):
        return self._logger

@pytest.fixture
def dummy_report():
    return {"steps": []}

@pytest.fixture
def dummy_cfg():
    return DummyConfigManager()

def test_all_steps_succeed(dummy_report, dummy_cfg):
    step_funcs = {
        "a": {"label": "Step A", "func": Mock()},
        "b": {"label": "Step B", "func": Mock()}
    }
    step_order = ["a", "b"]
    with patch("utils.step_runner.save_report_json"):
        results = run_steps(step_funcs, step_order, 0, {}, dummy_report, dummy_cfg)
    assert all(r["status"] == "✅" for r in results)
    assert len(dummy_report["steps"]) == 2

def test_step_skipped(dummy_report, dummy_cfg):
    step_funcs = {
        "a": {"label": "Step A", "func": Mock(), "skip": lambda p: "skip reason"},
        "b": {"label": "Step B", "func": Mock()}
    }
    step_order = ["a", "b"]
    with patch("utils.step_runner.save_report_json"):
        results = run_steps(step_funcs, step_order, 0, {}, dummy_report, dummy_cfg)
    assert results[0]["status"] == "⏭️"
    assert results[1]["status"] == "✅"
    assert dummy_report["steps"][0]["notes"] == "skip reason"

def test_step_fails_and_stops(dummy_report, dummy_cfg):
    def fail_func(**kwargs):
        raise RuntimeError("fail here")
    step_funcs = {
        "a": {"label": "Step A", "func": fail_func},
        "b": {"label": "Step B", "func": Mock()}
    }
    step_order = ["a", "b"]
    with patch("utils.step_runner.save_report_json"):
        results = run_steps(step_funcs, step_order, 0, {}, dummy_report, dummy_cfg)
    assert results[0]["status"] == "❌"
    assert len(results) == 1

def test_oid_backup_triggered(dummy_report, dummy_cfg):
    step_funcs = {
        "a": {"label": "Step A", "func": Mock()},
    }
    step_order = ["a"]
    wait_config = {"backup_oid_between_steps": True, "backup_before_step": ["a"]}
    with patch("utils.step_runner.save_report_json"), \
         patch("utils.step_runner.backup_oid") as mock_backup_oid:
        results = run_steps(step_funcs, step_order, 0, {"oid_fc": "OID"}, dummy_report, dummy_cfg, wait_config)
    assert results[0]["backup_created"] == "true"
    mock_backup_oid.assert_called_once_with("OID", "a", dummy_cfg)

def test_wait_triggered(dummy_report, dummy_cfg):
    step_funcs = {
        "a": {"label": "Step A", "func": Mock()},
    }
    step_order = ["a"]
    wait_config = {"wait_between_steps": True, "wait_before_step": ["a"], "wait_duration_sec": 0}
    with (patch("utils.step_runner.save_report_json"), \
          patch("utils.step_runner.backup_oid"), \
          patch("utils.step_runner.time.sleep") as mock_sleep):
        results = run_steps(step_funcs, step_order, 0, {}, dummy_report, dummy_cfg, wait_config)
    assert results[0]["status"] == "✅"
    # Verify that sleep was called, indicating wait was triggered
    mock_sleep.assert_called_once_with(0)

# Additional test: report_data missing 'steps' key

def test_report_data_missing_steps_key(dummy_cfg):
    step_funcs = {
        "a": {"label": "Step A", "func": Mock()},
    }
    step_order = ["a"]
    report_data = {}
    with patch("utils.step_runner.save_report_json"):
        results = run_steps(step_funcs, step_order, 0, {}, report_data, dummy_cfg)
    assert "steps" in report_data
    assert results[0]["status"] == "✅"
