# =============================================================================
# 🧰 Process Full Mosaic 360 Workflow (tools/process_360_orchestrator.py)
# -----------------------------------------------------------------------------
# Tool Name:          Process360Workflow
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.3.0
# Author:             RMI Valuation, LLC
# Created:            2025-05-08
# Last Updated:       2025-10-29
#
# Description:
#   Orchestrates the full end-to-end Mosaic 360 image processing pipeline within ArcGIS Pro.
#   Supports both Local and AWS-based execution environments. The tool determines which reel
#   folders to process—either from local project directories or from an S3 bucket—and runs a
#   configurable series of workflow steps including image rendering, OID creation, enrichment,
#   geolocation, AWS copy, and service publishing. Progress and results are tracked
#   in a persistent report JSON for dashboarding and audit.
#
# File Location:      /tools/process_360_orchestrator.py
#
# Core Utils:
#   - utils/build_step_funcs.py
#   - utils/step_runner.py
#   - utils/generate_report.py
#   - utils/manager/config_manager.py
#   - utils/shared/report_data_builder.py
#   - utils/shared/folder_stats.py
#   - utils/shared/gather_metrics.py
#   - utils/shared/arcpy_utils.py
#   - utils/s3_utils.py  ← (replaces old utils/s3_stage.py)
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/process_360_orchestrator.md
#   (Ensure these docs are updated to reflect Local/AWS workflow parity.)
#
# Parameters:
#   - Config File {config_file} (File): Optional override for the default config.yaml path.
#   - Source Mode {source_mode} (String): Select processing environment: Local | AWS.
#   - Project Folder {project_folder} (Folder): Root project directory (required in both Local and AWS modes).
#   - Raw S3 Bucket {raw_s3_bucket} (String): S3 bucket name containing raw 360 data (AWS mode).
#   - Project Key {project_key} (String): Selected project folder in the raw S3 bucket (AWS mode).
#   - Reels to Process {reels_to_process} (Multivalue String): Reel folders to process; if none selected, all reels are used.
#   - Staging Folder {staging_folder} (Folder): Optional local folder where reels are staged for processing.
#   - Start From Step {start_step} (String): Step label to begin from; earlier steps are skipped.
#   - OID Dataset - Input {oid_fc_input} (Feature Class): Existing Oriented Imagery Dataset (OID) to update.
#   - OID Dataset - Output {oid_fc_output} (Feature Class): Output OID (used only when creating a new dataset).
#   - Enable Smooth GPS {enable_smooth_gps} (Boolean): Enables smoothing and correction of GPS data.
#   - Enable Linear Referencing {enable_linear_ref} (Boolean): Enables MP/Route ID computation per image.
#   - Enable Geocode Images {enable_geocode} (Boolean): Enables image geolocation using GPS or address data.
#   - Enable Copy to AWS {enable_copy_to_aws} (Boolean): Uploads processed imagery and reports to AWS.
#   - Enable Deploy Lambda Monitor {enable_deploy_lambda_monitor} (Boolean): Deploys AWS monitoring Lambda (if enabled).
#   - Enable Generate Service {enable_generate_service} (Boolean): Publishes an OID web feature service.
#   - Centerline (M-enabled) {centerline_fc} (Feature Class): Polyline for GPS smoothing or referencing.
#   - Route ID Field {route_id_field} (Field): Field identifying route IDs in the centerline dataset.
#   - Generate HTML Report {generate_report} (Boolean): Whether to generate a visual report at the end.
#
# Notes:
#   - New "Source Mode" logic (Local vs AWS) replaces legacy stage_from_s3/s3_reels_prefix parameters.
#   - Local mode assumes reels are under <project_folder>/reels.
#   - AWS mode lists projects/reels directly from the S3 bucket and stages selected reels locally.
#   - Reels are always processed from a local folder—either directly (Local) or via staging (AWS).
#   - The tool maintains persistent JSON-based reporting and supports resumable workflows.
#   - Ensure all Core Utils and config files are synchronized for consistent behavior.
# =============================================================================

from typing import Optional, Any, Callable, Dict, List
from pathlib import Path
import arcpy
import time
import os

from utils.manager.config_manager import ConfigManager
from utils.generate_report import generate_report_from_json
from utils.step_runner import run_steps
from utils.build_step_funcs import build_step_funcs, get_step_order
from utils.shared.gather_metrics import collect_oid_metrics, summarize_oid_metrics
from utils.shared.folder_stats import folder_stats
from utils.shared.report_data_builder import (
    initialize_report_data,
    save_report_json,
    load_report_json_if_exists,
)
from utils.s3_utils import stage_reels, list_projects, list_reels


