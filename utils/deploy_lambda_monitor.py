# =============================================================================
# 📡 AWS Lambda Deployment Logic (utils/deploy_lambda_monitor.py)
# -----------------------------------------------------------------------------
# Purpose:             Deploys Lambda functions and schedules upload monitor for 360° image tracking
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Deploys and configures AWS Lambda functions for monitoring upload progress to S3. Sets up a CloudWatch
#   Events schedule to invoke the monitoring Lambda every 5 minutes. Initializes a project-specific progress
#   JSON file and verifies credentials via boto3. Uses keyring or fallback credentials defined in the config.
#
# File Location:        /utils/deploy_lambda_monitor.py
# Called By:            tools/copy_to_aws_tool.py, tools/process_360_orchestrator.py
# Int. Dependencies:    config_loader, expression_utils, arcpy_utils, aws_utils, path_resolver
# Ext. Dependencies:    boto3, botocore, json, zipfile, io, contextlib, datetime, typing
#
# Documentation:
#   See: docs/TOOL_GUIDES.md, docs/tools/copy_to_aws.md, and AWS_SETUP_GUIDE.md
#
# Notes:
#   - Deploys both progress monitor and auto-disable Lambda functions
#   - Configurable via standalone call or ArcGIS Python Toolbox wrapper
# =============================================================================

__all__ = ["deploy_lambda_monitor"]

import json
import zipfile
import io
import contextlib
from typing import Optional, Any
from datetime import datetime, timezone
from pathlib import Path
from boto3 import Session

from utils.expression_utils import resolve_expression
from utils.arcpy_utils import log_message
from utils.path_resolver import resolve_relative_to_pyt
from utils.config_loader import resolve_config
from utils.aws_utils import get_aws_credentials

# -- Constants for source files --
# Defer resolution until inside main()
PROGRESS_MONITOR_REL_PATH = "aws_lambdas/lambda_progress_monitor.py"
DEACTIVATOR_REL_PATH = "aws_lambdas/disable_rule.py"


def zip_lambda(source_path: str, arcname: str) -> bytes:
    """
    Packages a Python source file into an in-memory ZIP archive.
    
    Args:
        source_path: Path to the source file to be zipped.
        arcname: Name to assign to the file within the ZIP archive.
    
    Returns:
        The bytes of the ZIP archive containing the source file.
    
    Raises:
        FileNotFoundError: If the specified source file does not exist.
    """
    path = Path(source_path)

    if not path.is_file():
        raise FileNotFoundError(f"Lambda file not found: {path}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(arcname, path.read_bytes())

    buf.seek(0)
    return buf.read()


def count_final_images(config):
    """
    Counts the number of JPEG images in the final output folder specified by the config.
    
    Raises:
        ValueError: If the project root is missing from the config.
    
    Returns:
        The number of `.jpg` files found in the resolved final image output folder, or 0 if the folder does not exist.
    """
    parent = resolve_expression("config.image_output.folders.parent", config)
    renamed = resolve_expression("config.image_output.folders.renamed", config)

    root = config.get("__project_root__")
    if not root:
        raise ValueError("Missing __project_root__ in config — cannot locate image folder.")

    final_folder = Path(root) / parent / renamed

    if not final_folder.exists():
        log_message(f"⚠️ Final folder does not exist: {final_folder}", level="warning")
        return 0

    try:
        image_files = [f for f in final_folder.rglob("*") if f.suffix.lower() in [".jpg", ".jpeg"]]
        count = len(image_files)
        log_message(f"Found {count} JPEG images in {final_folder}", level="info")
        return count
    except Exception as e:
        log_message(f"Error counting images: {e}", level="warning")
        return 0


def build_progress_json(config, expected_total):
    """
    Builds a JSON-compatible dictionary representing the initial upload progress status.
    
    Args:
        config: Project configuration dictionary containing project, camera, and AWS details.
        expected_total: The expected total number of images to be uploaded.
    
    Returns:
        A dictionary with project, camera, and cloud metadata, timestamps, and initial progress metrics for upload
        monitoring.
    """
    now = datetime.now(timezone.utc)
    project_info = {
        "number": config["project"]["number"],
        "slug": config["project"]["slug"],
        "client": config["project"]["client"],
        "railroad_name": config["project"]["rr_name"],
        "railroad_code": config["project"]["rr_mark"],
        "description": config["project"]["description"]
    }

    camera_info = {
        "make": config["camera"]["make"],
        "model": config["camera"]["model"],
        "serial_number": config["camera"]["sn"],
        "firmware": config["camera"]["firmware"],
        "software": config["camera"]["software"]
    }

    cloud_info = {
        "bucket": config["aws"]["s3_bucket"],
        "prefix": resolve_expression(config["aws"]["s3_bucket_folder"], config),
        "region": config["aws"]["region"]
    }

    return {
        "project_slug": config["project"]["slug"],
        "last_updated": now.isoformat(),
        "start_time": now.isoformat(),
        "end_time": None,
        "upload_status": "In Progress",
        "stalls": 0,
        "count": 0,
        "expected_total": expected_total,
        "percent_complete": 0.0,
        "avg_time_per_image": None,
        "project_info": project_info,
        "camera_info": camera_info,
        "cloud_info": cloud_info
    }


def upload_progress_json(s3_client, progress, bucket, slug, messages):
    """
    Uploads the progress status JSON to an S3 bucket under the 'status/' prefix.
    
    Args:
        s3_client: A boto3 S3 client used to perform the upload.
        progress: The progress status dictionary to upload.
        bucket: The name of the S3 bucket.
        slug: Project slug used to generate the filename.
        messages: List to append log messages to.
    """
    filename = f"progress_{slug}.json"
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=f"status/{filename}",
            Body=json.dumps(progress, indent=2).encode("utf-8"),
            ContentType="application/json"
        )
        log_message(f"✅ Uploaded {filename} to s3://{bucket}/status/", messages)
    except Exception as e:
        log_message(f"❌ Failed to upload progress JSON: {e}", messages, level="error")


