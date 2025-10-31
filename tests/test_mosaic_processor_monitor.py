import pytest
import tempfile
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import csv

from utils.mosaic_processor_monitor import MosaicProcessorMonitor, create_monitor_from_config


class TestMosaicProcessorMonitor:

    def create_test_frame_times_csv(self, csv_path: Path, frame_count: int):
        """Create a test frame_times.csv file with specified frame count."""
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['frame', 'utc'])  # Header
            for i in range(frame_count):
                writer.writerow([i, f'2025-10-20 16:03:{52 + i}.953256491'])

    def create_test_output_files(self, output_dir: Path, file_count: int):
        """Create test JPEG files in output directory."""
        panos_dir = output_dir / "panos"
        panos_dir.mkdir(parents=True, exist_ok=True)
        for i in range(file_count):
            jpg_file = panos_dir / f"frame_{i:06d}.jpg"
            jpg_file.write_text("fake jpeg content")

    def test_read_frame_times_csv(self):
        """Test reading frame_times.csv files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test CSV
            csv_path = temp_path / "frame_times.csv"
            self.create_test_frame_times_csv(csv_path, 5)

            monitor = MosaicProcessorMonitor(
                input_reels_dir=str(temp_path),
                output_base_dir=str(temp_path)
            )

            count = monitor._read_frame_times_csv(csv_path)
            assert count == 5

    def test_scan_expected_frames(self):
        """Test scanning for expected frames across multiple reels."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test reel directories with frame_times.csv
            for reel_name, frame_count in [("reel_0001", 10), ("reel_0002", 15), ("reel_0003", 8)]:
                reel_dir = temp_path / reel_name
                csv_path = reel_dir / "frame_times.csv"
                self.create_test_frame_times_csv(csv_path, frame_count)

            monitor = MosaicProcessorMonitor(
                input_reels_dir=str(temp_path),
                output_base_dir=str(temp_path)
            )

            expected = monitor._scan_expected_frames()

            assert expected == {
                "reel_0001": 10,
                "reel_0002": 15,
                "reel_0003": 8
            }

    def test_count_generated_frames(self):
        """Test counting generated JPEG files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create output structure
            reel_output = temp_path / "reel_0001"
            self.create_test_output_files(reel_output, 7)

            monitor = MosaicProcessorMonitor(
                input_reels_dir=str(temp_path),
                output_base_dir=str(temp_path)
            )

            count = monitor._count_generated_frames("reel_0001")
            assert count == 7

            # Test non-existent reel
            count = monitor._count_generated_frames("reel_9999")
            assert count == 0

    def test_generate_status(self):
        """Test status generation with mock data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            monitor = MosaicProcessorMonitor(
                input_reels_dir=str(temp_path),
                output_base_dir=str(temp_path)
            )

            # Set up test data
            monitor._expected_frames = {"reel_0001": 10, "reel_0002": 5}

            # Mock the count function to return test values
            def mock_count(reel_name):
                return {"reel_0001": 7, "reel_0002": 5}.get(reel_name, 0)

            with patch.object(monitor, '_count_generated_frames', side_effect=mock_count):
                status = monitor._generate_status()

            # Check overall structure
            assert "timestamp" in status
            assert "reels" in status
            assert "totals" in status

            # Check reel-specific data
            assert status["reels"]["reel_0001"]["expected_frames"] == 10
            assert status["reels"]["reel_0001"]["generated_frames"] == 7
            assert status["reels"]["reel_0001"]["progress_percent"] == 70.0
            assert status["reels"]["reel_0001"]["completed"] == False

            assert status["reels"]["reel_0002"]["completed"] == True

            # Check totals
            assert status["totals"]["expected_frames"] == 15
            assert status["totals"]["generated_frames"] == 12
            assert status["totals"]["progress_percent"] == 80.0
            assert status["totals"]["reels_completed"] == 1
            assert status["totals"]["reels_total"] == 2

    def test_status_file_writing(self):
        """Test writing status to JSON file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            status_file = temp_path / "status.json"

            monitor = MosaicProcessorMonitor(
                input_reels_dir=str(temp_path),
                output_base_dir=str(temp_path),
                status_file=str(status_file)
            )

            test_status = {"test": "data", "timestamp": 12345}
            monitor._write_status_file(test_status)

            # Verify file was written
            assert status_file.exists()

            # Verify content
            with open(status_file, 'r') as f:
                loaded = json.load(f)

            assert loaded == test_status

    def test_create_monitor_from_config(self):
        """Test creating monitor from ConfigManager."""
        # Mock ConfigManager
        mock_cfg = MagicMock()
        mock_cfg.paths.original = Path("/test/output")
        mock_cfg.paths.get_log_file_path.return_value = Path("/test/logs/progress_log")
        mock_cfg.get_logger.return_value = MagicMock()

        monitor = create_monitor_from_config(mock_cfg, "/test/input")

        assert monitor.input_reels_dir == Path("/test/input")
        assert monitor.output_base_dir == Path("/test/output")
        assert monitor.status_file == Path("/test/logs/progress_log.json")

    def test_start_stop_monitoring(self):
        """Test starting and stopping the monitoring thread."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a reel with frame_times.csv
            reel_dir = temp_path / "reel_0001"
            csv_path = reel_dir / "frame_times.csv"
            self.create_test_frame_times_csv(csv_path, 3)

            monitor = MosaicProcessorMonitor(
                input_reels_dir=str(temp_path),
                output_base_dir=str(temp_path),
                check_interval=0.1  # Fast interval for testing
            )

            # Start monitoring
            assert monitor.start_monitoring() == True
            assert monitor.is_monitoring() == True

            # Let it run briefly
            time.sleep(0.2)

            # Stop monitoring
            monitor.stop_monitoring(timeout=2.0)
            assert monitor.is_monitoring() == False

    def test_monitor_completion_detection(self):
        """Test that monitor detects when all reels are complete."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a small test case
            reel_dir = temp_path / "reel_0001"
            csv_path = reel_dir / "frame_times.csv"
            self.create_test_frame_times_csv(csv_path, 2)  # Only 2 frames expected

            monitor = MosaicProcessorMonitor(
                input_reels_dir=str(temp_path),
                output_base_dir=str(temp_path),
                check_interval=0.1
            )

            # Start monitoring
            monitor.start_monitoring()

            # Initially, no frames generated
            time.sleep(0.15)
            status = monitor.get_current_status()
            assert status["totals"]["progress_percent"] == 0.0

            # Create the expected output files
            reel_output = temp_path / "reel_0001"
            self.create_test_output_files(reel_output, 2)

            # Wait for monitor to detect completion
            time.sleep(0.25)

            # Should detect completion and stop
            final_status = monitor.get_current_status()
            assert final_status["totals"]["progress_percent"] == 100.0
            assert final_status["totals"]["reels_completed"] == 1

            monitor.stop_monitoring()
