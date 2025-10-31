#!/usr/bin/env python3
# =============================================================================
# 🖥️ Mosaic Processor Progress Display (utils/mosaic_progress_display.py)
# -----------------------------------------------------------------------------
# Purpose:             Internal progress display component for separate CLI window
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-10-31
# Last Updated:        2025-10-31
#
# Description:
#   Internal component that displays progress in a separate CLI window.
#   Launched automatically by utils/mosaic_processor.py when processing starts.
#   Users never run this directly - it's an internal part of the monitoring system.
#
# File Location:        /utils/mosaic_progress_display.py
# Called By:            utils/mosaic_processor.py (via subprocess)
# Int. Dependencies:    Reads JSON status files created by mosaic_processor_monitor.py
# Ext. Dependencies:    argparse, json, time, os, sys, pathlib
#
# =============================================================================

import argparse
import json
import time
import os
import sys
from pathlib import Path


def clear_screen():
    """Clear the console screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def load_status(status_file: Path):
    """Load status from JSON file."""
    try:
        with open(status_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def format_progress_bar(percent: float, width: int = 40) -> str:
    """Create a text progress bar."""
    filled = int(width * percent / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {percent:5.1f}%"


def display_status(status):
    """Display formatted status information."""
    if not status:
        return

    clear_screen()

    print("🎬 MOSAIC PROCESSOR - REAL-TIME PROGRESS")
    print("=" * 60)

    # Overall progress
    totals = status.get("totals", {})
    overall_percent = totals.get("progress_percent", 0)
    generated = totals.get("generated_frames", 0)
    expected = totals.get("expected_frames", 0)
    reels_complete = totals.get("reels_completed", 0)
    reels_total = totals.get("reels_total", 0)

    print(f"\n📈 OVERALL PROGRESS")
    print(f"   {format_progress_bar(overall_percent)}")
    print(f"   Frames: {generated:,} / {expected:,}")
    print(f"   Reels:  {reels_complete} / {reels_total} complete")

    # Per-reel breakdown
    reels = status.get("reels", {})
    if reels:
        print(f"\n🎞️  REEL PROGRESS")
        print(f"{'Reel':<15} {'Progress':<45} {'Frames':<15} {'Status'}")
        print("-" * 85)

        for reel_name in sorted(reels.keys()):
            reel_data = reels[reel_name]
            percent = reel_data.get("progress_percent", 0)
            gen_frames = reel_data.get("generated_frames", 0)
            exp_frames = reel_data.get("expected_frames", 0)
            completed = reel_data.get("completed", False)

            progress_bar = format_progress_bar(percent, width=35)
            status_icon = "✅" if completed else "🔄" if gen_frames > 0 else "⏳"

            print(f"{reel_name:<15} {progress_bar:<45} {gen_frames:>6}/{exp_frames:<6} {status_icon}")

    # Footer
    timestamp = status.get("timestamp_iso", "Unknown")
    monitoring = status.get("monitoring", False)

    print("\n" + "=" * 60)
    print(f"⏰ Last Update: {timestamp}")
    print(f"🔄 Status: {'Monitoring Active' if monitoring else 'Complete'}")

    if monitoring:
        print("💡 This window will close automatically when processing completes")
    else:
        print("🎉 Processing completed! Window will close in 5 seconds...")


def main():
    """Main entry point for automatic progress monitoring."""
    parser = argparse.ArgumentParser(
        description="Automatic Mosaic Processor Progress Monitor"
    )
    parser.add_argument("--status-file", required=True, help="Path to progress JSON file")
    parser.add_argument("--watch", action="store_true", help="Monitor continuously")

    args = parser.parse_args()
    status_file = Path(args.status_file)

    # Set window title
    if os.name == 'nt':
        os.system('title Mosaic Processor Progress')

    print("🔍 Starting Mosaic Processor Progress Monitor...")
    print(f"📂 Monitoring: {status_file}")
    print("⏳ Waiting for processing to begin...\n")

    if not args.watch:
        # Single status display
        status = load_status(status_file)
        if status:
            display_status(status)
        else:
            print(f"❌ Could not read status from {status_file}")
        return

    # Continuous monitoring
    try:
        start_time = time.time()
        max_wait_time = 300  # 5 minutes timeout
        check_interval = 2.0

        while True:
            status = load_status(status_file)

            if status:
                display_status(status)

                # Check if complete
                current_percent = status.get("totals", {}).get("progress_percent", 0)
                monitoring = status.get("monitoring", True)

                if not monitoring or current_percent >= 100.0:
                    # Wait a moment to show final status, then exit
                    time.sleep(5)
                    break

            else:
                # No status file yet
                elapsed = time.time() - start_time
                if elapsed > max_wait_time:
                    print(f"\n⏰ Timeout: No status after {max_wait_time//60} minutes")
                    print("   Closing monitor window...")
                    break

                # Show waiting message every 10 seconds
                if int(elapsed) % 10 == 0:
                    clear_screen()
                    print("🎬 MOSAIC PROCESSOR - REAL-TIME PROGRESS")
                    print("=" * 60)
                    print(f"\n⏳ Waiting for processing to start...")
                    print(f"   Elapsed: {elapsed:.0f}s / {max_wait_time}s")
                    print(f"\n📂 Looking for: {status_file}")
                    print("\n💡 This window will show progress automatically once")
                    print("   MistikaVR begins rendering frames.")

            time.sleep(check_interval)

    except KeyboardInterrupt:
        print("\n\n👋 Monitor stopped by user")
    except Exception as e:
        print(f"\n❌ Monitor error: {e}")


if __name__ == "__main__":
    main()
