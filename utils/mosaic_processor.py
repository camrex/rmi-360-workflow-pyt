# =============================================================================
# 🖥️ Mosaic Processor Wrapper (utils/mosaic_processor.py)
# -----------------------------------------------------------------------------
# Purpose:             Executes Mosaic Processor CLI to render, fix reels, and integrate GPS metadata
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-13
# Last Updated:        2025-05-20
#
# Description:
#   Runs the Mosaic Processor in three sequential stages:
#   1. Render + Reel Fix
#   2. Frame number zero-padding
#   3. GPX metadata integration
#   Logs progress, validates config, and writes a single reel_info.json (optional).
#
# File Location:        /utils/mosaic_processor.py
# Validator:            /utils/validators/mosaic_processor_validator.py
# Called By:            tools/run_mosaic_processor_tool.py, tools/process_360_orchestrator.py
# Int. Dependencies:    utils/manager/config_manager
# Ext. Dependencies:    subprocess, json, re, os, typing, pathlib
# External Tools:       Mosaic Processor CLI, MistikaVR (external dependency)
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/run_mosaic_processor.md
#   (Ensure these docs are current; update if needed.)
#
# Notes:
#   - Uses cfg.validate(tool="mosaic_processor") for schema enforcement
#   - .cfg file support is reserved for future implementation
#   - Output is auto-padded to 6-digit frame numbers post-render
#
# =============================================================================
import os
import sys
import subprocess
import json
import re
import time
import platform
from pathlib import Path
from typing import Optional

from utils.manager.config_manager import ConfigManager
from utils.mosaic_processor_monitor import create_monitor_from_config

__all__ = ["run_mosaic_processor"]