def ensure_lambda_progress_monitor(lambda_client, role_arn, messages):
    """
    Ensures the 'UploadProgressMonitor' Lambda function exists, deploying it if necessary.
    
    Checks for the existence of the 'UploadProgressMonitor' AWS Lambda function. If it does not exist, packages the
    source code and creates the Lambda function using the provided role ARN. Logs deployment status and raises a
    FileNotFoundError if the source file is missing.
    """
    name = "UploadProgressMonitor"
    handler = "lambda_progress_monitor.lambda_handler"

    try:
        lambda_client.get_function(FunctionName=name)
        log_message(f"✅ Lambda '{name}' already exists.", messages)
        return
    except lambda_client.exceptions.ResourceNotFoundException:
        log_message("🚀 Deploying UploadProgressMonitor Lambda...", messages)

    progress_monitor_path = resolve_relative_to_pyt(PROGRESS_MONITOR_REL_PATH)
    try:
        zipped = zip_lambda(progress_monitor_path, "lambda_progress_monitor.py")
    except FileNotFoundError as e:
        log_message(f"❌ Lambda zip failed: {e}", messages, level="error")
        raise
    lambda_client.create_function(
        FunctionName=name,
        Runtime="python3.9",
        Role=role_arn,
        Handler=handler,
        Code={"ZipFile": zipped},
        Timeout=90,
        MemorySize=256,
        Publish=True
    )
    log_message(f"✅ Lambda '{name}' deployed.", messages)


def ensure_lambda_deactivator(lambda_client, role_arn, messages):
    """
    Ensures the 'DisableUploadMonitorRule' Lambda function exists, deploying it if necessary.
    
    If the Lambda function does not exist, packages its source code and creates the function using the provided role
    ARN. Logs deployment status and raises FileNotFoundError if the source file is missing.
    """
    name = "DisableUploadMonitorRule"
    handler = "disable_rule.lambda_handler"

    try:
        lambda_client.get_function(FunctionName=name)
        log_message(f"✅ Lambda '{name}' already exists.", messages)
        return
    except lambda_client.exceptions.ResourceNotFoundException:
        log_message("🚀 Deploying DisableUploadMonitorRule Lambda...", messages)

    # 🔍 Resolve Lambda source files relative to config file
    deactivator_path = resolve_relative_to_pyt(DEACTIVATOR_REL_PATH)
    try:
        zipped = zip_lambda(deactivator_path, "disable_rule.py")
    except FileNotFoundError as e:
        log_message(f"❌ Lambda zip failed: {e}", messages, level="error")
        raise

    lambda_client.create_function(
        FunctionName=name,
        Runtime="python3.9",
        Role=role_arn,
        Handler=handler,
        Code={"ZipFile": zipped},
        Timeout=30,
        MemorySize=128,
        Publish=True
    )
    log_message(f"✅ Lambda '{name}' deployed.", messages)


