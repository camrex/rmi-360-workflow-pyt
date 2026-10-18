# =============================================================================
# 🔐 AWS profile check (config_editor/core/aws_check.py)
# -----------------------------------------------------------------------------
# Verifies the AWS credential configuration a user is about to save:
#   1. Resolves the named AWS profile: aws.profile, else the AWS_PROFILE
#      environment variable. Neither, or "default", is an error — mirroring
#      utils.shared.aws_utils.resolve_profile_name, which refuses the same cases.
#   2. Validates the profile actually authenticates (STS get_caller_identity),
#      and optionally that the configured S3 buckets are reachable.
#
# Static keys (keyring / plaintext) are no longer supported (schema 1.7.0).
# boto3 is optional: if not installed, step 2 degrades to a warning. The
# session factory and environment are injectable for testing.
# =============================================================================

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, List, Mapping, Optional

PROFILE_ENV_VAR = "AWS_PROFILE"


@dataclass
class Check:
    name: str
    status: str   # "ok" | "warn" | "error"
    detail: str = ""


def _is_placeholder(v: Any) -> bool:
    return v is None or "<" in str(v) or not str(v).strip()


def _short(exc: Exception) -> str:
    msg = str(exc)
    return msg if len(msg) <= 160 else msg[:157] + "..."


def resolve_profile(aws: Mapping[str, Any], environ: Optional[Mapping[str, str]] = None) -> Check:
    """Which profile would the toolbox use? Returns a Check whose detail is the name."""
    environ = os.environ if environ is None else environ
    configured = str(aws.get("profile") or "").strip()
    from_env = str(environ.get(PROFILE_ENV_VAR, "") or "").strip()
    name = configured or from_env
    if not name:
        return Check("AWS profile", "error",
                     f"not set — set aws.profile (normally rmi-360-workflow-pyt) or {PROFILE_ENV_VAR}")
    if name.lower() == "default":
        return Check("AWS profile", "error", "'default' is refused — name the project's own profile")
    source = "aws.profile" if configured else PROFILE_ENV_VAR
    return Check("AWS profile", "ok", f"{name} (from {source})")


def check_aws_auth(values: Mapping[str, Any], *,
                   session_factory: Optional[Callable[..., Any]] = None,
                   environ: Optional[Mapping[str, str]] = None,
                   check_buckets: bool = True) -> List[Check]:
    """Run the AWS profile checks against a config ``values`` tree."""
    aws = (values.get("aws") or {}) if isinstance(values, Mapping) else {}
    region = aws.get("region")

    profile_check = resolve_profile(aws, environ)
    checks: List[Check] = [profile_check]
    if profile_check.status == "error":
        checks.append(Check("Validate credentials", "warn", "skipped — resolve the errors above first"))
        return checks
    profile = profile_check.detail.split(" (from ", 1)[0]

    # --- validate against AWS --------------------------------------------
    factory = session_factory
    if factory is None:
        try:
            import boto3  # type: ignore
            factory = boto3.Session
        except ImportError:
            checks.append(Check("Validate credentials", "warn",
                                "boto3 not installed — cannot verify against AWS"))
            return checks

    try:
        session = factory(profile_name=profile, region_name=None if _is_placeholder(region) else region)
        identity = session.client("sts").get_caller_identity()
        checks.append(Check("Credentials valid", "ok",
                            f"account {identity.get('Account')} — {identity.get('Arn')}"))
    except Exception as ex:  # noqa: BLE001
        checks.append(Check("Credentials valid", "error",
                            f"authentication failed: {_short(ex)} — try: aws sso login --profile {profile}"))
        return checks

    # --- optional: S3 bucket existence / access -----------------------------
    if check_buckets:
        secured_delivery = aws.get("secured_delivery") or {}
        bucket_specs = [aws.get("s3_bucket_panos_unsecured"), aws.get("s3_bucket_raw")]
        if secured_delivery.get("enabled"):
            bucket_specs.append(aws.get("s3_bucket_panos_secured"))
        s3 = session.client("s3")
        for bucket in bucket_specs:
            if _is_placeholder(bucket):
                continue
            status, detail = _bucket_status(s3, bucket)
            checks.append(Check(f"S3 bucket {bucket}", status, detail))

    return checks


def _error_code(exc: Exception) -> str:
    """Pull an AWS error code / HTTP status from a botocore ClientError-like exc
    without importing botocore (duck-typed on `.response`)."""
    resp = getattr(exc, "response", None)
    if isinstance(resp, Mapping):
        return str(resp.get("Error", {}).get("Code")
                   or resp.get("ResponseMetadata", {}).get("HTTPStatusCode") or "")
    return ""


def _bucket_status(s3, bucket):
    """Return (status, detail): does the bucket exist and is it accessible?"""
    try:
        s3.head_bucket(Bucket=bucket)
        return "ok", "exists and is accessible"
    except Exception as ex:  # noqa: BLE001
        code = _error_code(ex)
        if code in ("404", "NoSuchBucket"):
            return "error", "does not exist (404)"
        if code in ("403", "AccessDenied", "Forbidden"):
            return "warn", "exists but access denied (403) — check region/permissions"
        return "warn", f"could not verify: {_short(ex)}"


def summarize(checks: List[Check]) -> str:
    errs = sum(1 for c in checks if c.status == "error")
    warns = sum(1 for c in checks if c.status == "warn")
    if errs:
        return f"{errs} problem(s), {warns} warning(s)"
    if warns:
        return f"Looks OK with {warns} warning(s)"
    return "All checks passed"
