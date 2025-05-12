# =============================================================================
# 📦 Report Data Builder (utils/report_data_builder.py)
# -----------------------------------------------------------------------------
# Purpose:             Initializes, loads, and saves report data structures for the 360° workflow
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Builds a structured JSON-compatible dictionary to track workflow progress, AWS info, camera metadata,
#   image paths, and summary metrics. Includes logic for resolving dynamic config expressions and provides
#   helper functions to persist and reload report data from disk.
#
# File Location:        /utils/report_data_builder.py
# Called By:            orchestrator, generate_report.py, progress dashboard
# Int. Dependencies:    expression_utils, arcpy_utils
# Ext. Dependencies:    os, json, pathlib, typing
#
# Documentation:
#   See: docs_legacy/UTILITIES.md and docs_legacy/tools/process_360_orchestrator.md
#
# Notes:
#   - Supports fallback-safe resolution of config.project.* expressions
#   - Creates report folder if it doesn’t exist
# =============================================================================

import json
from typing import Dict, Optional
from utils.manager.config_manager import ConfigManager


def resolve_if_expression(val, cfg:ConfigManager):
    """
    Resolves a value as a configuration expression if it starts with 'config.'.
    
    If the input is a string beginning with 'config.', evaluates it as an expression
    against the provided config dictionary. Otherwise, returns the value unchanged.
    """
    return cfg.resolve(val) if isinstance(val, str) and val.startswith("config.") else val


def initialize_report_data(p, cfg: ConfigManager) -> Dict:
    """
    Initializes and returns a dictionary containing structured report data for a project.
    
    The returned dictionary includes project metadata, empty collections for steps and metrics, resolved file paths
    for images and reels, AWS S3 bucket information, camera configuration with dynamic value resolution, an export
    folder path, and an upload status tracker. Configuration values that are expressions prefixed with "config." are
    resolved against the provided config dictionary.
    
    Args:
        p: Dictionary containing project folder paths and input locations.
        cfg: Dictionary with project configuration and metadata.
    
    Returns:
        A dictionary representing the initialized report data structure.
    """
    paths = cfg.paths

    report_data = {"project": cfg.get("project", {}), "steps": [], "metrics": {}, "paths": {
        "oid_fc": p["oid_fc"],
        "oid_gdb": None,
        "reels_input": p["input_reels_folder"],
        "original_images": str(paths.original),
        "enhanced_images": str(paths.enhanced),
        "renamed_images": str(paths.renamed)
    }, "aws": {
        "bucket": cfg.resolve(cfg.get("aws.s3_bucket", "")),
        "folder": cfg.resolve(cfg.get("aws.s3_bucket_folder", ""))
    }, "camera": {
        k: resolve_if_expression(v, cfg)
        for k, v in cfg.get("camera", {}).items()
    }, "reels": [], "upload": {
        "status": "not_started",
        "count": 0,
        "expected_total": 0,
        "start_time": None,
        "end_time": None,
        "duration": None,
        "percent_complete": 0.0
    }}

    return report_data


def save_report_json(report_data, cfg: ConfigManager):
    """
    Saves the report data dictionary as a JSON file in the project's report directory.
    
    Attempts to write the provided report data to a JSON file named according to the project slug within the report
    directory specified in the configuration. Returns the file path as a string on success, or None if saving fails.
    """
    logger = cfg.get_logger()
    paths = cfg.paths
    try:
        slug = cfg.get("project.slug", "unknown")
        report_dir = paths.report
        report_dir.mkdir(parents=True, exist_ok=True)

        json_filename = f"report_data_{slug}.json"
        out_path = report_dir / json_filename

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info(f"📝 Saved report JSON to: {out_path}")
        return str(out_path)

    except Exception as e:
        logger.warning(f"Failed to save report JSON: {e}")
        return None


def load_report_json_if_exists(cfg:ConfigManager) -> Optional[Dict[str, any]]:
    """
    Attempts to load an existing report JSON file for the project.
    
    If the report file exists in the designated report directory, parses and returns its contents as a dictionary.
    Returns None if the file does not exist or if loading fails.
    """
    logger = cfg.get_logger()
    paths = cfg.paths
    try:
        slug = cfg.get("project.slug", "unknown")
        report_dir = paths.report
        json_path = report_dir / f"report_data_{slug}.json"

        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                logger.info(f"🔁 Reloading existing report JSON: {json_path}")
                return json.load(f)

    except Exception as e:
        logger.warning(f"Failed to load prior report: {e}")

    return None
