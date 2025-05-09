import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from utils.arcpy_utils import log_message, backup_oid
from utils.report_data_builder import save_report_json


def run_steps(
    step_funcs: Dict[str, Dict[str, Any]],
    step_order: List[str],
    start_index: int,
    param_values: Dict[str, Any],
    report_data: Dict[str, Any],
    project_folder: str,
    config: dict,
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
        config: Configuration dictionary.
        messages: ArcGIS messages interface for logging.
        wait_config: Optional dictionary controlling waiting and OID backup behavior.
    
    Returns:
        A list of dictionaries, each summarizing the outcome of a step, including status, timing, and notes.
    """
    results = []

    for step_key in step_order[start_index:]:
        if step_key not in step_funcs:
            log_message(f"❌ Step '{step_key}' not found in step_funcs dictionary", messages, level="error",
                        error_type=KeyError, config=config)
            break
        step = step_funcs[step_key]
        label = step.get("label", step_key)
        func = step["func"]
        skip_fn = step.get("skip")
        try:
            skip_reason = skip_fn(param_values) if skip_fn else None
        except Exception as e:
            log_message(f"[WARNING] Skip-check for '{label}' failed: {e}", messages, level="warning", config=config)
            skip_reason = None

        if skip_reason:
            log_message(f"⏭️ {label} — {skip_reason}", messages, config=config)
            step_result = {
                "name": label,
                "status": "⏭️",
                "time": "—",
                "notes": skip_reason
            }
            results.append(step_result)
            report_data["steps"].append(step_result)
            save_report_json(report_data, project_folder, config, messages)
            continue

        # Optional OID backup before this step
        backup_occurred = False
        if wait_config and wait_config.get("backup_oid_between_steps", False):
            backup_steps = wait_config.get("backup_before_step", [])
            if step_key in backup_steps:
                if "oid_fc" not in param_values:
                    log_message("[WARNING] `oid_fc` not supplied skipping OID backup", messages, level="warning",
                                config=config)
                else:
                    try:
                        backup_oid(param_values["oid_fc"], step_key, config, messages)
                        backup_occurred = True
                    except Exception as e:
                        log_message(f"[WARNING] Failed to back up OID before step '{step_key}': {e}",
                                    messages, level="warning", config=config)

        # ⏳ Optional wait before next step
        if wait_config and wait_config.get("wait_between_steps", False):
            wait_steps = wait_config.get("wait_before_step", [])
            wait_seconds = wait_config.get("wait_duration_sec", 60)
            if step_key in wait_steps:
                log_message(f"⏳ Waiting {wait_seconds} seconds before running step: {label}", messages, config=config)
                time.sleep(wait_seconds)

        log_message(f"▶️ {label}", messages, config=config)
        step_start = datetime.now(timezone.utc)

        try:
            func()
            status = "✅"
            notes = "Success"
        except Exception as e:
            status = "❌"
            notes = f"{e}"
            log_message(f"[ERROR] {label} failed: {e}", messages, level="error", config=config)

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
        save_report_json(report_data, project_folder, config, messages)

        # If the step failed, stop execution (optional; remove if continuing is preferred)
        if status == "❌":
            break

    return results
