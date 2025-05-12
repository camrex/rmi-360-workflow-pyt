# =============================================================================
# 🧭 Workflow Step Function Builder (utils/build_step_funcs.py)
# -----------------------------------------------------------------------------
# Purpose:             Constructs an ordered dictionary of callable workflow steps for OID processing
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Maps each pipeline step in the 360° imagery workflow to a labeled function. Supports conditional
#   skipping, parameter injection, and integration with orchestrator tools. Used to define the full
#   ordered execution sequence from raw video to cloud-published OID feature service.
#
# File Location:        /utils/build_step_funcs.py
# Called By:            tools/process_360_orchestrator.py
# Int. Dependencies:    All workflow utils (mosaic_processor, enhance_images, copy_to_aws, etc.)
# Ext. Dependencies:    None
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/TOOL_OVERVIEW.md
#
# Notes:
#   - Controls step label mapping, execution logic, and skip conditions
#   - Central entry point for orchestrator workflow automation
# =============================================================================

from utils.mosaic_processor import run_mosaic_processor
from utils.create_oid_feature_class import create_oriented_imagery_dataset
from utils.add_images_to_oid_fc import add_images_to_oid
from utils.assign_group_index import assign_group_index
from utils.calculate_oid_attributes import enrich_oid_attributes
from utils.smooth_gps_noise import smooth_gps_noise
from utils.correct_gps_outliers import correct_gps_outliers
from utils.update_linear_and_custom import update_linear_and_custom
from utils.enhance_images import enhance_images_in_oid
from utils.rename_images import rename_images
from utils.apply_exif_metadata import update_metadata_from_config
from utils.geocode_images import geocode_images
from utils.build_oid_footprints import build_oid_footprints
from utils.deploy_lambda_monitor import deploy_lambda_monitor
from utils.copy_to_aws import copy_to_aws
from utils.generate_oid_service import generate_oid_service

from utils.arcpy_utils import str_to_bool


def build_step_funcs(p, config, messages):
    """
    Builds a dictionary of processing step descriptors for an oriented imagery workflow.
    
    Each step descriptor includes a label, a callable for execution, and optional skip logic
    based on input parameters. The returned dictionary maps step keys to their corresponding
    descriptors, enabling sequential or conditional execution of the workflow steps.
    """
    return {
        "run_mosaic_processor": {
            "label": "Run Mosaic Processor",
            "func": lambda: run_mosaic_processor(
                project_folder=p["project_folder"],
                input_dir=p["input_reels_folder"],
                config=config,
                messages=messages
            )
        },
        "create_oid": {
            "label": "Create Oriented Imagery Dataset",
            "func": lambda: create_oriented_imagery_dataset(
                output_fc_path=p["oid_fc"],
                config=config,
                messages=messages
            )
        },
        "add_images": {
            "label": "Add Images to OID",
            "func": lambda: add_images_to_oid(
                project_folder=p["project_folder"],
                oid_fc_path=p["oid_fc"],
                config=config,
                messages=messages
            )
        },
        "assign_group_index": {
            "label": "Assign Group Index",
            "func": lambda: assign_group_index(
                oid_fc_path=p["oid_fc"],
                config=config,
                messages=messages
            )
        },
        "enrich_oid": {
            "label": "Calculate OID Attributes",
            "func": lambda: enrich_oid_attributes(
                oid_fc_path=p["oid_fc"],
                config=config,
                messages=messages
            )
        },
        "smooth_gps": {
            "label": "Smooth GPS Noise",
            "func": lambda: smooth_gps_noise(
                oid_fc=p["oid_fc"],
                centerline_fc=p["centerline_fc"],
                config=config,
                messages=messages
            )
        },
        "correct_gps": {
            "label": "Correct Flagged GPS Points",
            "func": lambda: correct_gps_outliers(
                oid_fc=p["oid_fc"],
                config=config,
                messages=messages
            )
        },
        "update_linear_custom": {
            "label": "Update Linear and Custom Attributes",
            "func": lambda: update_linear_and_custom(
                oid_fc=p["oid_fc"],
                centerline_fc=p["centerline_fc"],
                route_id_field=p["route_id_field"],
                enable_linear_ref=str_to_bool(p["enable_linear_ref"]),
                config=config,
                messages=messages
            )
        },
        "enhance_images": {
            "label": "Enhance Images",
            "func": lambda: enhance_images_in_oid(
                oid_fc_path=p["oid_fc"],
                config=config,
                messages=messages
            ),
            "skip": lambda params: "Skipped (enhancement disabled)" if params.get("skip_enhance_images") == "true" else None
        },
        "rename_images": {
            "label": "Rename Images",
            "func": lambda: rename_images(
                oid_fc=p["oid_fc"],
                config=config,
                messages=messages
            )
        },
        "update_metadata": {
            "label": "Update EXIF Metadata",
            "func": lambda: update_metadata_from_config(
                oid_fc=p["oid_fc"],
                config=config,
                messages=messages
            )
        },
        "geocode": {
            "label": "Geocode Images",
            "func": lambda: geocode_images(
                oid_fc=p["oid_fc"],
                config=config,
                messages=messages
            )
        },
        "build_footprints": {
            "label": "Build OID Footprints",
            "func": lambda: build_oid_footprints(
                oid_fc=p["oid_fc"],
                config=config,
                messages=messages
            )
        },
        "deploy_lambda_monitor": {
            "label": "Deploy Lambda AWS Monitor",
            "func": lambda: deploy_lambda_monitor(
                config=config,
                messages=messages
            ),
            "skip": lambda params: "Skipped (disabled by user)" if params.get("copy_to_aws") != "true" else None
        },
        "copy_to_aws": {
            "label": "Upload to AWS S3",
            "func": lambda: copy_to_aws(
                config=config,
                messages=messages
            ),
            "skip": lambda params: "Skipped (disabled by user)" if params.get("copy_to_aws") != "true" else None
        },
        "generate_service": {
            "label": "Generate OID Service",
            "func": lambda: generate_oid_service(
                oid_fc=p["oid_fc"],
                config=config,
                messages=messages
            ),
            "skip": lambda params: "Skipped (disabled by user)" if params.get("copy_to_aws") != "true" else None
        }
    }


def get_step_order(step_funcs: dict) -> list:
    """
    Returns a list of step keys in the order they appear in the step_funcs dictionary.
    
    Args:
        step_funcs: A dictionary mapping step keys to step descriptors.
    
    Returns:
        A list of step keys preserving their original order.
    """
    return list(step_funcs.keys())
