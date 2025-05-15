# =============================================================================
# 🧰 Process Full Mosaic 360 Workflow (tools/process_360_orchestrator.py)
# -----------------------------------------------------------------------------
# Tool Name:          Process360Workflow
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.1.0
# Author:             RMI Valuation, LLC
# Created:            2025-05-08
# Last Updated:       2025-05-15
#
# Description:
#   Orchestrates the full end-to-end Mosaic 360 image processing pipeline within ArcGIS Pro.
#   Executes a configurable series of steps, including image rendering, OID creation, image
#   enrichment, geolocation, cloud upload, and service publishing. Tracks progress and logs
#   results to a persistent report JSON for dashboard and reporting use. Integrates with Core Utils
#   for all workflow, configuration, and reporting steps.
#
# File Location:      /tools/process_360_orchestrator.py
# Core Utils:
#   - utils/build_step_funcs.py
#   - utils/step_runner.py
#   - utils/generate_report.py
#   - utils/manager/config_manager.py
#   - utils/shared/report_data_builder.py
#   - utils/shared/folder_stats.py
#   - utils/shared/gather_metrics.py
#   - utils/shared/arcpy_utils.py
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/process_360_orchestrator.md
#   (Ensure these docs are current; update if needed.)
#
# Parameters:
#   - Start From Step (Optional) {start_step} (String): Step label to start from. Skips earlier steps if selected.
#   - Project Folder {project_folder} (Folder): Root folder for the current 360 image processing project.
#   - Input Reels Folder {input_reels_folder} (Folder): Directory containing raw .mp4 reel folders from Mosaic camera.
#   - OID Dataset - Input {oid_fc_input} (Feature Class): Existing OID to update (used in most steps).
#   - OID Dataset - Output {oid_fc_output} (Feature Class): Output feature class (used only when creating a new OID).
#   - Centerline (M-enabled) {centerline_fc} (Feature Class): Required polyline for GPS smoothing and referencing.
#   - Route ID Field {route_id_field} (Field): Field in centerline used to identify routes for linear referencing.
#   - Enable Linear Referencing {enable_linear_ref} (Boolean): Whether to compute MP and Route ID values per image.
#   - Skip Enhance Images? {skip_enhance_images} (Boolean): If true, skips image enhancement even if config is enabled.
#   - Copy Processed Images to AWS S3? {copy_to_aws} (Boolean): Whether to trigger the AWS upload step.
#   - Custom Config File {config_file} (File): Optional override for default config.yaml path.
#   - Generate HTML Summary Report? {generate_report} (Boolean): Whether to generate a visual summary at the end.
#
# Notes:
#   - Uses a step dispatcher to execute ordered functions defined in build_step_funcs.
#   - Skipped steps are safely logged and retained in the report JSON.
#   - Can resume from an existing report if rerun on the same project.
#   - Ensure all Core Utils and config files are up-to-date for workflow success.
# =============================================================================

import arcpy
import time
import os
from typing import Optional, Any, Callable, Dict, List

