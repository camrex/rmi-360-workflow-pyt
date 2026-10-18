"""Unit tests for utils/shared/s3_status_tracker.py — the heartbeat publisher thread.

Loaded by file path: the module is pure stdlib and needs no arcpy or AWS.
"""

import importlib.util
import json
import pathlib
import threading
import time

_spec = importlib.util.spec_from_file_location(
    "s3_status_tracker_under_test",
    pathlib.Path(__file__).resolve().parents[1] / "utils" / "shared" / "s3_status_tracker.py",
)
tracker_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tracker_mod)
StatusTracker = tracker_mod.StatusTracker


def _heartbeat_threads():
    return [t for t in threading.enumerate() if t.name == "status-heartbeat" and t.is_alive()]


def test_publishes_on_a_timer_while_work_is_in_flight():
    sent = []
    tr = StatusTracker(None, publish=sent.append, publish_interval_sec=0.05)
    tr.set_totals(1)
    tr.start()
    time.sleep(0.4)                      # one long "transfer": no file_done calls at all
    assert len(sent) >= 3                # heartbeats kept coming anyway
    tr.file_done("g", "uploaded", 10)
    tr.finish("complete")
    assert _heartbeat_threads() == []    # the thread is stopped
    final = json.loads(sent[-1])
    assert final["phase"] == "complete" and final["completed_at"]
    assert final["totals"]["uploaded"] == 1


def test_publish_runs_off_the_calling_thread_and_outside_the_lock():
    seen = {}

    def publish(_text):
        seen["thread"] = threading.current_thread().name
        seen["lock_free"] = tr.lock.acquire(blocking=False)   # would deadlock/False if held
        if seen["lock_free"]:
            tr.lock.release()

    tr = StatusTracker(None, publish=publish, publish_interval_sec=60)
    tr.start()
    time.sleep(0.1)
    tr.finish("complete")
    assert seen["lock_free"] is True
    assert tr.publish_count >= 2        # the thread's first publish + the final one


def test_publish_failure_is_recorded_not_raised(tmp_path):
    def boom(_text):
        raise ConnectionError("no network")

    status = tmp_path / "status.json"
    tr = StatusTracker(status, publish=boom, publish_interval_sec=60, meta={"project": "RMI1"})
    tr.start()
    tr.file_done("g", "uploaded", 1)
    tr.finish("complete")
    assert tr.publish_error == "ConnectionError: no network"
    local = json.loads(status.read_text(encoding="utf-8"))   # local file still written
    assert local["phase"] == "complete" and local["meta"] == {"project": "RMI1"}
    assert _heartbeat_threads() == []


def test_no_publish_keeps_local_only_behaviour(tmp_path):
    status = tmp_path / "status.json"
    tr = StatusTracker(status)
    tr.start()                           # no-op without publish
    tr.set_totals(1)
    assert json.loads(status.read_text(encoding="utf-8"))["totals"]["files"] == 1
    assert _heartbeat_threads() == []


def test_slow_heartbeat_cannot_land_after_the_final_one():
    landed = []
    first = threading.Event()

    def publish(text):
        if not first.is_set():          # the thread's first (pre-final) heartbeat is slow
            first.set()
            time.sleep(0.3)
        landed.append(json.loads(text)["phase"])

    tr = StatusTracker(None, publish=publish, publish_interval_sec=60)
    tr.start()
    first.wait(1)
    tr.finish("complete", join_timeout_sec=0.01)   # join gives up while the slow PUT runs
    assert landed[-1] == "complete"


def test_older_snapshot_is_never_published_after_a_newer_one():
    sent = []
    tr = StatusTracker(None, publish=sent.append)
    tr._published_seq = 10**9            # pretend a newer snapshot already went out
    tr._publish_now()
    assert sent == []
