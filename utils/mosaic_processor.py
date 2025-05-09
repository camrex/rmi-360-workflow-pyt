# =============================================================================
# 🖥️ Mosaic Processor Wrapper (utils/mosaic_processor.py)
# -----------------------------------------------------------------------------
# Purpose:             Executes Mosaic Processor CLI to render, fix reels, and integrate GPS metadata
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Invokes the Mosaic Processor executable in two passes: one for rendering and reel fixing, and one for GPX
#   integration. Constructs shell-safe command lines, manages output folders, detects reel numbers, logs output,
#   and writes reel metadata. Uses subprocess for shell execution and logs all results for diagnostics.
#
# File Location:        /utils/mosaic_processor.py
# Called By:            tools/run_mosaic_processor_tool.py, tools/process_360_orchestrator.py
# Int. Dependencies:    config_loader, arcpy_utils, pad_mosaic_frame_numbers, path_utils
# Ext. Dependencies:    subprocess, json, re, os, typing, pathlib
# External Tools:       Mosaic Processor CLI, MistikaVR (external dependency)
#
# Documentation:
#   See: docs/TOOL_GUIDES.md and docs/tools/run_mosaic_processor.md
#
# Notes:
#   - .cfg path is reserved for future functionality
#   - Fails fast on missing .grp or invalid input folder
# =============================================================================

__all__ = ["run_mosaic_processor"]

import os
import subprocess
import json
import re
from pathlib import Path
from typing import Optional

from utils.config_loader import resolve_config
from utils.pad_mosaic_frame_numbers import pad_frame_numbers
from utils.arcpy_utils import log_message
from utils.path_utils import get_log_path


