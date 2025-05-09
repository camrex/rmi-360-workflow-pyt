# =============================================================================
# ☁️ AWS Credential Access Logic (utils/aws_utils.py)
# -----------------------------------------------------------------------------
# Purpose:             Retrieves AWS credentials from keyring or config for use in S3/Lambda clients
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
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
#   See: docs/UTILITIES.md and docs/AWS_SETUP_GUIDE.md
#
# Notes:
#   - Compatible with AWS CLI–configured profiles or keyring service
#   - Supports switching between secure and fallback credential modes
# =============================================================================

import keyring

def get_aws_credentials(config):
    """
    Retrieves AWS credentials from keyring or configuration.

    If keyring usage is enabled in the config, credentials are fetched from the system keyring using the specified
    service name. Otherwise, credentials are read directly from the config dictionary.

    Args:
        config: Configuration dictionary containing AWS credential settings.

    Returns:
        A tuple of (access_key, secret_key).

    Raises:
        RuntimeError: If keyring usage is enabled but credentials are missing.
    """
    use_keyring = config.get("aws", {}).get("keyring_aws", False)
    service_name = config.get("aws", {}).get("keyring_service_name", "rmi_s3")
    if use_keyring:
        access_key = keyring.get_password(service_name, "aws_access_key_id")
        secret_key = keyring.get_password(service_name, "aws_secret_access_key")
        if not access_key or not secret_key:
            raise RuntimeError(f"❌ AWS credentials not found in keyring for service '{service_name}'.")
        return access_key, secret_key
    else:
        aws_cfg = config.get("aws", {})
        access_key = aws_cfg.get("access_key")
        secret_key = aws_cfg.get("secret_key")
        if not access_key or not secret_key:
            raise RuntimeError("❌ AWS credentials not found in config. Please check your aws.access_key and "
                               "aws.secret_key settings.")
        return access_key, secret_key