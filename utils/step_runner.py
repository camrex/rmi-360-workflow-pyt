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
    cfg: ConfigManager,
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
        cfg (ConfigManager): Active configuration object with access to logging and paths.
        wait_config: Optional dictionary controlling waiting and OID backup behavior.

    Returns:
        A list of dictionaries, each summarizing the outcome of a step, including status, timing, and notes.
    """
    import traceback
    logger = cfg.get_logger()
    results: List[Dict[str, Any]] = []

    def ensure_report_steps(report: Dict[str, Any]) -> None:
        if "steps" not in report or not isinstance(report["steps"], list):
            report["steps"] = []

    def append_step_result(report: Dict[str, Any], step_result: Dict[str, Any]) -> None:
        ensure_report_steps(report)
        report["steps"].append(step_result)

    def should_skip_step(step: Dict[str, Any], param_values: Dict[str, Any]) -> Optional[str]:
        skip_fn = step.get("skip")
        if skip_fn:
            try:
                return skip_fn(param_values)
            except Exception as e:
                logger.warning(f"Skip-check for '{step.get('label', '')}' failed: {e}")
                return None
        return None

    def perform_oid_backup(step_key: str, param_values: Dict[str, Any], cfg: ConfigManager, wait_config: Optional[dict]) -> bool:
        if wait_config and wait_config.get("backup_oid_between_steps", False):
            backup_steps = wait_config.get("backup_before_step", [])
            if step_key in backup_steps:
                if "oid_fc" not in param_values:
                    logger.warning("`oid_fc` not supplied skipping OID backup")
                else:
                    try:
                        backup_oid(param_values["oid_fc"], step_key, cfg)
                        return True
                    except Exception as e:
                        logger.warning(f"Failed to back up OID before step '{step_key}': {e}")
        return False

    def perform_wait(step_key: str, label: str, wait_config: Optional[dict]):
        if wait_config and wait_config.get("wait_between_steps", False):
            wait_steps = wait_config.get("wait_before_step", [])
            wait_seconds = wait_config.get("wait_duration_sec", 60)
            if step_key in wait_steps:
                logger.info(f"⏳ Waiting {wait_seconds} seconds before running step: {label}")
                time.sleep(wait_seconds)

    def execute_step(label: str, func, report_data: Dict[str, Any]):
        step_start = datetime.now(timezone.utc)
        try:
            with logger.step(label):
                func(report_data=report_data)
            status = "✅"
            notes = "Success"
        except Exception as e:
            status = "❌"
            tb = traceback.format_exc()
            notes = f"{e}\n{tb}"
        step_end = datetime.now(timezone.utc)
        elapsed = f"{(step_end - step_start).total_seconds():.1f} sec"
        return status, notes, step_start, step_end, elapsed

    for step_key in step_order[start_index:]:
        if step_key not in step_funcs:
            logger.error(f"Step '{step_key}' not found in step_funcs dictionary", error_type=KeyError)
            break
        step = step_funcs[step_key]
        label = step.get("label", step_key)
        func = step["func"]
        skip_reason = should_skip_step(step, param_values)

        if skip_reason:
            logger.info(f"⏭️ {label} — {skip_reason}")
            step_result = {
                "name": label,
                "status": "⏭️",
                "time": "—",
                "notes": skip_reason
            }
            append_step_result(report_data, step_result)
            save_report_json(report_data, cfg)
            results.append(step_result)
            continue

        backup_occurred = perform_oid_backup(step_key, param_values, cfg, wait_config)
        perform_wait(step_key, label, wait_config)
        status, notes, step_start, step_end, elapsed = execute_step(label, func, report_data)

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
        append_step_result(report_data, step_result)
        save_report_json(report_data, cfg)
        results.append(step_result)
        if status == "❌":
            break
    return results