def build_mosaic_command(
    exe_path, input_dir, output_dir, grp_path,
    start_frame=None, end_frame=None,
    skip_gpx=False, skip_render=False, skip_reel_fix=False,
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


def run_render_stage(exe_path, input_dir, output_dir, grp_path, start_frame, end_frame, exe_dir, log_f, messages, config, log_path):
    """Run the Render + Reel Fix stage."""
    render_cmd = build_mosaic_command(exe_path, input_dir, str(output_dir), grp_path, start_frame, end_frame,
                                      skip_gpx=True, wrap_in_shell=True)
    log_message(f"🛠️ Running command: {render_cmd}", messages, level="debug", config=config)
    log_f.write(f"COMMAND: {render_cmd}\n\n")

    result1 = subprocess.run(render_cmd, cwd=exe_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, shell=True)

    log_f.write("=== Render + Reel Fix ===\n")
    log_f.write(result1.stdout or "")
    log_f.write("\n\n")

    if result1.returncode != 0:
        log_message("❌ Render failed. See log for details.", messages, level="error", error_type=RuntimeError,
                    config=config)
        log_message(f"📄 Log written to: {log_path}", messages, config=config)
        return False  # Return False if failed

    return True  # Return True if successful


def run_gpx_integration_stage(exe_path, input_dir, output_dir, grp_path, start_frame, end_frame, exe_dir, log_f, messages, config, log_path):
    """Run the GPX Integration stage."""
    gpx_cmd = build_mosaic_command(exe_path, input_dir, str(output_dir), grp_path, start_frame, end_frame,
                                   skip_render=True, skip_reel_fix=True, wrap_in_shell=True)
    log_message(f"🛠️ Running command: {gpx_cmd}", messages, level="debug", config=config)
    log_f.write(f"COMMAND: {gpx_cmd}\n\n")

    result2 = subprocess.run(gpx_cmd, cwd=exe_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             shell=True)

    log_f.write("=== GPX Integration ===\n")
    log_f.write(result2.stdout or "")
    log_f.write("\n\n")

    if result2.returncode != 0:
        log_message("❌ GPX Integration failed. See log for details.", messages, level="error",
                    error_type=RuntimeError, config=config)
        log_message(f"📄 Log written to: {log_path}", messages, config=config)
        return False  # Return False if failed

    return True  # Return True if successful


def run_mosaic_processor(
    project_folder: str,
    input_dir: str,
    grp_path: Optional[str] = None,
    start_frame: Optional[int] = None,
    end_frame: Optional[int] = None,
    exe_path: Optional[str] = None,
    config: Optional[dict] = None,
    config_file: Optional[str] = None,
    messages=None
) -> None:
    """
    Runs the Mosaic Processor workflow for a project in two sequential stages.
    
    This function orchestrates the execution of the Mosaic Processor executable, first performing rendering and reel
    fixing, then running GPX integration. It handles configuration resolution, validates required paths, manages output
    directories, detects reel numbers, and logs all steps and subprocess outputs to a dedicated log file. If any
    critical step fails, the function logs an error and exits early.
    
    Args:
        project_folder: Path to the project folder containing configuration and output directories.
        input_dir: Directory containing input image frames.
        grp_path: Optional path to the .grp calibration file; overrides config if provided.
        start_frame: Optional starting frame number for processing.
        end_frame: Optional ending frame number for processing.
        exe_path: Optional path to the Mosaic Processor executable; overrides config if provided.
        config: Optional preloaded and validated configuration dictionary.
        config_file: Optional path to a configuration YAML file (used if config is not provided).
        messages: Optional ArcPy messaging object for logging.
    
    """
    config = resolve_config(
        config=config,
        config_file=config_file,
        project_folder=project_folder,
        messages=messages,
        tool_name="mosaic_processor")

    folders = config.get("image_output", {}).get("folders", {})
    output_dir = Path(project_folder) / folders.get("parent", "panos") / folders.get("original", "original")
    os.makedirs(output_dir, exist_ok=True)

    proc_cfg = config.get("executables", {}).get("mosaic_processor", {})
    exe_path = exe_path or proc_cfg.get("exe_path")
    if not exe_path:
        log_message("❌ Mosaic Processor executable path is missing in config.", messages, level="error",
                    error_type=ValueError, config=config)
    exe_dir = os.path.dirname(exe_path)

    grp_path = grp_path or proc_cfg.get("grp_path")
    if not grp_path:
        log_message("❌ .grp calibration file path is missing in config.", messages, level="error",
                    error_type=ValueError, config=config)

    cfg_path = proc_cfg.get("cfg_path")  # Currently unused, but included for FUTURE FUNCTIONALITY
    if cfg_path and cfg_path != "DISABLED":
        log_message(f"⚠️ Note: cfg_path is not yet implemented. Provided value: {cfg_path}", messages, level="warning",
                    config=config)

    if not os.path.isdir(input_dir):
        log_message(f"Input folder does not exist: {input_dir}", messages, level="error", error_type=FileNotFoundError,
                    config=config)

    # === DETECT REEL NUMBER (if processing a single reel) ===
    reel_match = re.search(r"reel_(\d{4})", os.path.basename(input_dir), re.IGNORECASE)
    if reel_match:
        reel_number = reel_match.group(1)
        reel_info_path = output_dir / "reel_info.json"
        try:
            with open(reel_info_path, "w") as f:
                json.dump({"reel": reel_number}, f)
            log_message(f"Saved reel number {reel_number} to {reel_info_path}", messages, config=config)
        except Exception as e:
            log_message(f"WARNING: Failed to write reel_info.json to {reel_info_path}: {e}", messages,
                        level="warning", config=config)

    # === Prepare log file ===
    log_path = get_log_path("mosaic_processor_log", config)

    try:
        with open(log_path, "w", encoding="utf-8") as log_f:
            # === Step 1: Render + Reel Fix ===
            log_message("Running Mosaic Processor: Render + Reel Fix...", messages, config=config)
            if not run_render_stage(exe_path, input_dir, output_dir, grp_path, start_frame, end_frame, exe_dir, log_f,
                                    messages, config, log_path):
                return  # Exit if render stage fails

            # === Step 2: Pad frame numbers ===
            log_message("Checking and renaming frame numbers if needed...", messages, config=config)
            pad_frame_numbers(str(output_dir), messages)

            # === Step 3: GPX Integration ===
            log_message("Running Mosaic Processor: GPX Integration...", messages, config=config)
            if not run_gpx_integration_stage(exe_path, input_dir, output_dir, grp_path, start_frame, end_frame, exe_dir,
                                             log_f, messages, config, log_path):
                return  # Exit if GPX integration fails

    except Exception as e:
        log_message(f"❌ Error during Mosaic Processor workflow: {e}", messages, level="error", error_type=RuntimeError,
                    config=config)

    log_message("✅ Mosaic Processor workflow complete.", messages, config=config)
    log_message(f"📄 Mosaic Processor log saved to: {log_path}", messages, config=config)
