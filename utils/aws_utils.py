# =============================================================================
# ☁️ AWS Credential Access Logic (utils/aws_utils.py)
# -----------------------------------------------------------------------------
# Purpose:             Retrieves AWS credentials from keyring or config for use in S3/Lambda clients
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-14
# Last Updated:        2025-05-14
#
# Description:
#   Provides a utility function to retrieve AWS credentials required by boto3 clients.
#   If configured, credentials are securely pulled from the system keyring. Fallback
#   reads credentials from the config file. Raises explicit errors if credentials are missing.
#
# File Location:        /utils/aws_utils.py
# Called By:            copy_to_aws.py, deploy_lambda_monitor.py
# Int. Dependencies:    None
# Ext. Dependencies:    keyring
#
# Documentation:
#   See: docs_legacy/UTILITIES.md and docs_legacy/AWS_SETUP_GUIDE.md
#   (Ensure these docs are current; update if needed.)
#
# Notes:
#   - Compatible with AWS CLI–configured profiles or keyring service
#   - Supports switching between secure and fallback credential modes
# =============================================================================

import keyring
from utils.manager.config_manager import ConfigManager

from typing import Tuple, Optional, Any

def get_aws_credentials(
    cfg: ConfigManager,
    *,
    keyring_mod=None,
    logger: Optional[Any] = None
) -> Tuple[str, str]:
    """
    Retrieves AWS credentials from keyring or configuration.

    If keyring usage is enabled in the config, credentials are fetched from the system keyring using the specified
    service name. Otherwise, credentials are read directly from the config dictionary.

    Args:
        cfg: Instance of ConfigManager to retrieve settings.
        keyring_mod: Optional keyring module for dependency injection/testing.
        logger: Optional logger for dependency injection/testing.
    Returns:
        (access_key, secret_key): Tuple of AWS credentials as strings.
    Raises:
        RuntimeError: If required credentials are missing.
    """
    keyring_mod = keyring_mod or keyring
    logger = logger or cfg.get_logger()
    use_keyring = cfg.get("aws.keyring_aws", False)
    service_name = cfg.get("aws.keyring_service_name", "rmi_s3")
    if use_keyring:
        access_key = keyring_mod.get_password(service_name, "aws_access_key_id")
        secret_key = keyring_mod.get_password(service_name, "aws_secret_access_key")
        if not access_key or not secret_key:
            logger.error(f"AWS credentials not found in keyring for service '{service_name}'.")
            raise RuntimeError(f"AWS credentials not found in keyring for service '{service_name}'.")
        logger.debug("Retrieved AWS credentials from keyring.")
        return access_key, secret_key
    else:
        access_key = cfg.get("aws.access_key")
        secret_key = cfg.get("aws.secret_key")
        if not access_key or not secret_key:
            logger.error("AWS credentials not found in config. Please check your aws.access_key and aws.secret_key settings.")
            raise RuntimeError("AWS credentials not found in config. Please check your aws.access_key and aws.secret_key settings.")
        logger.debug("Retrieved AWS credentials from config.")
        return access_key, secret_key