# =============================================================================
# ☁️ Copy to AWS Validator (utils/validators/copy_to_aws_validator.py)
# -----------------------------------------------------------------------------
# Purpose:             Validates AWS configuration for copying data to S3
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.1
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
# Last Updated:        2025-05-22
#
# Description:
#   Ensures presence and correctness of required AWS keys, validates types, and checks max_workers and S3 folder
#   configuration for compatibility with S3 upload workflows.
#
# File Location:        /utils/validators/copy_to_aws_validator.py
# Called By:            AWS S3 upload and sync tools
# Notes:                Used for validation of AWS credentials and S3 upload settings.
# =============================================================================

from typing import TYPE_CHECKING

import os
from utils.shared.rmi_exceptions import ConfigValidationError
from utils.validators.common_validators import (
    try_resolve_config_expression,
    validate_keys_with_types
)
from utils.validators.secured_storage_validator import validate_secured_storage_deployment

if TYPE_CHECKING:
    from utils.manager.config_manager import ConfigManager


def validate(cfg: "ConfigManager") -> bool:
    """
    Validates the AWS configuration section for the copy-to-AWS tool.

    Checks for required AWS keys and their types, validates optional keys if present, ensures `max_workers` is an
    integer or a valid expression, and verifies that `s3_bucket_folder` resolves to a string.

    Returns:
        bool: True if validation passes, False otherwise.
    """
    logger = cfg.get_logger()
    error_count = 0

    aws = cfg.get("aws", {})

    # ✅ Required keys
    required_keys = {
        "region": str,
        "s3_bucket_panos_unsecured": str,
        "s3_bucket_folder": str
    }

    error_count += validate_keys_with_types(cfg, aws, required_keys, "aws", required=True)

    # ✅ Optional keys
    optional_keys = {
        "s3_bucket_raw": str,
        "skip_existing": bool,
        "retries": int,
        "profile": str,                   # named AWS profile; blank = AWS_PROFILE env var
    }

    error_count += validate_keys_with_types(cfg, aws, optional_keys, "aws", required=False)

    if not aws.get("s3_bucket_raw"):
        logger.warning("aws.s3_bucket_raw is not defined. Falling back to aws.s3_bucket_panos_unsecured for raw data staging.")

    # ✅ Credentials come only from a named AWS profile (aws.profile, else AWS_PROFILE).
    # The static-key modes (auth_mode keyring/config, access_key/secret_key) were removed
    # in schema 1.7.0; any leftover key is reported so it can be deleted.
    for retired in ("auth_mode", "keyring_service_name", "access_key", "secret_key"):
        if retired in aws:
            logger.warning(f"aws.{retired} is no longer used (credentials come from aws.profile); remove it.")
    profile = str(aws.get("profile") or "").strip() or os.environ.get("AWS_PROFILE", "").strip()
    if profile.lower() == "default":
        logger.error("The AWS profile 'default' is refused; set aws.profile to the project's profile "
                     "(normally 'rmi-360-workflow-pyt').", error_type=ConfigValidationError)
        error_count += 1
    elif not profile:
        logger.warning("No AWS profile: set aws.profile (normally 'rmi-360-workflow-pyt') or AWS_PROFILE. "
                       "AWS steps will refuse to run without one.")

    # ✅ max_workers logic: allow int or resolvable expression
    max_workers = aws.get("max_workers")
    if max_workers is None:
        logger.error("aws.max_workers must be defined", error_type=ConfigValidationError)
        error_count += 1
    elif isinstance(max_workers, int):
        pass  # OK
    elif isinstance(max_workers, str) and max_workers.lower().startswith("cpu*"):
        pass  # OK
    else:
        resolved = try_resolve_config_expression(max_workers, "aws.max_workers", cfg, expected_type=int)
        if resolved is None:
            error_count += 1

    # ✅ Ensure s3_bucket_folder resolves to a string
    folder_expr = aws.get("s3_bucket_folder")
    if not try_resolve_config_expression(folder_expr, "aws.s3_bucket_folder", cfg, expected_type=str):
        error_count += 1

    secured = cfg.get("aws.secured_delivery", {})
    if secured:
        if not isinstance(secured, dict):
            logger.error("aws.secured_delivery must be a mapping.", error_type=ConfigValidationError)
            error_count += 1
        else:
            if "enabled" in secured and not isinstance(secured.get("enabled"), bool):
                logger.error("aws.secured_delivery.enabled must be a boolean", error_type=ConfigValidationError)
                error_count += 1

            if secured.get("enabled", False):
                # Secured mode requires the secured panos bucket and the cloud store name.
                secured_bucket = cfg.get("aws.s3_bucket_panos_secured")
                if not isinstance(secured_bucket, str) or not secured_bucket.strip():
                    logger.error("aws.s3_bucket_panos_secured must be set when aws.secured_delivery.enabled is true",
                                 error_type=ConfigValidationError)
                    error_count += 1
                store = secured.get("cloud_store_name")
                if not isinstance(store, str) or not store.strip():
                    logger.error("aws.secured_delivery.cloud_store_name must be set when aws.secured_delivery.enabled is true",
                                 error_type=ConfigValidationError)
                    error_count += 1

                if error_count == 0 and not validate_secured_storage_deployment(cfg):
                    error_count += 1

    return error_count == 0
