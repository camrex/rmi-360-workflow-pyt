"""Unit tests for utils/shared/s3_status_tracker.py — the publish (heartbeat) hook.

Loaded by file path: the module is pure stdlib and needs no arcpy or AWS.
"""

import importlib.util
import json
import pathlib

_spec = importlib.util.spec_from_file_location(
    "s3_status_tracker_under_test",
    pathlib.Path(__file__).resolve().parents[1] / "utils" / "shared" / "s3_status_tracker.py",
)
tracker_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tracker_mod)
StatusTracker = tracker_mod.StatusTracker


def test_publish_is_throttled_and_forced_on_finish(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(tracker_mod, "now_ts", lambda: clock["t"])
    sent = []
    tr = StatusTracker(None, interval_sec=1, publish=sent.append, publish_interval_sec=60)
    tr.set_totals(3)                      # first flush publishes (nothing sent yet)
    for _ in range(3):
        clock["t"] += 2                   # flushes are due, publishes are not
        tr.file_done("g", "uploaded", 10)
    assert len(sent) == 1
    clock["t"] += 61
    tr.file_done("g", "skipped", 10)      # publish interval elapsed
    assert len(sent) == 2
    tr.finish("complete")                 # always published
    assert len(sent) == 3
    final = json.loads(sent[-1])
    assert final["phase"] == "complete" and final["completed_at"] == clock["t"]
    assert final["totals"]["uploaded"] == 3 and final["totals"]["skipped"] == 1


def test_publish_failure_is_recorded_not_raised(tmp_path):
    def boom(_text):
        raise ConnectionError("no network")

    status = tmp_path / "status.json"
    tr = StatusTracker(status, publish=boom, meta={"project": "RMI1"})
    tr.file_done("g", "uploaded", 1)
    tr.finish("complete")
    assert tr.publish_error == "ConnectionError: no network"
    local = json.loads(status.read_text(encoding="utf-8"))   # local file still written
    assert local["phase"] == "complete" and local["meta"] == {"project": "RMI1"}


def test_no_publish_keeps_local_only_behaviour(tmp_path):
    status = tmp_path / "status.json"
    tr = StatusTracker(status)
    tr.set_totals(1)
    assert json.loads(status.read_text(encoding="utf-8"))["totals"]["files"] == 1
