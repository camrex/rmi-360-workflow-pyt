# =============================================================================
# 📦 Report Data Builder (utils/report_data_builder.py)
# -----------------------------------------------------------------------------
# Purpose:             Initializes, loads, and saves report data structures for the 360° workflow
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.3.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
# Last Updated:        2025-10-30
#
# Description:
#   Builds a structured JSON-compatible dictionary to track workflow progress, AWS info, camera metadata,
#   image paths, and summary metrics. Includes logic for resolving dynamic config expressions and provides
#   helper functions to persist and reload report data from disk.
#
# File Location:        /utils/report_data_builder.py
# Called By:            orchestrator, generate_report.py, progress dashboard
# Int. Dependencies:    utils/manager/config_manager
# Ext. Dependencies:    json, typing
#
# Documentation:
#   See: docs_legacy/UTILITIES.md and docs_legacy/tools/process_360_orchestrator.md
#
# Notes:
#   - Supports fallback-safe resolution of config.project.* expressions
#   - Creates report folder if it doesn’t exist
# =============================================================================

import json
from typing import Dict, Optional, Any

from utils.manager.config_manager import ConfigManager


def resolve_if_expression(val: Any, cfg: ConfigManager) -> Any:
    """
    Resolves a value as a configuration expression if it starts with 'config.'.

    Args:
        val: The value to resolve.
        cfg: The configuration manager.
    Returns:
        The resolved value if it is a config expression, else the original value.
    """
    if isinstance(val, str) and val.startswith('config.'):
        return cfg.resolve(val)
    return val

def initialize_report_data(paths_dict: Dict[str, Any], cfg: ConfigManager) -> Dict[str, Any]:
    """
    Create the initial structured report data dictionary for a project.
    
    Builds a report data dictionary containing project metadata, workflow steps and metrics placeholders,
    filesystem paths, resolved AWS settings, camera configuration (resolving any config expressions),
    an empty reels list, and an upload progress summary.
    
    Args:
        paths_dict (Dict[str, Any]): Input path values used to populate report paths (must include
            "oid_fc" and "input_reels_folder").
        cfg (ConfigManager): Configuration manager providing project metadata, path objects (cfg.paths),
            and accessors for camera and AWS settings.
    
    Returns:
        Dict[str, Any]: Report data with the following top-level keys:
            - project: project metadata from configuration
            - steps: list placeholder for workflow step records
            - metrics: dictionary placeholder for collected metrics
            - paths: dictionary with keys "oid_fc", "oid_gdb", "reels_input", "original_images",
              and "renamed_images"
            - aws: resolved S3 "bucket" and "folder" values
            - camera: resolved camera configuration values
            - reels: empty list to be populated with reel records
            - upload: dictionary summarizing upload status and progress fields
    """
    paths = cfg.paths
    report_data = {
        "project": cfg.get("project", {}),
        "steps": [],
        "metrics": {},
        "paths": {
            "oid_fc": paths_dict["oid_fc"],
            "oid_gdb": None,
            "reels_input": paths_dict["input_reels_folder"],
            "original_images": str(paths.original),
            "renamed_images": str(paths.renamed)
        },
        "aws": {
            "bucket": cfg.resolve(cfg.get("aws.s3_bucket", "")),
            "folder": cfg.resolve(cfg.get("aws.s3_bucket_folder", ""))
        },
        "camera": {
            k: resolve_if_expression(v, cfg)
            for k, v in cfg.get("camera", {}).items()
        },
        "reels": [],
        "upload": {
            "status": "not_started",
            "count": 0,
            "expected_total": 0,
            "start_time": None,
            "end_time": None,
            "duration": None,
            "percent_complete": 0.0
        }
    }
    return report_data

def save_report_json(report_data: Dict[str, Any], cfg: ConfigManager, logger: Optional[Any] = None) -> Optional[str]:
    """
    Saves the report data dictionary as a JSON file in the project's report directory.

    Args:
        report_data: The report data dictionary to save.
        cfg: The configuration manager.
        logger: Optional logger for testability. Defaults to cfg.get_logger().
    Returns:
        The file path as a string on success, or None if saving fails.
    """
    logger = logger or cfg.get_logger()
    paths = cfg.paths
    try:
        slug = cfg.get("project.slug", "unknown")
        report_dir = paths.report
        report_dir.mkdir(parents=True, exist_ok=True)

        json_filename = f"report_data_{slug}.json"
        out_path = report_dir / json_filename

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.custom(f"Saved report JSON to: {out_path}", emoji="📄", indent=1)
        return str(out_path)

    except Exception as e:
        logger.error(f"Failed to save report JSON: {e}", indent=1)
        return None


def load_report_json_if_exists(cfg: ConfigManager, logger: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """
    Attempts to load an existing report JSON file for the project.

    Args:
        cfg: The configuration manager.
        logger: Optional logger for testability. Defaults to cfg.get_logger().
    Returns:
        The loaded dictionary if successful, or None if not found or on error.
    """
    logger = logger or cfg.get_logger()
    paths = cfg.paths
    try:
        slug = cfg.get("project.slug", "unknown")
        report_dir = paths.report
        json_path = report_dir / f"report_data_{slug}.json"

        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
    except Exception as e:
        logger.error(f"Failed to load report JSON: {e}", indent=1)
        return None