# =============================================================================
# 🧭 Workflow Step Function Builder (utils/build_step_funcs.py)
# -----------------------------------------------------------------------------
# Purpose:             Constructs an ordered dictionary of callable workflow steps for OID processing
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.3.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
# Last Updated:        2025-10-30
#
# Description:
#   Maps each pipeline step in the 360° imagery workflow to a labeled function. Supports conditional
#   skipping, parameter injection, and integration with orchestrator tools. Used to define the full
#   ordered execution sequence from raw video to cloud-published OID feature service.
#
# File Location:        /utils/build_step_funcs.py
# Called By:            tools/process_360_orchestrator.py
# Int. Dependencies:    All workflow utils (mosaic_processor, copy_to_aws, etc.), utils/shared/arcpy_utils
# Ext. Dependencies:    collections
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/TOOL_OVERVIEW.md
#   (Ensure these docs are current; update if needed.)
#
# Notes:
#   - Controls step label mapping, execution logic, and skip conditions
#   - Central entry point for orchestrator workflow automation
# =============================================================================

from collections import namedtuple

from utils.mosaic_processor import run_mosaic_processor
from utils.create_oid_feature_class import create_oriented_imagery_dataset
from utils.add_images_to_oid_fc import add_images_to_oid
from utils.assign_group_index import assign_group_index
from utils.calculate_oid_attributes import enrich_oid_attributes
from utils.smooth_gps_noise import smooth_gps_noise
from utils.correct_gps_outliers import correct_gps_outliers
from utils.update_linear_and_custom import update_linear_and_custom
from utils.rename_images import rename_images
from utils.apply_exif_metadata import update_metadata_from_config
from utils.geocode_images import geocode_images
from utils.build_oid_footprints import build_oid_footprints
from utils.deploy_lambda_monitor import deploy_lambda_monitor
from utils.copy_to_aws import copy_to_aws
from utils.generate_oid_service import generate_oid_service

StepSpec = namedtuple("StepSpec", ["key", "label", "func_builder", "skip_fn"])



def skip_if_copy_to_aws_disabled(params):
    # New logic: skip if 'enable_copy_to_aws' is not True
    """
    Return a skip message when the copy-to-AWS feature is disabled in the provided parameters.
    
    Parameters:
        params (dict): Pipeline or workflow parameters; expects an 'enable_copy_to_aws' key whose value indicates whether copying to AWS is enabled.
    
    Returns:
        str or None: 'Skipped (disabled by user)' if 'enable_copy_to_aws' is not True, `None` otherwise.
    """
    return "Skipped (disabled by user)" if not params.get("enable_copy_to_aws", False) else None

def skip_if_smooth_gps_disabled(params):
    return "Skipped (disabled by user)" if not params.get("enable_smooth_gps", False) else None

def skip_if_geocode_disabled(params):
    return "Skipped (disabled by user)" if not params.get("enable_geocode", False) else None

def skip_if_deploy_lambda_monitor_disabled(params):
    return "Skipped (disabled by user)" if not params.get("enable_deploy_lambda_monitor", False) else None

def skip_if_generate_service_disabled(params):
    return "Skipped (disabled by user)" if not params.get("enable_generate_service", False) else None

