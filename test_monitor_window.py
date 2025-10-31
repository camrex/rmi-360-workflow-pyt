#!/usr/bin/env python3
"""
Test script to verify the progress monitor window launches correctly.

This script tests the launch_progress_monitor_window function to ensure
it properly opens a separate CLI window for monitoring.
"""

import tempfile
import time
from pathlib import Path
from utils.mosaic_processor import launch_progress_monitor_window
from utils.manager.config_manager import ConfigManager


def test_launch_monitor_window():
    """Test launching the progress monitor window."""
    print("🧪 Testing progress monitor window launch...")
    print("   Note: Now uses utils/mosaic_progress_display.py (internal component)")

    # Create a temporary status file for testing
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as temp_file:
        status_file = Path(temp_file.name)

        # Write some test status data
        import json
        test_status = {
            "timestamp_iso": "2025-10-31 15:30:00",
            "monitoring": True,
            "reels": {
                "reel_0001": {
                    "expected_frames": 100,
                    "generated_frames": 50,
                    "progress_percent": 50.0,
                    "completed": False
                }
            },
            "totals": {
                "expected_frames": 100,
                "generated_frames": 50,
                "progress_percent": 50.0,
                "reels_completed": 0,
                "reels_total": 1
            }
        }

        with open(status_file, 'w') as f:
            json.dump(test_status, f, indent=2)

    try:
        # Create a mock logger
        class MockLogger:
            def warning(self, msg, indent=0):
                print(f"⚠️  {msg}")
            def info(self, msg, indent=0):
                print(f"ℹ️  {msg}")

        logger = MockLogger()

        # Test launching the window
        print(f"📂 Using status file: {status_file}")
        process = launch_progress_monitor_window(status_file, logger)

        if process:
            print("✅ Monitor window launched successfully!")
            print("   A new command prompt window should have opened showing progress.")
            print("   The window will monitor the test status file.")

            # Let it run for a moment
            print("   Letting it run for 10 seconds...")
            time.sleep(10)

            # Update the status to show completion
            test_status["totals"]["generated_frames"] = 100
            test_status["totals"]["progress_percent"] = 100.0
            test_status["reels"]["reel_0001"]["generated_frames"] = 100
            test_status["reels"]["reel_0001"]["progress_percent"] = 100.0
            test_status["reels"]["reel_0001"]["completed"] = True
            test_status["monitoring"] = False

            with open(status_file, 'w') as f:
                json.dump(test_status, f, indent=2)

            print("   Updated status to show completion - window should close automatically")

            # Clean up
            try:
                process.terminate()
            except:
                pass

            print("✅ Test completed successfully!")

        else:
            print("❌ Failed to launch monitor window")
            return False

    finally:
        # Clean up temp file
        try:
            status_file.unlink()
        except:
            pass

    return True


def test_integration_example():
    """Show how this integrates with the full workflow."""
    print("\n🔗 Integration Example:")
    print("   When run_mosaic_processor() is called:")
    print("   1. Progress monitor starts in background thread")
    print("   2. Separate CLI window opens automatically")
    print("   3. Window shows real-time progress as MistikaVR runs")
    print("   4. Window closes automatically when complete")
    print("   5. Main ArcGIS Pro tool continues normally")
    print("\n   Benefits:")
    print("   ✅ User sees progress without blocking ArcGIS Pro")
    print("   ✅ No manual intervention required")
    print("   ✅ Clean separation of concerns")
    print("   ✅ Works even if ArcGIS Pro UI is blocked")


if __name__ == "__main__":
    print("🖥️  Mosaic Processor Progress Monitor Window Test")
    print("=" * 60)

    print("\nThis test will:")
    print("1. Create a temporary status file")
    print("2. Launch the progress monitor window")
    print("3. Show test progress data")
    print("4. Automatically close when complete")

    input("\nPress Enter to start the test...")

    try:
        success = test_launch_monitor_window()
        test_integration_example()

        if success:
            print("\n🎉 All tests passed!")
        else:
            print("\n❌ Some tests failed")

    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()

    input("\nPress Enter to exit...")
