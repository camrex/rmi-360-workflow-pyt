# =============================================================================
# ☁️ AWS Session Logic (utils/shared/aws_utils.py)
# -----------------------------------------------------------------------------
# Purpose:             Builds boto3 sessions from a NAMED AWS profile, never the default chain
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             2.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-14
# Last Updated:        2026-10-18
#
# Description:
#   Every AWS call in the toolbox gets its session here. The profile comes from
#   config `aws.profile`, else the AWS_PROFILE environment variable. With neither,
#   or with the profile named "default", it refuses: falling through to boto3's
#   default chain would silently use whatever key the machine holds.
#
#   The profile is an IAM Identity Center (SSO) profile issued by rmi-aws-infra
#   (change 0049: `rmi-360-workflow-pyt`). Sign in with
#   `aws sso login --profile rmi-360-workflow-pyt` before a run. Static keys
#   (keyring or plaintext in config.yaml) are no longer supported.
#
# File Location:        /utils/shared/aws_utils.py
# Called By:            utils/copy_to_aws.py, utils/s3_utils.py, utils/shared/backup_to_s3.py,
#                       utils/shared/oid_storage_migration.py, utils/shared/s3_upload_helpers.py,
#                       utils/deploy_secured_test_set.py
# Ext. Dependencies:    boto3, botocore
#
# Documentation:
#   See: docs/aws/setup-guide.rst
# =============================================================================
from __future__ import annotations

import os
from typing import Optional, TYPE_CHECKING

from boto3.session import Session
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound

if TYPE_CHECKING:
    from utils.manager.config_manager import ConfigManager

PROFILE_ENV_VAR = "AWS_PROFILE"
DEFAULT_PROFILE = "rmi-360-workflow-pyt"


def resolve_profile_name(profile: Optional[str] = None) -> str:
    """Return the AWS profile to use: ``profile`` if given, else ``$AWS_PROFILE``.

    Raises:
        RuntimeError: if neither is set, or the profile is ``default``. The default
            profile and boto3's default chain are refused on purpose, so a run can
            never pick up an unrelated key by accident.
    """
    name = str(profile or "").strip() or os.environ.get(PROFILE_ENV_VAR, "").strip()
    if not name:
        raise RuntimeError(
            f"No AWS profile set. Set aws.profile in config.yaml (normally '{DEFAULT_PROFILE}') "
            f"or the {PROFILE_ENV_VAR} environment variable. The default credential chain is "
            "never used."
        )
    if name.lower() == "default":
        raise RuntimeError(
            "The AWS profile 'default' is refused. Name the project's own profile "
            f"(normally '{DEFAULT_PROFILE}') in aws.profile or {PROFILE_ENV_VAR}."
        )
    return name


def profile_session(profile: Optional[str] = None, region: Optional[str] = None) -> Session:
    """Create a boto3 Session for the resolved named profile.

    With an explicit profile name, botocore ignores AWS_ACCESS_KEY_ID-style
    environment credentials, so the session uses only that profile.
    """
    name = resolve_profile_name(profile)
    try:
        return Session(profile_name=name, region_name=region or None)
    except ProfileNotFound:
        raise RuntimeError(
            f"AWS profile '{name}' is not in ~/.aws/config on this machine. Add it (see "
            "docs/aws/setup-guide.rst), then run `aws sso login --profile "
            f"{name}`."
        ) from None


def get_boto3_session(cfg: "ConfigManager") -> Session:
    """Session for the config's ``aws.profile`` (or ``$AWS_PROFILE``) and ``aws.region``."""
    logger = cfg.get_logger()
    try:
        name = resolve_profile_name(cfg.get("aws.profile"))
        session = profile_session(name, cfg.get("aws.region"))
    except RuntimeError as e:
        logger.error(str(e), indent=2, error_type=RuntimeError)
        raise
    logger.custom(f"Using AWS profile '{name}'.", emoji="🔐", indent=2)
    return session


def validate_s3_bucket_access(cfg: "ConfigManager", bucket: Optional[str] = None) -> Session:
    """Verify AWS auth and target S3 bucket access before starting upload-dependent work."""
    logger = cfg.get_logger()
    bucket = bucket or cfg.get("aws.s3_bucket_panos_unsecured")

    if not bucket:
        logger.error("AWS S3 bucket is not configured.", indent=2, error_type=RuntimeError)

    try:
        session = get_boto3_session(cfg)
        logger.info(f"Verifying S3 bucket access: {bucket}", indent=1)
        s3 = session.client("s3")
        s3.head_bucket(Bucket=bucket)
        logger.custom(f"S3 bucket access verified: {bucket}", indent=2, emoji="🪣")
        return session
    except (ClientError, NoCredentialsError, Exception) as e:
        logger.error(f"AWS S3 preflight failed for bucket '{bucket}': {e}", indent=2, error_type=RuntimeError)
        raise
