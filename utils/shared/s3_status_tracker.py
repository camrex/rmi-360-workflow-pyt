#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
s3_status_tracker.py
====================

Thread-safe status tracking for S3 uploads with JSON heartbeat.

Tracks upload progress globally and per-group (reels, folder types, etc.)
with live JSON status file updates.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional


def now_ts() -> float:
    """Current timestamp."""
    return time.time()


def atomic_write_text(path: Path, text: str) -> None:
    """Atomic file write using temp file + rename."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


class StatusTracker:
    """
    Thread-safe, throttled JSON status writer with per-group and global stats.

    Groups can represent reels, folder types, or any logical collection of files.

    Methods:
        set_totals(n): Set total file count
        start_group(name, planned_files): Begin tracking a group
        complete_group(name): Mark group as complete
        start_file(group, fpath, size): Begin file upload
        file_progress_cb(group): Get progress callback for boto3
        file_done(group, outcome, size): Mark file complete
        note_skip(group): Note a skipped file
    """

    def __init__(self, status_path: Optional[Path], interval_sec: float = 2.0, group_key: str = "groups"):
        """
        Initialize status tracker.

        Args:
            status_path: Path to write JSON status (None to disable)
            interval_sec: Minimum seconds between JSON writes (throttling)
            group_key: JSON key for groups (e.g., "reels", "folder_types")
        """
        self.status_path = status_path
        self.interval = max(0.2, float(interval_sec))
        self.group_key = group_key
        self.lock = threading.Lock()
        self.last_flush = 0.0
        self.data = {
            "started_at": now_ts(),
            "phase": "init",
            f"current_{group_key.rstrip('s')}": None,
            "current_file": None,
            "current_file_bytes": 0,
            "current_file_size": 0,
            "totals": {"files": 0, "uploaded": 0, "skipped": 0, "failed": 0, "bytes_uploaded": 0},
            group_key: {},
            "last_update": now_ts(),
        }

    def set_totals(self, total_files: int):
        """Set total number of files to process."""
        with self.lock:
            self.data["totals"]["files"] = int(total_files)
            self._flush_if_due()

    def start_group(self, group: str, planned_files: int):
        """Begin processing a group."""
        with self.lock:
            self.data["phase"] = f"{self.group_key.rstrip('s')}_start"
            self.data[f"current_{self.group_key.rstrip('s')}"] = group
            self.data[self.group_key].setdefault(group, {
                "planned_files": planned_files,
                "uploaded": 0,
                "skipped": 0,
                "failed": 0,
                "bytes_uploaded": 0,
                "started_at": now_ts(),
                "completed_at": None
            })
            self._flush(force=True)

    def complete_group(self, group: str):
        """Mark a group as completed."""
        with self.lock:
            g = self.data[self.group_key].get(group)
            if g:
                g["completed_at"] = now_ts()
            self.data["phase"] = f"{self.group_key.rstrip('s')}_complete"
            self.data["current_file"] = None
            self.data["current_file_bytes"] = 0
            self.data["current_file_size"] = 0
            self._flush(force=True)

    def start_file(self, group: str, fpath: Path, size: int):
        """Begin uploading a file."""
        with self.lock:
            self.data["phase"] = "uploading"
            self.data[f"current_{self.group_key.rstrip('s')}"] = group
            self.data["current_file"] = str(fpath)
            self.data["current_file_bytes"] = 0
            self.data["current_file_size"] = int(size)
            self._flush_if_due()

    def file_progress_cb(self, group: str):
        """
        Get boto3-compatible progress callback for a file.

        Returns:
            Callback function(bytes_amount) for boto3 transfer
        """
        def _cb(bytes_amount: int):
            with self.lock:
                self.data["current_file_bytes"] += int(bytes_amount)
                self._flush_if_due()
        return _cb

    def file_done(self, group: str, outcome: str, size: int):
        """
        Mark file upload complete.

        Args:
            group: Group name
            outcome: "uploaded", "skipped", or "error"
            size: File size in bytes
        """
        with self.lock:
            g = self.data[self.group_key].setdefault(group, {
                "planned_files": 0,
                "uploaded": 0,
                "skipped": 0,
                "failed": 0,
                "bytes_uploaded": 0,
                "started_at": now_ts(),
                "completed_at": None
            })

            if outcome == "uploaded":
                g["uploaded"] += 1
                g["bytes_uploaded"] += int(size)
                self.data["totals"]["uploaded"] += 1
                self.data["totals"]["bytes_uploaded"] += int(size)
            elif outcome == "skipped":
                g["skipped"] += 1
                self.data["totals"]["skipped"] += 1
            else:
                g["failed"] += 1
                self.data["totals"]["failed"] += 1

            self.data["current_file"] = None
            self.data["current_file_bytes"] = 0
            self.data["current_file_size"] = 0
            self._flush_if_due()

    def note_skip(self, group: str):
        """Note a skipped file without full file_done tracking."""
        with self.lock:
            g = self.data[self.group_key].setdefault(group, {
                "planned_files": 0,
                "uploaded": 0,
                "skipped": 0,
                "failed": 0,
                "bytes_uploaded": 0,
                "started_at": now_ts(),
                "completed_at": None
            })
            g["skipped"] += 1
            self.data["totals"]["skipped"] += 1
            self._flush_if_due()

    def _flush_if_due(self):
        """Flush JSON if enough time has passed since last flush."""
        if not self.status_path:
            return
        now = now_ts()
        if (now - self.last_flush) >= self.interval:
            self._flush()

    def _flush(self, force: bool = False):
        """Write JSON status to disk."""
        if not self.status_path:
            return
        self.data["last_update"] = now_ts()
        atomic_write_text(self.status_path, json.dumps(self.data, ensure_ascii=False, indent=2))
        self.last_flush = now_ts()
