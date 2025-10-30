# =============================================================================
# ☁️ AWS Credential Access Logic (utils/aws_utils.py)
# -----------------------------------------------------------------------------
# Purpose:             Retrieves AWS credentials from keyring or config for use in S3/Lambda clients
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.2.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-14
# Last Updated:        2025-10-30
#
# Description:
#   Provides a utility function to retrieve AWS credentials required by boto3 clients.
#   If configured, credentials are securely pulled from the system keyring. Fallback
#   reads credentials from the config file. Raises explicit errors if credentials are missing.
#
# File Location:        /utils/aws_utils.py
# Called By:            utils/copy_to_aws.py, utils/deploy_lambda_monitor.py
# Int. Dependencies:    utils/manager/config_manager
# Ext. Dependencies:    keyring, typing
#
# Documentation:
#   See: docs_legacy/UTILITIES.md and docs_legacy/AWS_SETUP_GUIDE.md
#   (Ensure these docs are current; update if needed.)
#
# Notes:
#   - Compatible with AWS CLI–configured profiles or keyring service
#   - Supports switching between secure and fallback credential modes
#   - Raises explicit errors if credentials are missing or misconfigured
# =============================================================================
from __future__ import annotations
import keyring
from boto3.session import Session
from botocore.exceptions import ClientError, NoCredentialsError
from typing import Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from utils.manager.config_manager import ConfigManager


def get_aws_credentials(cfg: "ConfigManager") -> Tuple[str, str]:
    """
    Retrieves AWS credentials from keyring or configuration.

    If keyring usage is enabled in the config, credentials are fetched from the system keyring using the specified
    service name. Otherwise, credentials are read directly from the config dictionary.

    Args:
        cfg: Instance of ConfigManager to retrieve settings.
    Returns:
        (access_key, secret_key): Tuple of AWS credentials as strings.
    Raises:
        RuntimeError: If required credentials are missing.
    """
    logger = cfg.get_logger()
    use_keyring = cfg.get("aws.keyring_aws", False)
    service_name = cfg.get("aws.keyring_service_name", "rmi_s3")
    if use_keyring:
        access_key = keyring.get_password(service_name, "aws_access_key_id")
        secret_key = keyring.get_password(service_name, "aws_secret_access_key")
        if not access_key or not secret_key:
            logger.error(f"AWS credentials not found in keyring for service '{service_name}'.", indent=2,
                         error_type=RuntimeError)
        logger.custom("Retrieved AWS credentials from keyring.", indent=2, emoji="🔑")
        return access_key, secret_key
    else:
        access_key = cfg.get("aws.access_key")
        secret_key = cfg.get("aws.secret_key")
        if not access_key or not secret_key:
            logger.error("AWS credentials not found in config. Please check your aws.access_key and aws.secret_key "
                         "settings.", indent=2, error_type=RuntimeError)
        logger.custom("Retrieved AWS credentials from config.", indent=2, emoji="🔑")
        return access_key, secret_key


def verify_aws_credentials(access_key, secret_key, region, logger):
    """
    Attempts to verify AWS credentials by calling sts.get_caller_identity().
    Raises an exception if verification fails.

    Args:
        access_key (str): AWS access key ID.
        secret_key (str): AWS secret access key.
        region (str): AWS region.
        logger: Logger object for output.

    Returns:
        Session: A boto3 Session object if verification succeeds.
    """
    try:
        logger.info("Verifying AWS credentials...", indent=1)
        session = Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        sts = session.client("sts")
        sts.get_caller_identity()
        logger.custom("AWS credentials verified.", emoji="🔑", indent=2)
        return session
    except (ClientError, NoCredentialsError, Exception) as e:
        logger.error(f"AWS credentials verification failed: {e}", indent=2)
        raise


def get_boto3_session(cfg):
    """
    Returns a boto3 Session. If aws.auth_mode == 'instance', use default chain (instance profile).
    Else, fall back to existing get_aws_credentials() + verify_aws_credentials().
    """
    mode = cfg.get("aws.auth_mode", "config")  # "instance" | "keyring" | "config"
    region = cfg.get("aws.region")
    logger = cfg.get_logger()

    if mode == "instance":
        logger.custom("Using EC2 instance profile credentials.", emoji="🔐", indent=2)
        # Default session picks up IMDS/instance role automatically
        return Session(region_name=region)
    else:
        access_key, secret_key = get_aws_credentials(cfg)
        return verify_aws_credentials(access_key, secret_key, region, logger)

