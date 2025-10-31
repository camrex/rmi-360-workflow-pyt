#!/usr/bin/env python3
"""
Example script demonstrating how to integrate with the Mosaic Processor monitoring system.

This script shows how to:
1. Read progress status from external scripts
2. Use monitoring in custom workflows
3. Handle monitoring completion events
4. Integrate with external systems

Note: Progress monitoring is now fully automatic - these examples are for
advanced integration scenarios only.

Usage:
    python example_mosaic_monitoring.py
"""

import time
import json
from pathlib import Path
from utils.mosaic_processor_monitor import MosaicProcessorMonitor


def example_basic_monitoring():
    """Example of basic monitoring setup and usage."""
    print("=== Basic Monitoring Example ===")

    # Set up paths (adjust these for your environment)
    input_reels_dir = Path("D:/project/reels")  # Contains reel folders with frame_times.csv
    output_base_dir = Path("D:/project/panos/original")  # Where JPEG files are generated
    status_file = Path("D:/project/logs/mosaic_progress.json")

    # Create monitor instance
    monitor = MosaicProcessorMonitor(
        input_reels_dir=input_reels_dir,
        output_base_dir=output_base_dir,
        status_file=status_file,
        check_interval=2.0  # Check every 2 seconds
    )

    # Start monitoring
    print("Starting monitoring...")
    if monitor.start_monitoring():
        print(f"✅ Monitoring started, status file: {status_file}")

        # Let it run for a while
        for i in range(10):
            time.sleep(1)

            # Get current status
            status = monitor.get_current_status()
            if status:
                total_percent = status['totals']['progress_percent']
                generated = status['totals']['generated_frames']
                expected = status['totals']['expected_frames']
                print(f"Progress: {total_percent:.1f}% ({generated}/{expected} frames)")

                # Check if complete
                if total_percent >= 100.0:
                    print("🎉 Processing complete!")
                    break

        # Stop monitoring
        print("Stopping monitoring...")
        monitor.stop_monitoring()
        print("✅ Monitoring stopped")
    else:
        print("❌ Failed to start monitoring")


def example_external_status_reading():
    """Example of reading status from an external process."""
    print("\n=== External Status Reading Example ===")
    print("Shows how external scripts can read the progress JSON file")

    status_file = Path("D:/project/logs/mosaic_progress.json")

    if status_file.exists():
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)

            print(f"Status file timestamp: {status.get('timestamp_iso', 'Unknown')}")
            print(f"Monitoring active: {status.get('monitoring', False)}")

            # Display overall progress
            totals = status.get('totals', {})
            print(f"Overall progress: {totals.get('progress_percent', 0):.1f}%")
            print(f"Frames: {totals.get('generated_frames', 0)}/{totals.get('expected_frames', 0)}")
            print(f"Reels complete: {totals.get('reels_completed', 0)}/{totals.get('reels_total', 0)}")

            # Display per-reel status
            reels = status.get('reels', {})
            if reels:
                print("\nPer-reel status:")
                for reel_name, reel_data in sorted(reels.items()):
                    percent = reel_data.get('progress_percent', 0)
                    completed = reel_data.get('completed', False)
                    status_icon = "✅" if completed else "🔄"
                    print(f"  {reel_name}: {percent:.1f}% {status_icon}")

        except Exception as e:
            print(f"❌ Error reading status file: {e}")
    else:
        print(f"❌ Status file not found: {status_file}")
        print("Note: Status file is created automatically when Mosaic Processor runs")


def example_progress_callback():
    """Example showing how to use monitoring with custom progress callbacks."""
    print("\n=== Progress Callback Example ===")

    class ProgressTracker:
        def __init__(self):
            self.last_reported = -1
            self.milestones = [25, 50, 75, 90, 100]

        def check_progress(self, monitor):
            """Check progress and report milestones."""
            status = monitor.get_current_status()
            if not status:
                return

            current_percent = status['totals']['progress_percent']

            # Report milestone achievements
            for milestone in self.milestones:
                if current_percent >= milestone > self.last_reported:
                    print(f"🎯 Milestone reached: {milestone}% complete!")

                    if milestone == 100:
                        print("🎉 All processing complete!")
                        return True

            self.last_reported = current_percent
            return False

    # Set up monitoring (adjust paths as needed)
    monitor = MosaicProcessorMonitor(
        input_reels_dir="D:/project/reels",
        output_base_dir="D:/project/panos/original",
        check_interval=1.0
    )

    tracker = ProgressTracker()

    if monitor.start_monitoring():
        print("Monitoring with progress callbacks...")

        try:
            while monitor.is_monitoring():
                time.sleep(2)
                if tracker.check_progress(monitor):
                    break
        except KeyboardInterrupt:
            print("\n👋 Interrupted by user")
        finally:
            monitor.stop_monitoring()


def example_integration_with_subprocess():
    """Example showing how monitoring integrates with subprocess execution."""
    print("\n=== Subprocess Integration Example ===")

    # This simulates how the monitoring works with the actual Mosaic Processor
    import subprocess
    from pathlib import Path

    def simulate_mosaic_process():
        """Simulate running Mosaic Processor with monitoring."""

        # Set up monitoring
        monitor = MosaicProcessorMonitor(
            input_reels_dir="D:/project/reels",
            output_base_dir="D:/project/panos/original",
            status_file="D:/project/logs/mosaic_progress.json",
            check_interval=3.0
        )

        # Start monitoring before launching subprocess
        print("Starting progress monitoring...")
        if not monitor.start_monitoring():
            print("❌ Failed to start monitoring")
            return

        try:
            # This is where you would normally run the actual Mosaic Processor
            # subprocess.run([mosaic_exe, input_dir, "--output_dir", output_dir, ...])

            # For demo purposes, we'll just simulate some progress
            print("🚀 Mosaic Processor simulation started...")
            print("   (In real usage, this would be the actual MistikaVR process)")

            # Simulate processing time
            for i in range(20):
                time.sleep(0.5)

                # Check current progress
                status = monitor.get_current_status()
                if status and i % 4 == 0:  # Log every 2 seconds
                    progress = status['totals']['progress_percent']
                    print(f"   Current progress: {progress:.1f}%")

                # Simulate early completion
                if status and status['totals']['progress_percent'] >= 100.0:
                    print("   ✅ Processing completed early!")
                    break

            print("🏁 Mosaic Processor simulation finished")

        except Exception as e:
            print(f"❌ Error during processing: {e}")
        finally:
            # Always stop monitoring
            print("Stopping progress monitoring...")
            monitor.stop_monitoring()

            # Show final status
            final_status = monitor.get_current_status()
            if final_status:
                totals = final_status['totals']
                print(f"📊 Final Status: {totals['generated_frames']}/{totals['expected_frames']} frames")
                print(f"   {totals['reels_completed']}/{totals['reels_total']} reels complete")

    simulate_mosaic_process()


if __name__ == "__main__":
    print("🔍 Mosaic Processor Monitoring Examples")
    print("=" * 50)

    # Note: These examples use placeholder paths
    # Adjust the paths to match your actual project structure

    try:
        example_basic_monitoring()
        example_external_status_reading()
        example_progress_callback()
        example_integration_with_subprocess()

    except KeyboardInterrupt:
        print("\n👋 Examples interrupted by user")
    except Exception as e:
        print(f"\n❌ Example error: {e}")

    print("\n✅ Examples completed")
    print("\nTo use with real data:")
    print("1. Ensure your reels have frame_times.csv files")
    print("2. Update the input/output paths in the examples")
    print("3. Run during actual Mosaic Processor execution")