def launch_progress_monitor_window(status_file_path, logger):
    """
    Launch a separate CLI window showing progress monitoring.

    Args:
        status_file_path: Path to the progress JSON status file
        logger: Logger instance

    Returns:
        Subprocess Popen object or None if failed
    """
    try:
        # Get the path to the monitoring display script
        utils_dir = Path(__file__).parent
        monitor_script = utils_dir / "mosaic_progress_display.py"

        if not monitor_script.exists():
            logger.warning(f"Monitor script not found: {monitor_script}", indent=4)
            return None

        # Get Python executable (try to use same environment as current process)
        python_exe = "python"  # Default fallback
        try:
            python_exe = sys.executable
        except AttributeError:
            logger.debug("sys.executable unavailable, using 'python'", indent=4)

        # Build command to run monitoring script in new window (Windows only)
        if platform.system() != "Windows":
            logger.info("Progress monitor window is only supported on Windows.", indent=4)
            return None

        cmd = [
            "cmd", "/c", "start",
            "Mosaic Processor Progress",  # Window title
            python_exe, str(monitor_script),
            "--status-file", str(status_file_path),
            "--watch"
        ]

        # Launch the process
        creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        process = subprocess.Popen(
            cmd,
            creationflags=creation_flags,  # Create new window on Windows; 0 on other platforms
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        return process

    except (FileNotFoundError, OSError, subprocess.SubprocessError) as e:
        logger.warning(f"Failed to launch progress monitor window: {e}", indent=4)
        return None


def build_mosaic_command(
    exe_path,
    input_dir,
    output_dir,
    grp_path,
    start_frame=None,
    end_frame=None,
    skip_gpx=False,
    skip_render=False,
    skip_reel_fix=False,
    wrap_in_shell: bool = True
):
    """
    Constructs a command to run the Mosaic Processor executable with specified options.

    Args:
        exe_path: Path to the Mosaic Processor executable.
        input_dir: Directory containing input image frames.
        output_dir: Directory where output will be saved.
        grp_path: Path to the calibration .grp file.
        start_frame: Optional starting frame number to process.
        end_frame: Optional ending frame number to process.
        skip_gpx: If True, disables GPX integration.
        skip_render: If True, disables rendering.
        skip_reel_fix: If True, disables reel fixing.
        wrap_in_shell: If True, returns the command as a shell-wrapped string suitable for Windows; otherwise returns a
        list of command arguments.

    Returns:
        A shell-wrapped command string or a list of command arguments for subprocess execution, depending on
        wrap_in_shell.
    """
    cmd = [
        exe_path,
        input_dir,
        "--output_dir", output_dir,
        "--grp_path", grp_path
    ]

    if start_frame is not None:
        cmd += ["--start_frame", str(start_frame)]
    if end_frame is not None:
        cmd += ["--end_frame", str(end_frame)]
    if skip_gpx:
        cmd.append("--no_gpx_integration")
    if skip_render:
        cmd.append("--no_render")
    if skip_reel_fix:
        cmd.append("--no_reel_fixing")

    cmd = [str(c) for c in cmd if c is not None]

    if wrap_in_shell:
        quoted_cmd = [f'"{cmd[0]}"'] + [f'"{c}"' if " " in c else c for c in cmd[1:]]
        return f'cmd /c "{" ".join(quoted_cmd)}"'
    else:
        return cmd


def run_processor_stage(
    cfg: ConfigManager,
    input_dir: str,
    output_dir: Path,
    start_frame,
    end_frame,
    log_f,
    log_path,
    stage_name: str,
    skip_render=False,
    skip_reel_fix=False,
    skip_gpx=False,
) -> bool:
    """
    Runs a single Mosaic Processor CLI stage (Render or GPX Integration).

    Args:
        cfg: ConfigManager instance.
        input_dir: Input directory containing raw frames.
        output_dir: Target output directory.
        start_frame: Start frame (optional).
        end_frame: End frame (optional).
        log_f: File handle for writing logs.
        log_path: Path to log file.
        stage_name: Label for the stage ("Render + Reel Fix" or "GPX Integration").
        skip_render: If True, disables rendering.
        skip_reel_fix: If True, disables reel fixing.
        skip_gpx: If True, disables GPX integration.

    Returns:
        True if stage succeeded, False otherwise.
    """
    logger = cfg.get_logger()
    exe_path = cfg.paths.mosaic_processor_exe
    grp_path = cfg.paths.mosaic_processor_grp
    cfg_path = cfg.paths.mosaic_processor_cfg
    exe_dir = os.path.dirname(exe_path)

    if cfg_path != "DISABLED":
        logger.warning(f"Note: cfg_path is not yet implemented. Provided value: {cfg_path}", indent=1)

    cmd = build_mosaic_command(
        exe_path=exe_path,
        input_dir=input_dir,
        output_dir=str(output_dir),
        grp_path=grp_path,
        start_frame=start_frame,
        end_frame=end_frame,
        skip_gpx=skip_gpx,
        skip_render=skip_render,
        skip_reel_fix=skip_reel_fix,
        wrap_in_shell=True,
    )

    logger.custom(f"Running command: {cmd}", indent=2, emoji="🧑🏻‍💻")
    log_f.write(f"COMMAND: {cmd}\n\n")

    # Run subprocess normally (progress monitoring happens in separate window)
    result = subprocess.run(cmd, cwd=exe_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=True)

    log_f.write(f"=== {stage_name} ===\n")
    log_f.write(result.stdout or "")
    log_f.write("\n\n")

    if result.returncode != 0:
        logger.error(f"{stage_name} failed. See log for details.", error_type=RuntimeError, indent=0)
        logger.info(f"📄 Log written to: {log_path}", indent=1)
        return False

    logger.success(f"=== {stage_name} Complete ===", indent=1)

    return True


def pad_frame_numbers(output_dir: str, logger) -> int:
    """
    Renames JPG files in the output folder to use zero-padded 6-digit frame numbers.

    Args:
        output_dir: Directory containing frame image files.
        logger: ConfigManager logger instance.

    Returns:
        Number of files renamed.
    """
    renamed_count = 0
    logger.info(f"Checking for frame number padding in: {output_dir}", indent=2)

    # Check for any unpadded JPG file (less than 6 digits in the number)
    unpadded_found = False
    for root, _dirs, files in os.walk(output_dir):
        for f in files:
            if f.lower().endswith(".jpg"):
                match = re.match(r"^.*_(\d{1,5})\.jpg$", f)
                if match:
                    unpadded_found = True
                    break
        if unpadded_found:
            break

    if unpadded_found:
        logger.info("Frame numbers are not padded, padding...", indent=3)
    else:
        logger.info("Frame numbers are padded. Skipping padding.", indent=3)
        logger.success("=== Pad frame numbers Complete ===", indent=1)
        return 0

    # Proceed with renaming
    for root, _dirs, files in os.walk(output_dir):
        for f in files:
            if f.lower().endswith(".jpg"):
                match = re.match(r"^(.*_)(\d{1,5})\.jpg$", f)
                if match:
                    prefix, num = match.groups()
                    new_name = f"{prefix}{num.zfill(6)}.jpg"
                    old_path = os.path.join(root, f)
                    new_path = os.path.join(root, new_name)
                    os.rename(old_path, new_path)
                    renamed_count += 1
                    logger.debug(f"Renamed: {f} → {new_name}", indent=4)

    logger.info(f"Total files padded: {renamed_count}", indent=3)
    logger.success("=== Pad frame numbers Complete ===", indent=1)
    return renamed_count


def run_mosaic_processor(
    cfg: ConfigManager,
    input_dir: str,
    start_frame: Optional[int] = None,
    end_frame: Optional[int] = None,
) -> None:
    """
    Runs the Mosaic Processor workflow for a project in three sequential stages.

    This function orchestrates the execution of the Mosaic Processor executable, first performing rendering and reel
    fixing, then running GPX integration. It handles configuration resolution, validates required paths, manages output
    directories, detects reel numbers, and logs all steps and subprocess outputs to a dedicated log file. If any
    critical step fails, the function logs an error and exits early.

    Args:
        cfg (ConfigManager): Active configuration manager with logging and paths.
        input_dir: Directory containing input image frames.
        start_frame: Optional starting frame number for processing.
        end_frame: Optional ending frame number for processing.
    """
    logger = cfg.get_logger()
    cfg.validate(tool="mosaic_processor")

    output_dir = cfg.paths.original
    output_dir.mkdir(parents=True, exist_ok=True)

    if not os.path.isdir(input_dir):
        logger.error(f"Input folder does not exist: {input_dir}", error_type=FileNotFoundError, indent=1)

    # Optional: write reel_info.json if a reel folder name can be inferred
    reel_match = re.search(r"reel_(\d{4})", os.path.basename(input_dir), re.IGNORECASE)
    if reel_match:
        reel_number = reel_match.group(1)
        reel_info_path = output_dir / "reel_info.json"
        try:
            with open(reel_info_path, "w") as f:
                json.dump({"reel": reel_number}, f)
            logger.info(f"Saved reel number {reel_number} to {reel_info_path}", indent=1)
        except Exception as e:
            logger.warning(f"Failed to write reel_info.json to {reel_info_path}: {e}", indent=1)

    log_path = cfg.paths.get_log_file_path("mosaic_processor_log", cfg)

    # Initialize progress monitor without callback (will use separate CLI window)
    progress_monitor = create_monitor_from_config(cfg, input_dir)
    monitor_started = False
    monitor_process = None

    try:
        with open(log_path, "w", encoding="utf-8") as log_f, \
                cfg.get_progressor(total=3, label="Mosaic Processor Workflow") as progressor:

            # === Step 1: Render + Reel Fix ===
            logger.info("=== Render + Reel Fix Started ===", indent=1)
            reel_folders = [d for d in os.listdir(input_dir) if (Path(input_dir) / d).is_dir()]
            number_of_reels = len(reel_folders)
            logger.info(f"Found {number_of_reels} reel(s) in {input_dir}", indent=2)

            for folder in reel_folders:
                logger.info(f"🎞️ {folder}", indent=3)

            # Start progress monitoring before rendering begins
            logger.info("📊 Starting progress monitoring...", indent=2)
            monitor_started = progress_monitor.start_monitoring()
            time.sleep(0.1)  # Give monitor a moment to initialize
            if monitor_started:
                if not progress_monitor.is_monitoring():
                    logger.warning("Progress monitoring disabled (no frame_times.csv found); skipping monitor window", indent=3)
                else:
                    status_file_path = cfg.paths.logs / "mosaic_processor_progress.json"
                    logger.info(f"📈 Progress status: {status_file_path}", indent=3)

                    # Display initial expected frame counts
                    initial_status = progress_monitor.get_current_status()
                    if initial_status and initial_status.get('totals', {}).get('expected_frames', 0) > 0:
                        total_expected = initial_status['totals']['expected_frames']
                        reel_count = initial_status['totals']['reels_total']
                        logger.info(f"📊 Expecting {total_expected:,} frames across {reel_count} reel(s)", indent=3)

                    # Launch separate CLI monitoring window
                    monitor_process = launch_progress_monitor_window(status_file_path, logger)
                    if monitor_process:
                        logger.info("🖥️ Progress monitor window opened", indent=3)
                    else:
                        logger.warning("Failed to open progress monitor window", indent=3)
            else:
                logger.warning("Failed to start progress monitoring", indent=3)
            if not run_processor_stage(
                    cfg, input_dir, output_dir, start_frame, end_frame,
                    log_f, log_path,
                    stage_name="Render + Reel Fix",
                    skip_gpx=True
            ):
                return
            progressor.update(1)

            # === Step 2: Pad frame numbers ===
            logger.info("=== Pad frame numbers Started ===", indent=1)
            pad_frame_numbers(str(output_dir), logger)
            progressor.update(2)

            # === Step 3: GPX Integration ===
            logger.info("=== GPX Integration Started ===", indent=1)
            if not run_processor_stage(
                    cfg, input_dir, output_dir, start_frame, end_frame,
                    log_f, log_path,
                    stage_name="GPX Integration",
                    skip_render=True,
                    skip_reel_fix=True
            ):
                return
            progressor.update(3)

    except Exception as e:
        logger.error(f"Error during Mosaic Processor workflow: {e}", error_type=RuntimeError, indent=1)
    finally:
        # Stop progress monitoring
        if monitor_started and progress_monitor.is_monitoring():
            logger.info("📊 Stopping progress monitoring...", indent=1)
            progress_monitor.stop_monitoring(timeout=15.0)

            # Log final status with visual summary
            final_status = progress_monitor.get_current_status()
            if final_status:
                totals = final_status.get("totals", {})
                final_percent = totals.get('progress_percent', 0)
                generated = totals.get('generated_frames', 0)
                expected = totals.get('expected_frames', 0)
                completed_reels = totals.get('reels_completed', 0)
                total_reels = totals.get('reels_total', 0)

                if final_percent >= 100.0:
                    logger.success("🎉 All frames rendered successfully!", indent=2)
                    logger.info(f"   📊 Total: {generated:,} frames across {total_reels} reels", indent=2)
                else:
                    logger.info(
                        f"📈 Final Status: {generated:,}/{expected:,} frames "
                        f"({final_percent:.1f}%), {completed_reels}/{total_reels} reels complete",
                        indent=2
                    )

        # Close progress monitor window
        if monitor_process:
            try:
                # Give the monitor window a moment to show final status
                time.sleep(3)
                monitor_process.terminate()
                logger.info("🖥️ Progress monitor window closed", indent=2)
            except (ProcessLookupError, OSError) as e:
                logger.debug(f"Error closing monitor window: {e}", indent=3)

    logger.custom(f"Mosaic Processor log saved to: {log_path}", indent=1, emoji="📄")