class Process360Workflow(object):
    def __init__(
        self,
        arcpy_mod: Any = None,
        os_mod: Any = None,
        time_mod: Any = None,
        collect_oid_metrics_fn: Optional[Callable] = None,
        summarize_oid_metrics_fn: Optional[Callable] = None,
        folder_stats_fn: Optional[Callable] = None,
        build_step_funcs_fn: Optional[Callable] = None,
        get_step_order_fn: Optional[Callable] = None,
        run_steps_fn: Optional[Callable] = None,
        initialize_report_data_fn: Optional[Callable] = None,
        save_report_json_fn: Optional[Callable] = None,
        load_report_json_if_exists_fn: Optional[Callable] = None,
        generate_report_from_json_fn: Optional[Callable] = None,
    ):
        """
        Allows injection of dependencies for testability.
        Defaults to real modules/functions if not provided.
        """
        self.arcpy_mod = arcpy_mod or arcpy
        self.os_mod = os_mod or os
        self.time_mod = time_mod or time
        self.collect_oid_metrics_fn = collect_oid_metrics_fn or collect_oid_metrics
        self.summarize_oid_metrics_fn = summarize_oid_metrics_fn or summarize_oid_metrics
        self.folder_stats_fn = folder_stats_fn or folder_stats
        self.build_step_funcs_fn = build_step_funcs_fn or build_step_funcs
        self.get_step_order_fn = get_step_order_fn or get_step_order
        self.run_steps_fn = run_steps_fn or run_steps
        self.initialize_report_data_fn = initialize_report_data_fn or initialize_report_data
        self.save_report_json_fn = save_report_json_fn or save_report_json
        self.load_report_json_if_exists_fn = load_report_json_if_exists_fn or load_report_json_if_exists
        self.generate_report_from_json_fn = generate_report_from_json_fn or generate_report_from_json

    @staticmethod
    def parameters_to_dict(parameters: List[Any]) -> Dict[str, Any]:
        """
        Converts ArcPy tool parameters to a dictionary keyed by parameter name.
        Ensures all GPBoolean and 'enable_*' parameters are Python bools for skip logic.
        """
        result: Dict[str, Any] = {}
        for param in parameters:
            if getattr(param, "datatype", None) == "GPBoolean" or param.name.startswith("enable_"):
                result[param.name] = bool(param.value)
            else:
                result[param.name] = param.valueAsText
        return result

    @staticmethod
    def _symlink_or_copy(src: Path, dst: Path, logger=None):
        """
        Try to create a symlink; on Windows without elevation or if symlink fails,
        fall back to a directory copy (preserves behavior).
        """
        try:
            os.symlink(src, dst, target_is_directory=True)
            if logger:
                logger.info(f"Symlinked: {src} -> {dst}", indent=2)
        except Exception as e:
            if logger:
                logger.info(f"Symlink failed ({e}); copying instead: {src} -> {dst}", indent=2)
            import shutil
            shutil.copytree(src, dst, dirs_exist_ok=True)

    def _compute_and_store_folder_stats(self, labels: List[str], paths: Any, report_data: dict, logger: Any):
        """
        Helper to compute and store folder stats for the given labels.
        """
        for label in labels:
            try:
                folder_path = getattr(paths, label)
                count, size = self.folder_stats_fn(folder_path)
                report_data.setdefault("paths", {})[f"{label}_images"] = str(folder_path)
                report_data.setdefault("metrics", {})[f"{label}_count"] = count
                report_data.setdefault("metrics", {})[f"{label}_size"] = size
            except Exception as e:
                report_data.setdefault("metrics", {})[f"{label}_count"] = 0
                report_data.setdefault("metrics", {})[f"{label}_size"] = "0 B"
                logger.warning(f"Failed to compute folder stats for {label}: {e}")

    label = "Process Full Mosaic 360 Workflow"
    description = (
        "Runs the full Mosaic 360 image processing pipeline including:\n"
        "1) Run Mosaic Processor\n"
        "2) Create Oriented Imagery Dataset\n"
        "3) Add Images to OID\n"
        "4) Assign Group Index\n"
        "5) Calculate OID Attributes\n"
        "6) Smooth GPS Noise (optional)\n"
        "7) Correct Flagged GPS Points (optional)\n"
        "8) Update Linear and Custom Attributes (linear referencing optional)\n"
        "9) Rename Images\n"
        "10) Update EXIF Metadata\n"
        "11) Geocode Images (optional)\n"
        "12) Create OID Footprints\n"
        "13) Deploy Lambda Monitor (optional)\n"
        "14) Copy to AWS (optional)\n"
        "15) Generate OID Service (optional)"
    )
    canRunInBackground = False

    # Explicitly define the steps with a numeric index to ensure correct order
    STEP_FUNCTIONS = [
        (1, "run_mosaic_processor", "Run Mosaic Processor"),
        (2, "create_oid", "Create Oriented Imagery Dataset"),
        (3, "add_images", "Add Images to OID"),
        (4, "assign_group_index", "Assign Group Index"),
        (5, "enrich_oid", "Calculate OID Attributes"),
        (6, "smooth_gps", "Smooth GPS Noise"),
        (7, "correct_gps", "Correct Flagged GPS Points"),
        (8, "update_linear_custom", "Update Linear and Custom Attributes"),
        (9, "rename_images", "Rename Images"),
        (10, "update_metadata", "Update EXIF Metadata"),
        (11, "geocode", "Geocode Images"),
        (12, "build_footprints", "Build OID Footprints"),
        (13, "deploy_lambda_monitor", "Deploy Lambda Monitor"),
        (14, "copy_to_aws", "Upload to AWS S3"),
        (15, "generate_service", "Generate OID Service")
    ]

    # Sort by numeric index and extract step names in the correct order
    STEP_ORDER = [step[1] for step in sorted(STEP_FUNCTIONS, key=lambda x: x[0])]

    def getParameterInfo(self):
        """
        Defines and returns the list of ArcPy parameters for the Mosaic 360 workflow tool
        in the new, AWS/Local-aware order.
        """
        params: List[Any] = []

        # -- Build step labels
        label_to_name = {label: name for _, name, label in self.STEP_FUNCTIONS}
        name_to_label = {name: label for _, name, label in self.STEP_FUNCTIONS}
        step_labels = [label for _, _, label in self.STEP_FUNCTIONS]

        # 0) Config File
        config_file_param = arcpy.Parameter(
            displayName="Config File",
            name="config_file",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input",
        )
        config_file_param.filter.list = ["yaml", "yml"]
        params.append(config_file_param)

        # 1) Source Mode
        source_mode_param = arcpy.Parameter(
            displayName="Source Mode",
            name="source_mode",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        source_mode_param.filter.list = ["Local", "AWS"]
        source_mode_param.value = "Local"
        params.append(source_mode_param)

        # 2) Project Folder (required in both modes)
        project_folder_param = arcpy.Parameter(
            displayName="Project Folder",
            name="project_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
        )
        params.append(project_folder_param)

        # 3) Raw S3 Bucket (AWS only)
        s3_bucket_raw_param = arcpy.Parameter(
            displayName="Raw S3 Bucket (AWS)",
            name="raw_s3_bucket",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )
        params.append(s3_bucket_raw_param)

        # 4) AWS Project Key (AWS; dropdown)
        aws_project_key_param = arcpy.Parameter(
            displayName="Project Key (AWS)",
            name="project_key",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )
        params.append(aws_project_key_param)

        # 5) Reels to Process (multiselect; optional)
        reels_to_process_param = arcpy.Parameter(
            displayName="Reels to Process",
            name="reels_to_process",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
            multiValue=True,
        )
        params.append(reels_to_process_param)

        # 6) Staging Folder
        staging_folder_param = arcpy.Parameter(
            displayName="Staging Folder (Optional)",
            name="staging_folder",
            datatype="DEFolder",
            parameterType="Optional",
            direction="Input",
        )
        params.append(staging_folder_param)

        # 7) Start From Step
        start_step_param = arcpy.Parameter(
            displayName="Start From Step (Optional)",
            name="start_step",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )
        start_step_param.filter.list = ["--SELECT STEP--"] + step_labels
        start_step_param.value = "--SELECT STEP--"
        params.append(start_step_param)

        # Save label/name maps for dynamic code
        self._step_label_to_name = label_to_name
        self._step_name_to_label = name_to_label

        # 8) OID Input
        oid_fc_input_param = arcpy.Parameter(
            displayName="OID Dataset - Input (used in most steps)",
            name="oid_fc_input",
            datatype="DEFeatureClass",
            parameterType="Optional",
            direction="Input",
        )
        oid_fc_input_param.enabled = False
        params.append(oid_fc_input_param)

        # 9) OID Output
        oid_fc_output_param = arcpy.Parameter(
            displayName="OID Dataset - Output (used only when creating a new OID)",
            name="oid_fc_output",
            datatype="DEFeatureClass",
            parameterType="Optional",
            direction="Output",
        )
        oid_fc_output_param.enabled = False
        params.append(oid_fc_output_param)

        # 10) Enable Smooth GPS
        enable_smooth_gps_param = arcpy.Parameter(
            displayName="Enable Smooth GPS (and Correct GPS)",
            name="enable_smooth_gps",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        enable_smooth_gps_param.value = True
        params.append(enable_smooth_gps_param)

        # 11) Enable Linear Referencing
        enable_linear_ref_param = arcpy.Parameter(
            displayName="Enable Linear Referencing",
            name="enable_linear_ref",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        enable_linear_ref_param.value = True
        params.append(enable_linear_ref_param)

        # 12) Enable Geocode Images
        enable_geocode_param = arcpy.Parameter(
            displayName="Enable Geocode Images",
            name="enable_geocode",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        enable_geocode_param.value = True
        params.append(enable_geocode_param)

        # 13) Enable Copy to AWS
        enable_copy_to_aws_param = arcpy.Parameter(
            displayName="Enable Copy to AWS",
            name="enable_copy_to_aws",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        enable_copy_to_aws_param.value = True
        params.append(enable_copy_to_aws_param)

        # 14) Enable Deploy Lambda Monitor
        enable_deploy_lambda_monitor_param = arcpy.Parameter(
            displayName="Enable Deploy Lambda Monitor",
            name="enable_deploy_lambda_monitor",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        enable_deploy_lambda_monitor_param.value = True
        params.append(enable_deploy_lambda_monitor_param)

        # 15) Enable Generate OID Service
        enable_generate_service_param = arcpy.Parameter(
            displayName="Enable Generate OID Service",
            name="enable_generate_service",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        enable_generate_service_param.value = True
        params.append(enable_generate_service_param)

        # 16) Centerline (Polyline)
        centerline_param = arcpy.Parameter(
            displayName="Centerline (M-enabled, used for GPS smoothing and linear referencing)",
            name="centerline_fc",
            datatype="DEFeatureClass",
            parameterType="Optional",
            direction="Input",
        )
        centerline_param.filter.list = ["Polyline"]
        params.append(centerline_param)

        # 17) Route ID Field
        route_id_param = arcpy.Parameter(
            displayName="Route ID Field",
            name="route_id_field",
            datatype="Field",
            parameterType="Optional",
            direction="Input",
        )
        route_id_param.parameterDependencies = [centerline_param.name]
        route_id_param.filter.list = ["Short", "Long", "Text"]
        params.append(route_id_param)

        # 18) Generate HTML Summary Report
        generate_report_param = arcpy.Parameter(
            displayName="Generate HTML Summary Report",
            name="generate_report",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        generate_report_param.value = True
        params.append(generate_report_param)

        return params

    def updateParameters(self, parameters):
        """
        Dynamic UI logic for Process360Workflow — name-based (no indices).
        - Drives Local vs AWS discovery
        - Populates project_key + reels_to_process
        - Mirrors existing OID/centerline/route + copy→lambda/service gating
        """
        pmap = {p.name: p for p in parameters}

        # Ensure label maps exist
        if not hasattr(self, "_step_label_to_name") or not hasattr(self, "_step_name_to_label"):
            self._step_label_to_name = {label: name for _, name, label in self.STEP_FUNCTIONS}
            self._step_name_to_label = {name: label for _, name, label in self.STEP_FUNCTIONS}

        # Shorthands
        source_mode = pmap.get("source_mode")
        project_folder = pmap.get("project_folder")
        config_file = pmap.get("config_file")
        raw_s3_bucket = pmap.get("raw_s3_bucket")
        project_key = pmap.get("project_key")
        reels_param = pmap.get("reels_to_process")
        staging_folder = pmap.get("staging_folder")

        start_step = pmap.get("start_step")
        oid_in = pmap.get("oid_fc_input")
        oid_out = pmap.get("oid_fc_output")
        enable_smooth_gps = pmap.get("enable_smooth_gps")
        enable_linear_ref = pmap.get("enable_linear_ref")

        centerline_param = pmap.get("centerline_fc")
        route_id_param = pmap.get("route_id_field")

        enable_copy_to_aws = pmap.get("enable_copy_to_aws")
        enable_deploy_lambda_monitor = pmap.get("enable_deploy_lambda_monitor")
        enable_generate_service = pmap.get("enable_generate_service")

        # 1) Local vs AWS
        is_aws = (source_mode.valueAsText == "AWS") if source_mode and source_mode.valueAsText else False

        # Always enable Project Folder (required in both modes)
        if project_folder:
            project_folder.enabled = True

        if raw_s3_bucket:
            raw_s3_bucket.enabled = is_aws

        if project_key:
            project_key.enabled = is_aws
            project_key.filter.list = []

        if staging_folder:
            staging_folder.enabled = True

        # Seed raw bucket from config (lightweight)
        if is_aws and raw_s3_bucket and not raw_s3_bucket.valueAsText:
            try:
                cfg = ConfigManager.from_file(
                    path=config_file.valueAsText if config_file and config_file.valueAsText else None,
                    project_base=project_folder.valueAsText if project_folder and project_folder.valueAsText else None,
                    messages=None,
                )
                default_raw = cfg.get("aws.s3_bucket_raw", cfg.get("aws.s3_bucket")) if cfg else None
                if default_raw:
                    raw_s3_bucket.value = default_raw
            except Exception:
                pass

        # 2) Populate AWS Project Key dropdown
        if is_aws and raw_s3_bucket and raw_s3_bucket.valueAsText and project_key:
            try:
                project_key.filter.list = list_projects(raw_s3_bucket.valueAsText.strip())
            except Exception:
                pass

        # 3) Populate Reels multiselect
        if reels_param:
            reels_param.filter.list = []
            if not is_aws:
                base = project_folder.valueAsText if project_folder else None
                try:
                    if base and self.os_mod.path.isdir(base):
                        reels_root = self.os_mod.path.join(base, "reels")
                        if self.os_mod.path.isdir(reels_root):
                            names = [
                                d
                                for d in self.os_mod.listdir(reels_root)
                                if self.os_mod.path.isdir(self.os_mod.path.join(reels_root, d))
                            ]
                            reels_param.filter.list = sorted(names)
                except Exception:
                    reels_param.filter.list = []
            else:
                try:
                    bucket = raw_s3_bucket.valueAsText.strip() if raw_s3_bucket and raw_s3_bucket.valueAsText else ""
                    proj = project_key.valueAsText.strip().strip("/") if project_key and project_key.valueAsText else ""
                    if bucket and proj:
                        reels_param.filter.list = list_reels(bucket, proj)
                except Exception:
                    reels_param.filter.list = []

        # 4) Start step → OID in/out enablement
        if start_step:
            step_label = start_step.valueAsText
            step_name = self._step_label_to_name.get(step_label, "") if step_label and step_label != "--SELECT STEP--" else ""
            if step_name in ("run_mosaic_processor", "create_oid"):
                if oid_in:
                    oid_in.enabled = False
                    oid_in.value = None
                if oid_out:
                    oid_out.enabled = True
            elif step_name:
                if oid_in:
                    oid_in.enabled = True
                if oid_out:
                    oid_out.enabled = False
                    oid_out.value = None
            else:
                if oid_in:
                    oid_in.enabled = False
                    oid_in.value = None
                if oid_out:
                    oid_out.enabled = False
                    oid_out.value = None

        # 5) Linear Ref vs Smooth GPS → Centerline/Route gating
        linear_ref_enabled = bool(getattr(enable_linear_ref, "value", False))
        smooth_gps_enabled = bool(getattr(enable_smooth_gps, "value", False))

        if linear_ref_enabled:
            if centerline_param:
                centerline_param.enabled = True
                centerline_param.parameterType = "Required"
            if route_id_param:
                route_id_param.enabled = True
                route_id_param.parameterType = "Required"
        elif smooth_gps_enabled:
            if centerline_param:
                centerline_param.enabled = True
                centerline_param.parameterType = "Optional"
            if route_id_param:
                route_id_param.enabled = False
                route_id_param.parameterType = "Optional"
                route_id_param.value = None
        else:
            if centerline_param:
                centerline_param.enabled = False
                centerline_param.parameterType = "Optional"
                centerline_param.value = None
            if route_id_param:
                route_id_param.enabled = False
                route_id_param.parameterType = "Optional"
                route_id_param.value = None

        # 6) Copy to AWS → (Deploy Lambda / Generate Service) gating
        if enable_copy_to_aws and not bool(enable_copy_to_aws.value):
            if enable_deploy_lambda_monitor:
                enable_deploy_lambda_monitor.enabled = False
                enable_deploy_lambda_monitor.value = False
            if enable_generate_service:
                enable_generate_service.enabled = False
                enable_generate_service.value = False
        else:
            if enable_deploy_lambda_monitor:
                enable_deploy_lambda_monitor.enabled = True
            if enable_generate_service:
                enable_generate_service.enabled = True

    def updateMessages(self, parameters):
        """
        Validate parameters and surface helpful guidance (name-based; no index math).
        - Start step & OID input/output checks
        - Local vs AWS source checks (project folder / raw bucket / project key)
        - Centerline/Route ID checks based on Linear Ref / Smooth GPS toggles
        - Non-blocking info when no reels are selected (we'll process ALL)
        """
        p = {param.name: param for param in parameters}

        if not hasattr(self, "_step_label_to_name") or not hasattr(self, "_step_name_to_label"):
            self._step_label_to_name = {label: name for _, name, label in self.STEP_FUNCTIONS}
            self._step_name_to_label = {name: label for _, name, label in self.STEP_FUNCTIONS}

        # Shorthands
        source_mode = p.get("source_mode")
        project_folder = p.get("project_folder")
        raw_s3_bucket = p.get("raw_s3_bucket")
        project_key = p.get("project_key")
        reels_param = p.get("reels_to_process")

        start_step_param = p.get("start_step")
        oid_in = p.get("oid_fc_input")
        oid_out = p.get("oid_fc_output")

        enable_linear_ref = p.get("enable_linear_ref")
        enable_smooth_gps = p.get("enable_smooth_gps")
        centerline_param = p.get("centerline_fc")
        route_id_param = p.get("route_id_field")

        # 1) Start step & OID messages
        step_label = start_step_param.valueAsText if start_step_param else None
        step = self._step_label_to_name.get(step_label, "") if step_label and step_label != "--SELECT STEP--" else ""

        if start_step_param:
            if step_label == "--SELECT STEP--":
                start_step_param.setErrorMessage("⚠️ Please select a valid Start Step before running.")
            else:
                start_step_param.clearMessage()

        if oid_in and oid_out:
            oid_in.clearMessage()
            oid_out.clearMessage()
            if step in ("run_mosaic_processor", "create_oid"):
                if not oid_out.valueAsText:
                    oid_out.setErrorMessage("⚠️ Please specify the output path for the new OID dataset.")
                oid_out.setWarningMessage("ℹ️ A new OID will be created or an existing one will be overwritten.")
            elif step:
                if not oid_in.valueAsText:
                    oid_in.setErrorMessage("⚠️ Please specify the existing OID dataset.")
                oid_in.setWarningMessage("ℹ️ The existing OID will be used and preserved.")

        # 2) Source Mode checks
        is_aws = (source_mode.valueAsText == "AWS") if source_mode and source_mode.valueAsText else False

        # Project Folder is always required
        if project_folder and not project_folder.valueAsText:
            project_folder.setErrorMessage("⚠️ Please specify the Project Folder.")
        else:
            project_folder.clearMessage()

        # Local nicety: warn if <project>\reels missing
        if project_folder and project_folder.valueAsText and (source_mode.valueAsText != "AWS"):
            try:
                reels_root = self.os_mod.path.join(project_folder.valueAsText, "reels")
                if not self.os_mod.path.isdir(reels_root):
                    project_folder.setWarningMessage("ℹ️ Expected folder '<project>\\reels' was not found.")
            except Exception:
                pass

        # AWS: require raw bucket and project key
        if is_aws:
            if raw_s3_bucket:
                if not (raw_s3_bucket.valueAsText and raw_s3_bucket.valueAsText.strip()):
                    raw_s3_bucket.setErrorMessage("⚠️ Please specify the Raw S3 Bucket (e.g., rmi-360-raw).")
                else:
                    raw_s3_bucket.clearMessage()
            if project_key:
                if not (project_key.valueAsText and project_key.valueAsText.strip()):
                    project_key.setErrorMessage("⚠️ Please select a Project Key from the Raw S3 Bucket.")
                else:
                    project_key.clearMessage()

        # Reels selection: non-blocking note (empty => ALL)
        if reels_param:
            reels_param.clearMessage()
            basics_ok = (not is_aws and bool(project_folder and project_folder.valueAsText)) or (
                is_aws and bool(raw_s3_bucket and raw_s3_bucket.valueAsText and project_key and project_key.valueAsText)
            )
            if basics_ok:
                selected = (reels_param.valueAsText or "").strip()
                if not selected:
                    reels_param.setWarningMessage("ℹ️ No reels selected — the tool will process ALL reels in the source.")

        # 3) Centerline / Route ID messages
        linear_ref_enabled = bool(getattr(enable_linear_ref, "value", False))
        smooth_gps_enabled = bool(getattr(enable_smooth_gps, "value", False))

        if centerline_param:
            centerline_param.clearMessage()
        if route_id_param:
            route_id_param.clearMessage()

        if linear_ref_enabled:
            if centerline_param and not centerline_param.valueAsText:
                centerline_param.setErrorMessage("⚠️ Centerline is required when Linear Referencing is enabled.")
            if route_id_param and not route_id_param.valueAsText:
                route_id_param.setErrorMessage("⚠️ Route ID is required when Linear Referencing is enabled.")

    def execute(self, parameters: list, messages: Any) -> None:
        """
        Orchestrates the end-to-end Mosaic 360 processing workflow, preparing a local reels workspace and executing the configured pipeline steps.
        
        This method:
        - Resolves and stages input reels into a local working folder (assigned to p["input_reels_folder"]) from either a Local project folder or an S3 bucket (AWS mode).
        - Loads and validates configuration, builds the ordered step functions, and runs the selected steps starting from the requested start step.
        - Maintains and updates a persistent JSON report (metrics, paths, reels summary), collects OID metrics, computes folder statistics, and records elapsed time.
        - Optionally generates an HTML report and uploads project artifacts to S3 if configured.
        
        Parameters:
            parameters (list): ArcPy tool parameter objects supplied by the calling tool UI; used to build the runtime parameter dictionary and control workflow behavior (e.g., source mode, project locations, selected reels, start step).
            messages (Any): ArcPy messages/logging object used for user feedback and logger integration.
        """

        # ----------- Helpers (local) -----------
        def _parse_multi(gp_param) -> List[str]:
            if not gp_param or not gp_param.valueAsText:
                return []
            return [s.strip() for s in str(gp_param.valueAsText).split(";") if s.strip()]

        # ----------- Map params by name -----------
        pmap = {param.name: param for param in parameters}

        # Build dict with typed booleans for enable_* flags
        p = self.parameters_to_dict(parameters)

        # Determine which OID path is active
        oid_in_param = pmap.get("oid_fc_input")
        oid_out_param = pmap.get("oid_fc_output")
        if oid_out_param and oid_out_param.enabled:
            p["oid_fc"] = oid_out_param.valueAsText
        else:
            p["oid_fc"] = oid_in_param.valueAsText if oid_in_param else None

        generate_report_flag = bool(p.get("generate_report", True))

        # ----------- Load config, logger, paths -----------
        cfg = ConfigManager.from_file(
            path=p.get("config_file"),
            project_base=(pmap.get("project_folder").valueAsText if pmap.get("project_folder") else None),
            messages=messages,
        )
        logger = cfg.get_logger(messages)
        paths = cfg.paths

        # --- Runtime roots & project directory ---
        local_root = cfg.get("runtime.local_root")
        if not local_root:
            raise ValueError(
                "Missing 'runtime.local_root' in configuration. "
                "Specify it in config.yaml or set the RMI_LOCAL_ROOT environment variable."
            )

        # New structure: D:/Process360_Data/projects/{project_key}/
        project_key_value = cfg.get("project.slug", "project")
        project_dir = Path(local_root) / "projects" / project_key_value
        project_dir.mkdir(parents=True, exist_ok=True)

        # Resolve staging location and reels root under project directory
        staging_override = (
            Path(pmap["staging_folder"].valueAsText) if pmap.get("staging_folder") and pmap["staging_folder"].valueAsText else None
        )
        work_project_dir = staging_override if staging_override else project_dir  # .../projects/<slug>
        reels_root = work_project_dir / "reels"
        reels_root.mkdir(parents=True, exist_ok=True)

        # ----------- Resolve reels locally based on Source Mode -----------
        source_mode = (pmap.get("source_mode").valueAsText if pmap.get("source_mode") else "Local") or "Local"
        selected_reels = _parse_multi(pmap.get("reels_to_process"))

        if source_mode == "Local":
            project_folder = pmap["project_folder"].valueAsText if pmap.get("project_folder") else None
            if not project_folder:
                logger.error("Project Folder is required for Local mode.", indent=1)
                return

            project_reels = Path(project_folder) / "reels"
            if not project_reels.is_dir():
                logger.error(f"Local reels folder not found: {project_reels}", indent=1)
                return

            if selected_reels:
                for r in selected_reels:
                    src = project_reels / r
                    dst = reels_root / r
                    if not src.is_dir():
                        logger.warning(f"Skipping missing reel folder: {src}", indent=1)
                        continue
                    self._symlink_or_copy(src, dst, logger=logger)
            else:
                # No selection → include all subfolders in <project>\reels
                for name in os.listdir(project_reels):
                    src = project_reels / name
                    if src.is_dir():
                        dst = reels_root / name
                        self._symlink_or_copy(src, dst, logger=logger)

            # Downstream expects a local folder that CONTAINS reel folders
            p["input_reels_folder"] = str(reels_root)

        else:  # AWS
            raw_s3_bucket = (pmap.get("raw_s3_bucket").valueAsText if pmap.get("raw_s3_bucket") else None) or cfg.get(
                "aws.s3_bucket_raw", cfg.get("aws.s3_bucket")
            )
            project_key = (pmap.get("project_key").valueAsText if pmap.get("project_key") else None)
            if not raw_s3_bucket or not project_key:
                logger.error("Raw S3 Bucket and Project Key are required for AWS mode.", indent=1)
                return

            logger.info(f"Staging reels from s3://{raw_s3_bucket}/{project_key}/reels/ → {work_project_dir}", indent=1)
            staged_root = stage_reels(
                bucket=raw_s3_bucket,
                project_key=project_key.strip().strip("/"),
                reels=selected_reels or None,  # None => all reels
                local_project_dir=work_project_dir,  # ensures projects/<slug>/reels/<reel>/...
                max_workers=16,
                skip_if_exists=True,  # don't re-download existing files
            )

            # stage_reels returns <local_project_dir>/reels
            p["input_reels_folder"] = str(staged_root)

        # ----------- Orchestrator flow -----------
        logger.custom("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~", indent=0, emoji="🚀")
        logger.custom("| --- Starting Mosaic 360 Workflow --- |", indent=0, emoji="🚀")
        logger.custom("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~", indent=0, emoji="🚀")
        logger.info(f"Using config: {cfg.source_path}", indent=1)
        logger.info(f"Project root: {cfg.get('__project_root__')}", indent=1)

        if not p.get("oid_fc"):
            logger.error("OID dataset not specified; cannot continue.", indent=1)
            return

        # Validate config
        cfg.validate()

        # Build steps + order
        step_funcs = self.build_step_funcs_fn(p, cfg)
        step_order = self.get_step_order_fn(step_funcs)

        # Initialize or load report data
        report_data = self.load_report_json_if_exists_fn(cfg)
        if report_data is None:
            report_data = self.initialize_report_data_fn(p, cfg)
            self.save_report_json_fn(report_data, cfg)
        else:
            logger.custom("Loaded existing report JSON — appending new steps", indent=1, emoji="🔄")

        # Run steps
        t_start = self.time_mod.time()
        if not hasattr(self, "_step_label_to_name") or not hasattr(self, "_step_name_to_label"):
            self._step_label_to_name = {label: name for _, name, label in self.STEP_FUNCTIONS}
            self._step_name_to_label = {name: label for _, name, label in self.STEP_FUNCTIONS}

        step_label = p.get("start_step")
        start_step = (
            self._step_label_to_name.get(step_label, step_order[0]) if step_label and step_label != "--SELECT STEP--" else step_order[0]
        )
        if start_step not in step_order:
            logger.warning(f"Invalid start_step '{start_step}' provided. Falling back to default '{step_order[0]}'.", indent=1)
            start_step = step_order[0]
        start_index = step_order.index(start_step)

        wait_config = cfg.get("orchestrator", {})
        self.run_steps_fn(step_funcs, step_order, start_index, p, report_data, cfg, wait_config=wait_config)

        # Post-run: OID path, metrics, reel count, folder stats
        try:
            report_data.setdefault("paths", {})["oid_gdb"] = self.arcpy_mod.Describe(p["oid_fc"]).path
        except Exception as e:
            logger.warning(f"Could not describe OID FC yet: {e}", indent=1)
            report_data.setdefault("paths", {})["oid_gdb"] = "Unavailable"

        try:
            raw_metrics = self.collect_oid_metrics_fn(p["oid_fc"])
            summary, reels = self.summarize_oid_metrics_fn(raw_metrics)
            report_data["metrics"].update(summary)
            report_data["reels"] = reels
        except Exception as e:
            logger.warning(f"Could not gather OID stats: {e}", indent=1)

        # Count reel folders under the resolved local input path
        try:
            reel_folders = [
                f
                for f in self.os_mod.listdir(p["input_reels_folder"])
                if self.os_mod.path.isdir(self.os_mod.path.join(p["input_reels_folder"], f))
            ]
            report_data["metrics"]["reel_count"] = len(reel_folders)
        except Exception as e:
            report_data["metrics"]["reel_count"] = "—"
            logger.warning(f"Failed to count reel folders: {e}", indent=1)

        # Folder stats, elapsed, report generation
        try:
            self._compute_and_store_folder_stats(["original", "renamed"], paths, report_data, logger)
        except Exception as e:
            logger.warning(f"Failed to compute folder stats: {e}", indent=1)
        elapsed_total = self.time_mod.time() - t_start
        report_data["metrics"]["elapsed"] = f"{elapsed_total:.1f} sec"
        total_images = report_data["metrics"].get("total_images", 0)
        if total_images:
            report_data["metrics"]["time_per_image"] = f"{elapsed_total / total_images:.2f} sec/image"

        report_dir = paths.report
        report_data["paths"]["report_dir"] = str(report_dir)
        self.save_report_json_fn(report_data, cfg)

        if generate_report_flag:
            try:
                report_data["config"] = cfg.raw
                slug = cfg.get("project.slug", "unknown")
                json_path = self.os_mod.path.join(paths.report, f"report_data_{slug}.json")
                self.generate_report_from_json_fn(json_path=json_path, cfg=cfg)
                logger.custom(f"Final report and JSON saved to: {report_dir}", indent=1, emoji="📄")
                logger.export_html()
            except Exception as e:
                logger.warning(f"Report generation failed: {e}", indent=1)
        else:
            logger.custom("Skipping report generation (disabled by user)", indent=1, emoji="⏭️")

        # --- Upload artifacts to S3 (optional) ---
        upload_artifacts = cfg.get("orchestrator.upload_artifacts_to_s3", False)
        if upload_artifacts:
            try:
                from utils.shared.backup_to_s3 import upload_project_artifacts
                artifact_types = cfg.get("orchestrator.artifact_types", ['config', 'logs', 'report'])
                timestamp = self.time_mod.strftime("%Y%m%d_%H%M")
                logger.custom("Uploading project artifacts to S3 for backup...", indent=1, emoji="📤")
                results = upload_project_artifacts(cfg, artifact_types=artifact_types, timestamp=timestamp, logger=logger)
                if results:
                    logger.custom(f"Artifacts uploaded: {', '.join(results.keys())}", indent=1, emoji="✅")
            except Exception as e:
                logger.warning(f"Failed to upload artifacts to S3: {e}", indent=1)

        logger.custom("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~", indent=0, emoji="🎉")
        logger.custom("| --- Mosaic 360 Workflow Complete --- |", indent=0, emoji="🎉")
        logger.custom("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~", indent=0, emoji="🎉")