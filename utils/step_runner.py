# =============================================================================
# 🔁 Step Runner Orchestration Logic (utils/step_runner.py)
# -----------------------------------------------------------------------------
# Purpose:             Executes a sequence of configured workflow steps with progress logging
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Iterates through workflow step functions, checking for skip conditions, handling wait intervals,
#   and optionally backing up the OID feature class between steps. Tracks progress, captures run timing,
#   appends results to a shared report object, and saves state to JSON after each step. Designed for use
#   by the orchestrator tool and developer automation.
#
# File Location:        /utils/step_runner.py
# Called By:            tools/process_360_orchestrator.py
# Int. Dependencies:    arcpy_utils, report_data_builder
# Ext. Dependencies:    time, datetime, typing
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/process_360_orchestrator.md
#
# Notes:
#   - Logs each step with emoji-coded status (✅, ❌, ⏭️)
#   - Stops execution on first failure by default (can be customized)
# =============================================================================

import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from utils.arcpy_utils import backup_oid
from utils.report_data_builder import save_report_json
from utils.manager.config_manager import ConfigManager


def run_steps(
    step_funcs: Dict[str, Dict[str, Any]],
    step_order: List[str],
    start_index: int,
    param_values: Dict[str, Any],
    report_data: Dict[str, Any],
    project_folder: str,
    cfg: ConfigManager,
    messages,
    wait_config: Optional[dict] = None
) -> List[Dict[str, Any]]:
    """
    Executes a sequence of pipeline steps with logging, optional waiting, and OID backups.
    
    Iterates through the specified steps in order, starting from the given index. For each step, checks if it should be
    skipped, optionally performs an OID backup and/or waits before execution, and logs the step's status and timing.
    Updates the report data after each step and saves it to JSON. Stops execution if a step fails.
    
    Args:
        step_funcs: Mapping of step keys to dictionaries containing step metadata, including the function to execute
        and optional skip logic.
        step_order: Ordered list of step keys defining execution sequence.
        start_index: Index in step_order to begin execution.
        param_values: Dictionary of parameters, including ArcPy parameters.
        report_data: Dictionary representing the report, updated incrementally with step results.
        project_folder: Path to the root project folder.
        cfg: Configuration dictionary.
        messages: ArcGIS messages interface for logging.
        wait_config: Optional dictionary controlling waiting and OID backup behavior.
    
    Returns:
        A list of dictionaries, each summarizing the outcome of a step, including status, timing, and notes.
    """
    logger = cfg.get_logger()
    results = []

    for step_key in step_order[start_index:]:
        if step_key not in step_funcs:
            logger.error(f"Step '{step_key}' not found in step_funcs dictionary", error_type=KeyError)
            break
        step = step_funcs[step_key]
        label = step.get("label", step_key)
        func = step["func"]
        skip_fn = step.get("skip")
        try:
            skip_reason = skip_fn(param_values) if skip_fn else None
        except Exception as e:
            logger.warning(f"Skip-check for '{label}' failed: {e}")
            skip_reason = None

        if skip_reason:
            logger.info(f"⏭️ {label} — {skip_reason}")
            step_result = {
                "name": label,
                "status": "⏭️",
                "time": "—",
                "notes": skip_reason
            }
            results.append(step_result)
            report_data["steps"].append(step_result)
            save_report_json(report_data, project_folder, cfg, messages)
            continue

        # Optional OID backup before this step
        backup_occurred = False
        if wait_config and wait_config.get("backup_oid_between_steps", False):
            backup_steps = wait_config.get("backup_before_step", [])
            if step_key in backup_steps:
                if "oid_fc" not in param_values:
                    logger.warning("`oid_fc` not supplied skipping OID backup")
                else:
                    try:
                        backup_oid(param_values["oid_fc"], step_key, cfg)
                        backup_occurred = True
                    except Exception as e:
                        logger.warning(f"Failed to back up OID before step '{step_key}': {e}")

        # ⏳ Optional wait before next step
        if wait_config and wait_config.get("wait_between_steps", False):
            wait_steps = wait_config.get("wait_before_step", [])
            wait_seconds = wait_config.get("wait_duration_sec", 60)
            if step_key in wait_steps:
                logger.info(f"⏳ Waiting {wait_seconds} seconds before running step: {label}")
                time.sleep(wait_seconds)

        logger.info(f"▶️ {label}")  # TODO logger.step needs to be implemented
        step_start = datetime.now(timezone.utc)

        try:
            func()
            status = "✅"
            notes = "Success"
        except Exception as e:
            status = "❌"
            notes = f"{e}"
            logger.error(f"{label} failed: {e}")

        step_end = datetime.now(timezone.utc)
        elapsed = f"{(step_end - step_start).total_seconds():.1f} sec"

        step_result = {
            "name": label,
            "status": status,
            "step_started": step_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "step_ended": step_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time": elapsed,
            "notes": notes + (" (OID backup created before step)" if backup_occurred else "")
        }

        if backup_occurred:
            step_result["backup_created"] = "true"

        results.append(step_result)
        report_data["steps"].append(step_result)

        # ✅ Save current state to JSON after each step
        save_report_json(report_data, project_folder, cfg, messages)

        # If the step failed, stop execution (optional; remove if continuing is preferred)
        if status == "❌":
            break

    return results
