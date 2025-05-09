# =============================================================================
# ☁️ Copy to AWS (tools/copy_to_aws_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          CopyToAwsTool
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
# Created:            2025-05-08
#
# Description:
#   Implements ArcPy Tool class for uploading enhanced or renamed images to AWS S3 using TransferManager.
#   Optionally deploys a Lambda-based monitor to track upload progress via CloudWatch Events.
#   Reads from a config YAML and supports skipping existing uploads, logging, and progress tracking.
#
# File Location:      /tools/copy_to_aws_tool.py
# Uses:
#   - utils/copy_to_aws.py
#   - utils/deploy_lambda_monitor.py
#   - utils/arcpy_utils.py
#   - utils/config_loader.py
#
# Documentation:
#   See: docs/TOOL_GUIDES.md and docs/tools/copy_to_aws.md
#
# Parameters:
#   - Input Folder for Images to be Uploaded {input_image_folder} (Folder): Directory containing images to upload to AWS S3.
#   - Skip Existing Files in S3? {skip_existing} (Boolean): If checked, skips files that already exist in the target S3 location.
#   - Config File {config_file} (File): Path to the project YAML config file with AWS and path settings.
#   - Project Folder {project_folder} (Folder): Root folder for the project; used for resolving logs and asset paths.
#   - Deploy Upload Monitor? {enable_monitor} (Boolean): Whether to deploy the AWS Lambda upload monitor before transfer.
#
# Notes:
#   - Supports optional Lambda monitor deployment before upload
#   - Skips re-uploading files already present in S3 if specified
#   - Uses resumable upload strategy with retry handling
# =============================================================================

import arcpy
from utils.deploy_lambda_monitor import deploy_lambda_monitor
from utils.copy_to_aws import copy_to_aws
from utils.arcpy_utils import str_to_bool, log_message
from utils.config_loader import get_default_config_path


class CopyToAwsTool:
    def __init__(self):
        self.label = "09 - Copy To AWS"
        self.description = "Uploads renamed and tagged images to AWS S3 using the project config."
        self.category = "Individual Tools"

    def getParameterInfo(self):
        """
        Defines the input parameters for the CopyToAwsTool ArcPy geoprocessing tool.
        
        Returns:
            A list of ArcPy Parameter objects specifying required and optional inputs for
            uploading images to AWS S3, including image folder, configuration file,
            project folder, and upload options.
        """
        params = []

        # Input folder with images to be exported
        in_image_folder = arcpy.Parameter(
            displayName="Input Folder for Images to be Uploaded",
            name="input_image_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input"
        )
        in_image_folder.description = "Folder where images to be uploaded to AWS are located."
        params.append(in_image_folder)

        # Skip uploading files to AWS if they already exist
        skip_exist_aws_param = arcpy.Parameter(
            displayName="Skip Existing Files in S3?",
            name="skip_existing",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        skip_exist_aws_param.value = False
        skip_exist_aws_param.description = "If checked, skips uploading files that already exist in S3."
        params.append(skip_exist_aws_param)

        # Config file
        config_param = arcpy.Parameter(
            displayName="Config File",
            name="config_file",
            datatype="DEFile",
            parameterType="Required",
            direction="Input"
        )
        config_param.description = "Config.yaml file containing project-specific settings."
        params.append(config_param)

        # (0) Project folder - Root folder for this Mosaic 360 imagery project. All imagery and logs will be organized
        # under this folder.
        project_param = arcpy.Parameter(
            displayName="Project Folder",
            name="project_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input"
        )
        params.append(project_param)

        enable_monitor = arcpy.Parameter(
            displayName="Deploy Upload Monitor?",
            name="enable_monitor",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        enable_monitor.value = True
        params.append(enable_monitor)

        return params

    def execute(self, parameters, messages):
        """
        Executes the tool to optionally deploy an AWS upload monitor and upload images to S3.
        
        Extracts user-specified parameters, deploys an AWS Lambda monitor if enabled, and uploads images from the
        specified local folder to AWS S3 using project configuration settings. Logs progress and errors, raising
        exceptions on failure.
        """
        p = {param.name: param.valueAsText for param in parameters}

        all_messages = []

        if str_to_bool(p.get("enable_monitor", "true")):
            try:
                log_message("Deploying AWS upload monitor...", messages)
                deploy_lambda_monitor(
                    config_file=p.get("config_file") or get_default_config_path(),
                    messages=messages
                )
            except Exception as e:
                log_message(f"Failed to deploy AWS Monitor: {str(e)}", messages, level="error", error_type=RuntimeError)
                raise

        try:
            log_message("📤 Starting AWS Upload...", messages)
            copy_to_aws(
                local_dir=p["input_image_folder"],
                skip_existing=str_to_bool(p.get("skip_existing")),
                config_file=p.get("config_file") or get_default_config_path(),
                project_folder=p["project_folder"],
                messages=messages
            )
        except Exception as e:
            log_message(f"❌ Upload failed: {str(e)}", messages, level="error", error_type=RuntimeError)
            raise

        for msg in all_messages:
            log_message(msg, messages)