def build_step_funcs(p, cfg):
    """
    Builds an ordered mapping of workflow step descriptors for the oriented imagery pipeline.
    
    Each mapping value is a descriptor dict containing:
    - `label`: human-readable step name,
    - `func`: a callable that executes the step (callable may accept keyword args),
    - optional `skip`: a function that, given run parameters, returns a skip message or None.
    
    Parameters:
        p (dict): Runtime parameters and paths used to configure each step (e.g., `input_reels_folder`, `oid_fc`, `centerline_fc`, `route_id_field`, `enable_linear_ref`, etc.).
        cfg (Mapping): Configuration/settings object used by step implementations.
    
    Returns:
        dict: An ordered dictionary mapping each step key (str) to its descriptor dict as described above.
    """
    step_specs = [
        StepSpec("run_mosaic_processor", "Run Mosaic Processor",
            lambda params, config: lambda **kwargs: run_mosaic_processor(input_dir=p["input_reels_folder"], cfg=cfg), None),
        StepSpec("create_oid", "Create Oriented Imagery Dataset",
            lambda params, config: lambda **kwargs: create_oriented_imagery_dataset(output_fc_path=p["oid_fc"], cfg=cfg), None),
        StepSpec("add_images", "Add Images to OID",
            lambda params, config: lambda **kwargs: add_images_to_oid(oid_fc_path=p["oid_fc"], cfg=cfg), None),
        StepSpec("assign_group_index", "Assign Group Index",
            lambda params, config: lambda **kwargs: assign_group_index(oid_fc_path=p["oid_fc"], cfg=cfg), None),
        StepSpec("enrich_oid", "Calculate OID Attributes",
            lambda params, config: lambda **kwargs: enrich_oid_attributes(oid_fc_path=p["oid_fc"], cfg=cfg), None),
        StepSpec("smooth_gps", "Smooth GPS Noise",
            lambda params, config: lambda **kwargs: smooth_gps_noise(oid_fc=p["oid_fc"], centerline_fc=p["centerline_fc"], cfg=cfg), skip_if_smooth_gps_disabled),
        StepSpec("correct_gps", "Correct Flagged GPS Points",
            lambda params, config: lambda **kwargs: correct_gps_outliers(oid_fc=p["oid_fc"], cfg=cfg), skip_if_smooth_gps_disabled),
        StepSpec("update_linear_custom", "Update Linear and Custom Attributes",
            lambda params, config: lambda **kwargs: update_linear_and_custom(oid_fc_path=p["oid_fc"], centerline_fc=p["centerline_fc"], route_id_field=p["route_id_field"], enable_linear_ref=p["enable_linear_ref"], cfg=cfg), None),
        StepSpec("rename_images", "Rename Images",
            lambda params, config: lambda **kwargs: rename_images(oid_fc=p["oid_fc"], cfg=cfg, enable_linear_ref=p["enable_linear_ref"]), None),
        StepSpec("update_metadata", "Update EXIF Metadata",
            lambda params, config: lambda **kwargs: update_metadata_from_config(oid_fc=p["oid_fc"], cfg=cfg), None),
        StepSpec("geocode", "Geocode Images",
            lambda params, config: lambda **kwargs: geocode_images(oid_fc=p["oid_fc"], cfg=cfg), skip_if_geocode_disabled),
        StepSpec("build_footprints", "Build OID Footprints",
            lambda params, config: lambda **kwargs: build_oid_footprints(oid_fc=p["oid_fc"], cfg=cfg), None),
        StepSpec("deploy_lambda_monitor", "Deploy Lambda AWS Monitor",
            lambda params, config: lambda **kwargs: deploy_lambda_monitor(cfg=cfg), skip_if_deploy_lambda_monitor_disabled),
        StepSpec("copy_to_aws", "Upload to AWS S3",
            lambda params, config: lambda **kwargs: copy_to_aws(cfg=cfg, **kwargs), skip_if_copy_to_aws_disabled),
        StepSpec("generate_service", "Generate OID Service",
            lambda params, config: lambda **kwargs: generate_oid_service(oid_fc=p["oid_fc"], cfg=cfg), skip_if_generate_service_disabled),
    ]
    step_funcs = {}
    for spec in step_specs:
        entry = {"label": spec.label, "func": spec.func_builder(p, cfg)}
        if spec.skip_fn:
            entry["skip"] = spec.skip_fn
        step_funcs[spec.key] = entry
    return step_funcs


def get_step_order(step_funcs: dict) -> list:
    """
    Return the ordered list of step keys as they appear in the provided step mapping.
    
    Parameters:
        step_funcs (dict): Mapping of step keys to step descriptor dictionaries.
    
    Returns:
        list: Step keys in the mapping's insertion order.
    """
    return list(step_funcs.keys())