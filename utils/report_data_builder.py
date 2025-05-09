import os
import json
from pathlib import Path
from typing import Dict, Optional
from utils.expression_utils import resolve_expression
from utils.arcpy_utils import log_message


def resolve_if_expression(val, config):
    """
    Resolves a value as a configuration expression if it starts with 'config.'.
    
    If the input is a string beginning with 'config.', evaluates it as an expression
    against the provided config dictionary. Otherwise, returns the value unchanged.
    """
    return resolve_expression(val, config=config) if isinstance(val, str) and val.startswith("config.") else val


def get_image_path(project_folder, config, subfolder_key):
    """Helper function to build image paths with config resolution and fallbacks."""
    folders = config.get("image_output", {}).get("folders", {})
    parent_expr = folders.get("parent", "panos")
    subfolder_expr = folders.get(subfolder_key, subfolder_key)

    parent = resolve_if_expression(parent_expr, config=config)
    subfolder = resolve_if_expression(subfolder_expr, config=config)

    return os.path.join(project_folder, parent, subfolder)


def initialize_report_data(p, config) -> Dict:
    """
    Initializes and returns a dictionary containing structured report data for a project.
    
    The returned dictionary includes project metadata, empty collections for steps and metrics, resolved file paths
    for images and reels, AWS S3 bucket information, camera configuration with dynamic value resolution, an export
    folder path, and an upload status tracker. Configuration values that are expressions prefixed with "config." are
    resolved against the provided config dictionary.
    
    Args:
        p: Dictionary containing project folder paths and input locations.
        config: Dictionary with project configuration and metadata.
    
    Returns:
        A dictionary representing the initialized report data structure.
    """
    report_data = {
        "project": config.get("project", {}),
        "steps": [],
        "metrics": {},
        "paths": {
            "oid_fc": p["oid_fc"],
            "oid_gdb": None,
            "reels_input": p["input_reels_folder"],
            "original_images": get_image_path(p["project_folder"], config, "original"),
            "enhanced_images": get_image_path(p["project_folder"], config, "enhanced"),
            "renamed_images": get_image_path(p["project_folder"], config, "renamed"),
        },
        "aws": {
            "bucket": resolve_if_expression(config.get("aws", {}).get("s3_bucket", ""), config),
            "folder": resolve_if_expression(config.get("aws", {}).get("s3_bucket_folder", ""), config)
        },
        "camera": {
            k: resolve_if_expression(v, config)
            for k, v in config.get("camera", {}).items()
        },
        "reels": []
    }

    # Resolve export folder (optional expression in config)
    export_expr = config.get("report", {}).get("export_folder_expr", "config.project.number")
    report_data["paths"]["export_folder"] = resolve_if_expression(export_expr, config)

    report_data["upload"] = {
        "status": "not_started",
        "count": 0,
        "expected_total": 0,
        "start_time": None,
        "end_time": None,
        "duration": None,
        "percent_complete": 0.0
    }

    return report_data


def save_report_json(report_data, project_folder, config, messages=None):
    """
    Saves the report data dictionary as a JSON file in the project's report directory.
    
    Attempts to write the provided report data to a JSON file named according to the project slug within the report
    directory specified in the configuration. Returns the file path as a string on success, or None if saving fails.
    """
    try:
        slug = config.get("project", {}).get("slug", "unknown")
        report_dir = Path(project_folder) / config.get("logs", {}).get("report_path", "report")
        report_dir.mkdir(parents=True, exist_ok=True)

        json_filename = f"report_data_{slug}.json"
        out_path = report_dir / json_filename

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        log_message(f"📝 Saved report JSON to: {out_path}", messages, config=config)
        return str(out_path)

    except Exception as e:
        log_message(f"[WARNING] Failed to save report JSON: {e}", messages, level="warning", config=config)
        return None


def load_report_json_if_exists(project_folder, config, messages=None) -> Optional[Dict[str, any]]:
    """
    Attempts to load an existing report JSON file for the project.
    
    If the report file exists in the designated report directory, parses and returns its contents as a dictionary.
    Returns None if the file does not exist or if loading fails.
    """
    try:
        slug = config.get("project", {}).get("slug", "unknown")
        report_dir = Path(project_folder) / config.get("logs", {}).get("report_path", "report")
        json_path = report_dir / f"report_data_{slug}.json"

        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                log_message(f"🔁 Reloading existing report JSON: {json_path}", messages, config=config)
                return json.load(f)

    except Exception as e:
        log_message(f"[WARNING] Failed to load prior report: {e}", messages, level="warning", config=config)

    return None