from utils.manager.config_manager import ConfigManager
from utils.shared.arcpy_utils import str_to_bool
from utils.generate_report import generate_report_from_json
from utils.step_runner import run_steps
from utils.build_step_funcs import build_step_funcs, get_step_order
from utils.shared.gather_metrics import collect_oid_metrics, summarize_oid_metrics
from utils.shared.folder_stats import folder_stats
from utils.shared.report_data_builder import initialize_report_data, save_report_json, load_report_json_if_exists


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
        generate_report_from_json_fn: Optional[Callable] = None
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
        """
        return {param.name: param.valueAsText for param in parameters}

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
        "4) Smooth GPS Noise\n"
        "5) Update Linear and Custom Attributes\n"
        "6) Rename and Tag\n"
        "7) Geocode Images (optional)\n"
        "8) Create OID Footprints\n"
        "9) Copy to AWS (optional)\n"
        "10) Generate OID Service (optional)"
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
        (9, "enhance_images", "Enhance Images"),
        (10, "rename_images", "Rename Images"),
        (11, "update_metadata", "Update EXIF Metadata"),
        (12, "geocode", "Geocode Images"),
        (13, "build_footprints", "Build OID Footprints"),
        (14, "deploy_lambda_monitor", "Deploy Lambda Monitor"),
        (15, "copy_to_aws", "Upload to AWS S3"),
        (16, "generate_service", "Generate OID Service")
    ]

    # Sort by numeric index and extract step names in the correct order
    STEP_ORDER = [step[1] for step in sorted(STEP_FUNCTIONS, key=lambda x: x[0])]

    def getParameterInfo(self):
        """
        Defines and returns the list of ArcPy parameters for the Mosaic 360 workflow tool.
        
        The parameters include options for selecting the workflow start step, specifying project and input folders,
        input and output Oriented Imagery Dataset (OID) feature classes, centerline and route ID fields, and toggles
        for linear referencing, image enhancement, AWS upload, custom configuration, and report generation. Parameter
        defaults, filters, and dependencies are set to guide user input in the ArcGIS interface.
        """
        params = []

        start_step_param = arcpy.Parameter(
            displayName="Start From Step (Optional)",
            name="start_step",
            datatype="GPString",
            parameterType="Optional",
            direction="Input"
        )
        start_step_param.filter.list = ["--SELECT STEP--"] + self.STEP_ORDER
        start_step_param.value = "--SELECT STEP--"
        params.append(start_step_param)

        project_folder_param = arcpy.Parameter(
            displayName="Project Folder",
            name="project_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input"
        )
        params.append(project_folder_param)

        input_reels_folder_param = arcpy.Parameter(
            displayName="Input Reels Folder",
            name="input_reels_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input"
        )
        params.append(input_reels_folder_param)

        oid_fc_input_param = arcpy.Parameter(
            displayName="OID Dataset - Input (used in most steps)",
            name="oid_fc_input",
            datatype="DEFeatureClass",
            parameterType="Optional",
            direction="Input"
        )
        oid_fc_input_param.enabled = False
        params.append(oid_fc_input_param)

        oid_fc_output_param = arcpy.Parameter(
            displayName="OID Dataset - Output (used only for 'Run Mosaic Processor' or 'Create OID')",
            name="oid_fc_output",
            datatype="DEFeatureClass",
            parameterType="Optional",
            direction="Output"
        )
        oid_fc_output_param.enabled = False
        params.append(oid_fc_output_param)

        centerline_param = arcpy.Parameter(
            displayName="Centerline (M-enabled, used for GPS smoothing and linear referencing)",
            name="centerline_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        centerline_param.filter.list = ["Polyline"]
        params.append(centerline_param)

        route_id_param = arcpy.Parameter(
            displayName="Route ID Field",
            name="route_id_field",
            datatype="Field",
            parameterType="Required",
            direction="Input"
        )
        route_id_param.parameterDependencies = [centerline_param.name]
        route_id_param.filter.list = ["Short", "Long", "Text"]
        params.append(route_id_param)

        enable_lr_param = arcpy.Parameter(
            displayName="Enable Linear Referencing",
            name="enable_linear_ref",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        enable_lr_param.value = True
        params.append(enable_lr_param)

        skip_enhance_param = arcpy.Parameter(
            displayName="Skip Enhance Images?",
            name="skip_enhance_images",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        skip_enhance_param.value = False
        params.append(skip_enhance_param)

        copy_to_aws_param = arcpy.Parameter(
            displayName="Copy Processed Images to AWS S3?",
            name="copy_to_aws",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        copy_to_aws_param.value = True
        params.append(copy_to_aws_param)

        config_param = arcpy.Parameter(
            displayName="Custom Config File (Leave blank to use default config.yaml)",
            name="config_file",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input"
        )
        params.append(config_param)

        generate_report_param = arcpy.Parameter(
            displayName="Generate HTML Summary Report?",
            name="generate_report",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        generate_report_param.value = True
        params.append(generate_report_param)

        return params

    def updateParameters(self, parameters):
        """
        Dynamically enables or disables OID input and output parameters based on the selected start step.
        
        If the start step is "run_mosaic_processor" or "create_oid", enables the output OID parameter and disables the
        input OID parameter; otherwise, enables the input OID parameter and disables the output OID parameter. Clears
        the value of any parameter that is disabled.
        """
        start_step_param = parameters[0]  # Start step param
        oid_in = parameters[3]  # oid_fc_input
        oid_out = parameters[4]  # oid_fc_output

        if start_step_param.altered:
            step = start_step_param.valueAsText

            # Treat placeholder as "no selection"
            if step == "--SELECT STEP--":
                step = ""

            if step in ("run_mosaic_processor", "create_oid"):
                oid_in.enabled = False
                oid_out.enabled = True
            elif step:
                oid_in.enabled = True
                oid_out.enabled = False
            else:
                oid_in.enabled = False
                oid_out.enabled = False

            oid_in.value = None if not oid_in.enabled else oid_in.value
            oid_out.value = None if not oid_out.enabled else oid_out.value

    def updateMessages(self, parameters):
        """
        Validates workflow parameters and sets error or warning messages for user guidance.
        
        Checks the selected start step and OID dataset parameters, displaying appropriate
        messages if required values are missing or if existing data may be overwritten or reused.
        """
        start_step_param = parameters[0]
        oid_in = parameters[3]
        oid_out = parameters[4]

        start_step = start_step_param.valueAsText

        if start_step == "--SELECT STEP--":
            start_step_param.setErrorMessage("⚠️ Please select a valid Start Step before running.")
        elif start_step in ("run_mosaic_processor", "create_oid"):
            oid_out.setWarningMessage("⚠️ Existing OID will be overwritten if it exists.")
        else:
            oid_in.setWarningMessage("ℹ️ Existing OID will be used and preserved.")

        if oid_in.enabled and not oid_in.valueAsText:
            oid_in.setErrorMessage("⚠️ Please specify the existing OID dataset.")
        elif oid_out.enabled and not oid_out.valueAsText:
            oid_out.setErrorMessage("⚠️ Please specify the output path for the new OID dataset.")

    def execute(self, parameters: list, messages: Any) -> None:
        """
        Executes the full Mosaic 360 image processing workflow and generates reports.
        Allows dependency injection for testability. Compatible with ArcGIS Pro GUI.
        """
        # Map parameters to dict
        p = self.parameters_to_dict(parameters)
        # Determine which OID param was enabled and populate p["oid_fc"]
        if parameters[4].enabled:
            p["oid_fc"] = parameters[4].valueAsText  # oid_fc_output
        else:
            p["oid_fc"] = parameters[3].valueAsText  # oid_fc_input

        generate_report_flag = str_to_bool(p.get("generate_report", "true"))

        cfg = ConfigManager.from_file(
            path=p.get("config_file"),
            project_base=p["project_folder"],
            messages=messages,
        )
        logger = cfg.get_logger(messages)
        paths = cfg.paths

        if cfg.get("debug_messages", False):
            logger.debug("🔍 Debug mode enabled from config")

        cfg.validate()

        logger.info("--- Starting Mosaic 360 Workflow ---")
        logger.debug(f"Using config: {cfg.source_path}")
        logger.debug(f"Project root: {cfg.get('__project_root__')}")

        # Build steps + order
        step_funcs = self.build_step_funcs_fn(p, cfg)
        step_order = self.get_step_order_fn(step_funcs)

        # Initialize report data
        report_data = self.load_report_json_if_exists_fn(cfg)
        if report_data is None:
            report_data = self.initialize_report_data_fn(p, cfg)
            self.save_report_json_fn(report_data, cfg)
        else:
            logger.info("🔁 Loaded existing report JSON — appending new steps")

        # Execute steps and capture results
        t_start = self.time_mod.time()
        start_step = p.get("start_step") or step_order[0]
        if start_step not in step_order:
            logger.warning(f"Invalid start_step '{start_step}' provided. Falling back to default '{step_order[0]}'.")
            start_step = step_order[0]
        start_index = step_order.index(start_step)

        wait_config = cfg.get("orchestrator", {})
        self.run_steps_fn(step_funcs, step_order, start_index, p, report_data, cfg, wait_config=wait_config)

        # After the OID has been created (via run_steps), describe its GDB path
        try:
            report_data.setdefault("paths", {})["oid_gdb"] = self.arcpy_mod.Describe(p["oid_fc"]).path
        except Exception as e:
            logger.warning(f"Could not describe OID FC yet: {e}")
            report_data.setdefault("paths", {})["oid_gdb"] = "Unavailable"

        # OID-based metrics
        try:
            raw_metrics = self.collect_oid_metrics_fn(p["oid_fc"])
            summary, reels = self.summarize_oid_metrics_fn(raw_metrics)
            report_data["metrics"].update(summary)
            report_data["reels"] = reels
        except Exception as e:
            logger.warning(f"Could not gather OID stats: {e}")

        # Reel folder count
        try:
            reel_folders = [f for f in self.os_mod.listdir(p["input_reels_folder"]) if
                            self.os_mod.path.isdir(self.os_mod.path.join(p["input_reels_folder"], f))]
            report_data["metrics"]["reel_count"] = len(reel_folders)
        except Exception as e:
            report_data["metrics"]["reel_count"] = "—"
            logger.warning(f"Failed to count reel folders: {e}")

        # Folder stats for original/enhanced/renamed
        self._compute_and_store_folder_stats(["original", "enhanced", "renamed"], paths, report_data, logger)

        # Elapsed time
        elapsed_total = self.time_mod.time() - t_start
        report_data["metrics"]["elapsed"] = f"{elapsed_total:.1f} sec"
        total_images = report_data["metrics"].get("total_images", 0)
        if total_images:
            report_data["metrics"]["time_per_image"] = f"{elapsed_total / total_images:.2f} sec/image"

        # Determine report output folder
        report_dir = paths.report
        report_data["paths"]["report_dir"] = str(report_dir)

        # Save report data to JSON for future recovery/report generation
        self.save_report_json_fn(report_data, cfg)

        if generate_report_flag:
            try:
                report_data["config"] = cfg
                slug = cfg.get("project.slug", "unknown")
                json_path = self.os_mod.path.join(paths.report, f"report_data_{slug}.json")

                self.generate_report_from_json_fn(
                    json_path=json_path,
                    cfg=cfg
                )
                logger.info(f"📄 Final report and JSON saved to: {report_dir}")
            except Exception as e:
                logger.warning(f"Report generation failed: {e}")
        else:
            logger.info("⏭️ Skipping report generation (disabled by user)")

        logger.info("--- Mosaic 360 Workflow Complete ---")
