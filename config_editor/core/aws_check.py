# =============================================================================
# 🔐 AWS auth / keyring check (config_editor/core/aws_check.py)
# -----------------------------------------------------------------------------
# Verifies the AWS credential configuration a user is about to save:
#   1. Resolves the intended source from aws.auth_mode (instance | keyring | config),
#      mirroring utils.shared.aws_utils.
#   2. Checks the source is populated — keyring items present, or plaintext keys set
#      (and not still <PLACEHOLDER>).
#   3. Validates the credentials actually authenticate (STS get_caller_identity),
#      and optionally that the configured S3 buckets are reachable.
#
# boto3 / keyring are optional: if not installed the relevant step degrades to a
# warning instead of failing. Both deps are injectable for testing.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Mapping, Optional

# Keyring item names — MUST match the Set AWS Keyring tool and aws_utils (lowercase).
KEYRING_ITEMS = ("aws_access_key_id", "aws_secret_access_key")


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


def check_aws_auth(values: Mapping[str, Any], *,
                   keyring_mod: Any = None,
                   session_factory: Optional[Callable[..., Any]] = None,
                   check_buckets: bool = True) -> List[Check]:
    """Run the AWS auth/keyring checks against a config ``values`` tree."""
    aws = (values.get("aws") or {}) if isinstance(values, Mapping) else {}
    auth_mode = str(aws.get("auth_mode", "config")).lower()
    use_keyring = auth_mode == "keyring"
    service = aws.get("keyring_service_name", "rmi_s3")
    region = aws.get("region")

    checks: List[Check] = [Check("Auth mode", "ok", auth_mode)]
    access_key = secret_key = None

    # --- 1/2: resolve + populated check -------------------------------------
    if use_keyring:
        km = keyring_mod
        if km is None:
            try:
                import keyring as km  # type: ignore
            except ImportError:
                km = None
        if km is None:
            checks.append(Check("Keyring module", "warn",
                                "python 'keyring' not installed — cannot read the keyring here"))
            return checks
        creds = {}
        for item in KEYRING_ITEMS:
            try:
                val = km.get_password(service, item)
            except Exception as ex:  # noqa: BLE001
                checks.append(Check(f"Keyring {service}/{item}", "error", f"read failed: {_short(ex)}"))
                val = None
            else:
                if val and str(val).strip():
                    checks.append(Check(f"Keyring {service}/{item}", "ok", "present"))
                else:
                    checks.append(Check(f"Keyring {service}/{item}", "error", "missing or empty"))
            creds[item] = val
        access_key = creds["aws_access_key_id"]
        secret_key = creds["aws_secret_access_key"]

    elif auth_mode == "instance":
        checks.append(Check("Credential source", "ok",
                            "EC2/instance profile (default chain on this machine)"))
    else:  # config (plaintext)
        access_key = aws.get("access_key")
        secret_key = aws.get("secret_key")
        for name, val in (("access_key", access_key), ("secret_key", secret_key)):
            if _is_placeholder(val):
                checks.append(Check(f"Config {name}", "error", "missing or still a <PLACEHOLDER>"))
            else:
                checks.append(Check(f"Config {name}", "ok", "present"))

    if any(c.status == "error" for c in checks):
        checks.append(Check("Validate credentials", "warn", "skipped — resolve the errors above first"))
        return checks

    # --- 3: validate against AWS --------------------------------------------
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
        if auth_mode == "instance" and not use_keyring:
            session = factory(region_name=region)
        else:
            session = factory(aws_access_key_id=access_key,
                              aws_secret_access_key=secret_key, region_name=region)
        identity = session.client("sts").get_caller_identity()
        checks.append(Check("Credentials valid", "ok",
                            f"account {identity.get('Account')} — {identity.get('Arn')}"))
    except Exception as ex:  # noqa: BLE001
        checks.append(Check("Credentials valid", "error", f"authentication failed: {_short(ex)}"))
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


def set_keyring_credentials(service_name: str, access_key_id: str, secret_access_key: str,
                            *, keyring_mod: Any = None) -> Check:
    """Store AWS creds in the OS keyring under the names the toolbox/reader expect
    (service = aws.keyring_service_name; items = aws_access_key_id/aws_secret_access_key)."""
    if not service_name or not str(service_name).strip():
        return Check("Set keyring", "error", "keyring service name is required")
    if not access_key_id or not secret_access_key:
        return Check("Set keyring", "error", "both Access Key ID and Secret are required")

    km = keyring_mod
    if km is None:
        try:
            import keyring as km  # type: ignore
        except ImportError:
            return Check("Set keyring", "error", "python 'keyring' not installed")
    try:
        km.set_password(service_name, "aws_access_key_id", access_key_id)
        km.set_password(service_name, "aws_secret_access_key", secret_access_key)
    except Exception as ex:  # noqa: BLE001
        return Check("Set keyring", "error", f"failed to store: {_short(ex)}")
    return Check("Set keyring", "ok",
                 f"stored under service '{service_name}'. Set auth_mode: keyring to use it.")


def summarize(checks: List[Check]) -> str:
    errs = sum(1 for c in checks if c.status == "error")
    warns = sum(1 for c in checks if c.status == "warn")
    if errs:
        return f"{errs} problem(s), {warns} warning(s)"
    if warns:
        return f"Looks OK with {warns} warning(s)"
    return "All checks passed"