def setup_schedule_and_target(events_client, lambda_client, config, expected_total, messages):
    """
    Creates or updates a CloudWatch Events rule to trigger the upload progress monitor Lambda.
    
    Configures a scheduled rule to invoke the "UploadProgressMonitor" Lambda function every 5 minutes, passing
    project-specific input parameters. Ensures the Lambda has the necessary permissions to be invoked by the event rule.
    """
    rule_name = "UploadProgressScheduleRule"
    target_lambda = "UploadProgressMonitor"

    rule_arn = events_client.put_rule(
        Name=rule_name,
        ScheduleExpression="rate(5 minutes)",
        State="ENABLED"
    )["RuleArn"]

    lambda_arn = lambda_client.get_function(FunctionName=target_lambda)["Configuration"]["FunctionArn"]

    project_config = {
        "project_slug": config["project"]["slug"],
        "bucket": config["aws"]["s3_bucket"],
        "prefix": f"{config['project']['number']}/",
        "expected_total": expected_total
    }

    events_client.put_targets(
        Rule=rule_name,
        Targets=[{
            "Id": "UploadProgressTarget",
            "Arn": lambda_arn,
            "Input": json.dumps(project_config)
        }]
    )

    with contextlib.suppress(lambda_client.exceptions.ResourceConflictException):
        lambda_client.add_permission(
            FunctionName=target_lambda,
            StatementId="AllowEventsInvokeUploadProgress",
            Action="lambda:InvokeFunction",
            Principal="events.amazonaws.com",
            SourceArn=rule_arn
        )

    log_message(f"✅ CloudWatch rule '{rule_name}' updated with target input.", messages, config=config)


# 🎯 Main entrypoint
def deploy_lambda_monitor(config: Optional[dict] = None, config_file: Optional[str] = None, messages: Optional[Any] = None):
    """
    Deploys and configures AWS Lambda functions and resources for monitoring image upload progress.

    Resolves configuration, counts final images, builds and uploads initial progress status to S3, ensures required
    Lambda functions are deployed, and sets up a scheduled CloudWatch Events rule to trigger progress monitoring.
    Logs key steps and warnings throughout the process.

    Args:
        config: Optional configuration dictionary. If not provided, config_file is used.
        config_file: Optional path to a configuration file. Used if config is not provided.
        messages: Optional list to collect log messages.
    """
    if messages is None:
        messages = []

    config = resolve_config(config=config, config_file=config_file, tool_name="deploy_lambda_monitor")

    region = config["aws"]["region"]
    role_arn = config["aws"]["lambda_role_arn"]
    slug = config["project"]["slug"]
    bucket = config["aws"]["s3_bucket"]

    # Load credentials from keyring or config and verify AWS credentials
    try:
        access_key, secret_key = get_aws_credentials(config)
        session = Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        sts = session.client("sts")
        sts.get_caller_identity()
        log_message("✅ AWS credentials verified.", messages, config=config)
    except Exception as e:
        log_message(f"❌ AWS credentials verification failed: {e}", messages, level="error", config=config)
        return

    expected_total = count_final_images(config)
    log_message(f"📸 Found {expected_total} image(s) in final folder.", messages, config=config)

    if expected_total == 0:
        log_message("⚠️ expected_total is 0 — progress tracking will show 0% until images appear.", messages,
                    level="warning", config=config)

    progress = build_progress_json(config, expected_total)

    s3 = session.client("s3")
    lambda_client = session.client("lambda")
    events_client = session.client("events")

    upload_progress_json(s3, progress, bucket, slug, messages)
    ensure_lambda_progress_monitor(lambda_client, role_arn, messages)
    ensure_lambda_deactivator(lambda_client, role_arn, messages)
    setup_schedule_and_target(events_client, lambda_client, config, expected_total, messages)


# 🧪 CLI fallback
if __name__ == "__main__":
    from utils.config_loader import get_default_config_path
    log_message("🧪 Running deploy_lambda_monitor standalone...", [])
    deploy_lambda_monitor(config_file=get_default_config_path())
