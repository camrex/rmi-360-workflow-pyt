#!/usr/bin/env python3
# =============================================================================
# 🎬 Standalone Mosaic Monitor Script (scripts/standalone_mosaic_monitor.py)
# -----------------------------------------------------------------------------
# Purpose:             Launch a standalone mosaic processor progress monitor
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-11-01
# Last Updated:        2025-11-01
#
# Description:
#   Standalone script to launch a mosaic processor monitor when the automatic
#   monitor has closed or you need to reconnect to an ongoing process.
#   Automatically finds the most recent status file or allows manual specification.
#
# Usage:
#   python scripts/standalone_mosaic_monitor.py [--project PROJECT_NAME] [--status-file PATH]
#
# Examples:
#   python scripts/standalone_mosaic_monitor.py --project RMI25320
#   python scripts/standalone_mosaic_monitor.py --status-file "D:/Process360_Data/projects/RMI25320/logs/mosaic_progress.json"
#   python scripts/standalone_mosaic_monitor.py  # Auto-detect most recent
#
# =============================================================================

import argparse
import sys
import subprocess
import os
from pathlib import Path
import json
from datetime import datetime
import glob


def find_status_files(base_path=None):
    """
    Find all mosaic progress status files.

    Args:
        base_path: Base directory to search in (defaults to D:/Process360_Data/projects)

    Returns:
        List of status file paths with metadata
    """
    if base_path is None:
        base_path = Path("D:/Process360_Data/projects")

    status_files = []

    # Search pattern for mosaic progress JSON files
    pattern = "**/logs/mosaic_*progress*.json"

    try:
        for status_file in Path(base_path).glob(pattern):
            if status_file.is_file():
                try:
                    # Get file modification time
                    mtime = status_file.stat().st_mtime
                    mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

                    # Try to read basic info from the file
                    try:
                        with open(status_file, 'r') as f:
                            data = json.load(f)
                            project_info = data.get("project_name", "Unknown")
                            monitoring = data.get("monitoring", False)
                            progress = data.get("totals", {}).get("progress_percent", 0)
                    except (json.JSONDecodeError, KeyError):
                        project_info = "Unknown"
                        monitoring = False
                        progress = 0

                    status_files.append({
                        "path": status_file,
                        "modified": mtime,
                        "modified_str": mtime_str,
                        "project": project_info,
                        "monitoring": monitoring,
                        "progress": progress
                    })
                except OSError:
                    continue
    except Exception as e:
        print(f"⚠️ Error searching for status files: {e}")

    # Sort by modification time (newest first)
    status_files.sort(key=lambda x: x["modified"], reverse=True)
    return status_files


def launch_monitor(status_file_path):
    """
    Launch the standalone mosaic monitor.

    Args:
        status_file_path: Path to the status JSON file to monitor
    """
    # Find the monitor script
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    monitor_script = repo_root / "utils" / "mosaic_progress_display.py"

    if not monitor_script.exists():
        print(f"❌ Monitor script not found: {monitor_script}")
        return False

    if not Path(status_file_path).exists():
        print(f"❌ Status file not found: {status_file_path}")
        return False

    print(f"🎬 Launching mosaic monitor...")
    print(f"📁 Status file: {status_file_path}")
    print(f"🔧 Monitor script: {monitor_script}")

    try:
        # Build command for Windows
        if os.name == 'nt':
            cmd = [
                "cmd", "/c", "start",
                f"Mosaic Monitor - {Path(status_file_path).parent.parent.name}",  # Window title with project name
                sys.executable, str(monitor_script),
                "--status-file", str(status_file_path),
                "--watch"
            ]

            # Launch in new console window
            creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            subprocess.Popen(
                cmd,
                creationflags=creation_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            print("✅ Monitor launched successfully in new window!")
            return True

        else:
            # For non-Windows systems, launch directly
            cmd = [
                sys.executable, str(monitor_script),
                "--status-file", str(status_file_path),
                "--watch"
            ]
            subprocess.Popen(cmd)
            print("✅ Monitor launched successfully!")
            return True

    except Exception as e:
        print(f"❌ Failed to launch monitor: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Launch standalone mosaic processor progress monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/standalone_mosaic_monitor.py --project RMI25320
  python scripts/standalone_mosaic_monitor.py --status-file "D:/Process360_Data/projects/RMI25320/logs/mosaic_progress.json"
  python scripts/standalone_mosaic_monitor.py  # Auto-detect most recent
        """
    )

    parser.add_argument("--project", "-p",
                       help="Project name to find status file for")
    parser.add_argument("--status-file", "-f",
                       help="Direct path to mosaic progress JSON file")
    parser.add_argument("--list", "-l", action="store_true",
                       help="List available status files and exit")

    args = parser.parse_args()

    print("🎬 Standalone Mosaic Monitor Launcher")
    print("=" * 50)

    # Find available status files
    print("📋 Searching for mosaic progress files...")
    status_files = find_status_files()

    if not status_files:
        print("❌ No mosaic progress files found in D:/Process360_Data/projects/*/logs/")
        print("💡 Make sure a mosaic process is running or has been started recently.")
        return 1

    # If --list flag, show available files and exit
    if args.list:
        print(f"\n📋 Found {len(status_files)} status file(s):")
        print()
        for i, sf in enumerate(status_files, 1):
            status = "🟢 Active" if sf["monitoring"] else "🔴 Complete"
            print(f"{i:2d}. {sf['project']} - {sf['progress']:.1f}% - {status}")
            print(f"     📁 {sf['path']}")
            print(f"     🕐 Modified: {sf['modified_str']}")
            print()
        return 0

    # Determine which status file to use
    target_file = None

    if args.status_file:
        # Use specified file
        target_file = Path(args.status_file)
        if not target_file.exists():
            print(f"❌ Status file not found: {target_file}")
            return 1

    elif args.project:
        # Find file for specific project
        project_files = [sf for sf in status_files if args.project.lower() in sf["project"].lower()]
        if not project_files:
            print(f"❌ No status files found for project: {args.project}")
            print("💡 Available projects:")
            for sf in status_files[:5]:  # Show first 5
                print(f"    - {sf['project']}")
            return 1
        target_file = project_files[0]["path"]  # Most recent for this project

    else:
        # Auto-select most recent
        if len(status_files) == 1:
            target_file = status_files[0]["path"]
            print(f"📁 Auto-selected: {status_files[0]['project']} ({status_files[0]['modified_str']})")
        else:
            print(f"\n📋 Found {len(status_files)} status files. Please specify which one:")
            print()
            for i, sf in enumerate(status_files[:10], 1):  # Show top 10
                status = "🟢 Active" if sf["monitoring"] else "🔴 Complete"
                print(f"{i:2d}. {sf['project']} - {sf['progress']:.1f}% - {status}")
                print(f"     🕐 {sf['modified_str']}")
            print()
            print("💡 Use --project PROJECT_NAME or --status-file PATH to specify")
            print("💡 Use --list to see full paths")
            return 1

    # Launch the monitor
    print(f"🚀 Launching monitor for: {target_file.parent.parent.name}")
    success = launch_monitor(target_file)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
