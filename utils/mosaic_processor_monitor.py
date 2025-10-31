# =============================================================================
# 📊 Mosaic Processor Progress Monitor (utils/mosaic_processor_monitor.py)
# -----------------------------------------------------------------------------
# Purpose:             Monitors Mosaic Processor/MistikaVR progress by tracking output files
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-10-31
# Last Updated:        2025-10-31
#
# Description:
#   Provides real-time progress monitoring for Mosaic Processor operations by:
#   1. Reading frame_times.csv files to determine expected frame counts per reel
#   2. Monitoring output directories for generated JPEG files
#   3. Writing progress status to JSON files for external monitoring
#   4. Running as a background subprocess during Mosaic Processor execution
#
# File Location:        /utils/mosaic_processor_monitor.py
# Called By:            utils/mosaic_processor.py
# Int. Dependencies:    utils/manager/config_manager
# Ext. Dependencies:    os, csv, json, time, threading, pathlib
#
# =============================================================================
import os
import csv
import json
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

__all__ = ["MosaicProcessorMonitor"]


class MosaicProcessorMonitor:
    """
    Monitors Mosaic Processor progress by tracking expected vs actual frame generation.

    This class runs in a separate thread and periodically checks:
    1. Expected frame counts from frame_times.csv files in input reel folders
    2. Actual generated JPEG files in output reel directories
    3. Updates progress status in a JSON file for external monitoring
    """

    def __init__(
        self,
        input_reels_dir: str,
        output_base_dir: str,
        status_file: Optional[str] = None,
        check_interval: float = 5.0,
        logger=None,
        progress_callback=None
    ):
        """
        Initialize the monitor.

        Args:
            input_reels_dir: Directory containing reel folders with frame_times.csv files
            output_base_dir: Base output directory (project_folder/panos/original)
            status_file: Optional path to write JSON status updates
            check_interval: Seconds between progress checks
            logger: Optional LogManager instance from ConfigManager.get_logger()
            progress_callback: Optional callback function to receive progress updates
        """
        self.input_reels_dir = Path(input_reels_dir)
        self.output_base_dir = Path(output_base_dir)
        self.status_file = Path(status_file) if status_file else None
        self.check_interval = check_interval
        self.logger = logger or self._create_null_logger()
        self.progress_callback = progress_callback

        self._stop_event = threading.Event()
        self._monitor_thread = None
        self._expected_frames = {}
        self._last_status = {}
        self._last_callback_percent = -1

    def _create_null_logger(self):
        """Create a null logger that discards all log messages for testing."""
        class NullLogger:
            def info(self, msg, indent=0): pass
            def warning(self, msg, indent=0): pass
            def error(self, msg, indent=0): pass
            def success(self, msg, indent=0): pass
            def debug(self, msg, indent=0): pass
        return NullLogger()

    def _read_frame_times_csv(self, csv_path: Path) -> int:
        """
        Read frame_times.csv and return the number of expected frames.

        Args:
            csv_path: Path to the frame_times.csv file

        Returns:
            Number of frames expected, or 0 if file can't be read
        """
        try:
            # csv module recommends opening files with newline='' to handle newlines consistently
            with open(csv_path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                frame_count = sum(1 for _ in reader)
                return frame_count
        except Exception as e:
            self.logger.warning(f"Failed to read {csv_path}: {e}", indent=2)
            return 0

    def _scan_expected_frames(self) -> Dict[str, int]:
        """
        Scan input reel directories for frame_times.csv files and count expected frames.

        Returns:
            Dictionary mapping reel names to expected frame counts
        """
        expected = {}

        if not self.input_reels_dir.exists():
            self.logger.warning(f"Input reels directory not found: {self.input_reels_dir}", indent=2)
            return expected

        for reel_dir in self.input_reels_dir.iterdir():
            if not reel_dir.is_dir():
                continue

            reel_name = reel_dir.name
            frame_times_csv = reel_dir / "frame_times.csv"

            if frame_times_csv.exists():
                count = self._read_frame_times_csv(frame_times_csv)
                if count > 0:
                    expected[reel_name] = count
                    self.logger.info(f"Reel {reel_name}: expecting {count} frames", indent=2)
                else:
                    self.logger.warning(f"Reel {reel_name}: frame_times.csv found but no frames counted", indent=2)
            else:
                self.logger.warning(f"Reel {reel_name}: no frame_times.csv found", indent=2)

        return expected

    def _count_generated_frames(self, reel_name: str) -> int:
        """
        Count generated image files for a specific reel.

        Args:
            reel_name: Name of the reel to check

        Returns:
            Number of JPEG files found in the reel's output directory
        """
        # Output path: <output_base_dir>/reel_XXXX/panos/
        reel_output_dir = self.output_base_dir / reel_name / "panos"

        if not reel_output_dir.exists():
            return 0

        # Count common JPEG extensions (case insensitive)
        valid_suffixes = {'.jpg', '.jpeg'}
        image_count = sum(
            1 for f in reel_output_dir.iterdir()
            if f.is_file() and f.suffix.lower() in valid_suffixes
        )

        return image_count

    def _generate_status(self) -> Dict:
        """
        Generate current status including progress for each reel and overall totals.

        Returns:
            Status dictionary with reel-by-reel and overall progress
        """
        status = {
            "timestamp": time.time(),
            "timestamp_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "monitoring": True,
            "reels": {},
            "totals": {
                "expected_frames": 0,
                "generated_frames": 0,
                "progress_percent": 0.0,
                "reels_completed": 0,
                "reels_total": len(self._expected_frames)
            }
        }

        total_expected = 0
        total_generated = 0
        reels_completed = 0

        for reel_name, expected_count in self._expected_frames.items():
            generated_count = self._count_generated_frames(reel_name)
            progress_pct = (generated_count / expected_count * 100) if expected_count > 0 else 0
            is_complete = generated_count >= expected_count

            reel_status = {
                "expected_frames": expected_count,
                "generated_frames": generated_count,
                "progress_percent": round(progress_pct, 1),
                "completed": is_complete
            }

            status["reels"][reel_name] = reel_status

            total_expected += expected_count
            total_generated += generated_count
            if is_complete:
                reels_completed += 1

        # Update totals
        status["totals"]["expected_frames"] = total_expected
        status["totals"]["generated_frames"] = total_generated
        status["totals"]["progress_percent"] = round(
            (total_generated / total_expected * 100) if total_expected > 0 else 0, 1
        )
        status["totals"]["reels_completed"] = reels_completed

        return status

    def _write_status_file(self, status: Dict):
        """Write status to JSON file if configured."""
        if not self.status_file:
            return

        try:
            # Ensure parent directory exists
            self.status_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.status_file, 'w', encoding='utf-8') as f:
                json.dump(status, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to write status file {self.status_file}: {e}", indent=2)

    def _monitor_loop(self):
        """Main monitoring loop that runs in a separate thread."""
        self.logger.info("📊 Starting Mosaic Processor monitoring...", indent=2)

        # Initial scan of expected frames
        self._expected_frames = self._scan_expected_frames()

        if not self._expected_frames:
            self.logger.warning("No reels with frame_times.csv found - monitoring disabled", indent=2)
            status = self._generate_status()
            status["monitoring"] = False
            status["message"] = "No frame_times.csv found; monitoring disabled"
            self._write_status_file(status)
            self._last_status = status
            return

        total_expected = sum(self._expected_frames.values())
        self.logger.info(f"Monitoring {len(self._expected_frames)} reels, {total_expected} total expected frames", indent=2)

        while not self._stop_event.is_set():
            try:
                # Generate current status
                status = self._generate_status()

                # Write to file if configured
                self._write_status_file(status)

                # Log progress if it changed significantly or call callback
                current_progress = status["totals"]["progress_percent"]
                last_progress = self._last_status.get("totals", {}).get("progress_percent", -1)

                # Report progress at 5% intervals and completion
                should_report = (
                    abs(current_progress - last_progress) >= 5.0 or
                    current_progress == 100.0
                )

                if should_report:
                    completed_reels = status["totals"]["reels_completed"]
                    total_reels = status["totals"]["reels_total"]
                    generated = status["totals"]["generated_frames"]
                    expected = status["totals"]["expected_frames"]

                    progress_msg = (
                        f"Progress: {current_progress:.1f}% "
                        f"({generated:,}/{expected:,} frames, {completed_reels}/{total_reels} reels complete)"
                    )
                    self.logger.info(progress_msg, indent=2)

                    # Call progress callback if provided
                    if self.progress_callback and abs(current_progress - self._last_callback_percent) >= 5.0:
                        try:
                            self.progress_callback(status)
                            self._last_callback_percent = current_progress
                        except Exception as e:
                            self.logger.warning(f"Progress callback error: {e}", indent=2)

                self._last_status = status

                # Check if all reels are complete
                if status["totals"]["reels_completed"] == status["totals"]["reels_total"] and status["totals"]["reels_total"] > 0:
                    self.logger.success("🎉 All reels completed!", indent=2)
                    break

            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}", indent=2)

            # Wait for next check or stop signal
            if self._stop_event.wait(self.check_interval):
                break

        # Final status update
        try:
            final_status = self._generate_status()
            final_status["monitoring"] = False
            final_status["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            self._write_status_file(final_status)
            self.logger.success("📊 Monitoring completed", indent=2)
        except Exception as e:
            self.logger.error(f"Error writing final status: {e}", indent=2)

    def start_monitoring(self) -> bool:
        """
        Start monitoring in a background thread.

        Returns:
            True if monitoring started successfully, False otherwise
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            self.logger.warning("Monitoring is already running", indent=2)
            return False

        try:
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()
            return True
        except Exception as e:
            self.logger.error(f"Failed to start monitoring: {e}", indent=2)
            return False

    def stop_monitoring(self, timeout: float = 10.0):
        """
        Stop monitoring and wait for thread to finish.

        Args:
            timeout: Maximum seconds to wait for thread to stop
        """
        if not self._monitor_thread or not self._monitor_thread.is_alive():
            return

        self.logger.info("Stopping monitoring...", indent=2)
        self._stop_event.set()

        try:
            self._monitor_thread.join(timeout)
            if self._monitor_thread.is_alive():
                self.logger.warning("Monitoring thread did not stop within timeout", indent=2)
        except Exception as e:
            self.logger.error(f"Error stopping monitoring: {e}", indent=2)

    def get_current_status(self) -> Optional[Dict]:
        """
        Get the current monitoring status.

        Returns:
            Status dictionary or None if monitoring not active
        """
        if not self._expected_frames:
            return None

        return self._generate_status()

    def is_monitoring(self) -> bool:
        """Check if monitoring is currently active."""
        return self._monitor_thread and self._monitor_thread.is_alive()


def create_monitor_from_config(cfg, input_reels_dir: str, progress_callback=None) -> MosaicProcessorMonitor:
    """
    Create a MosaicProcessorMonitor instance configured from ConfigManager.

    Args:
        cfg: ConfigManager instance
        input_reels_dir: Path to input reels directory
        progress_callback: Optional function to call with progress updates

    Returns:
        Configured MosaicProcessorMonitor instance
    """
    output_base_dir = cfg.paths.original  # project_folder/panos/original
    status_file = cfg.paths.get_log_file_path("mosaic_processor_progress", cfg).with_suffix('.json')

    return MosaicProcessorMonitor(
        input_reels_dir=input_reels_dir,
        output_base_dir=str(output_base_dir),
        status_file=str(status_file),
        check_interval=5.0,
        logger=cfg.get_logger(),
        progress_callback=progress_callback
    )
