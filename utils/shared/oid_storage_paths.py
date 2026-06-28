from __future__ import annotations

from urllib.parse import quote
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from utils.manager.config_manager import ConfigManager


def is_secured_storage_enabled(cfg: "ConfigManager") -> bool:
    return bool(cfg.get("aws.secured_delivery.enabled", False))


def _normalize_prefix(prefix: Optional[str]) -> str:
    if not prefix:
        return ""
    return str(prefix).strip().strip("/")


def resolve_oid_key_prefix(cfg: "ConfigManager", secured_mode: Optional[bool] = None) -> str:
    # One shared key prefix for both delivery modes (secured_mode kept for signature
    # compatibility; the prefix no longer differs by mode).
    expr = cfg.get("aws.s3_bucket_folder")
    resolved = cfg.resolve(expr) if expr else ""
    prefix = _normalize_prefix(resolved)

    if not prefix:
        # Safe fallback to project slug if expression is missing.
        prefix = _normalize_prefix(cfg.get("project.slug", ""))

    return prefix


def resolve_oid_target_bucket(cfg: "ConfigManager", secured_mode: Optional[bool] = None) -> str:
    secured = is_secured_storage_enabled(cfg) if secured_mode is None else bool(secured_mode)
    return (cfg.get("aws.s3_bucket_panos_secured") if secured
            else cfg.get("aws.s3_bucket_panos_unsecured"))


def resolve_oid_target_region(cfg: "ConfigManager", secured_mode: Optional[bool] = None) -> str:
    # Per-bucket region override when set, else the default aws.region.
    secured = is_secured_storage_enabled(cfg) if secured_mode is None else bool(secured_mode)
    override = (cfg.get("aws.s3_bucket_panos_secured_region") if secured
                else cfg.get("aws.s3_bucket_panos_unsecured_region"))
    return override or cfg.get("aws.region")


def build_oid_object_key(cfg: "ConfigManager", image_filename: str, secured_mode: Optional[bool] = None) -> str:
    prefix = resolve_oid_key_prefix(cfg, secured_mode=secured_mode)
    filename = str(image_filename).strip().lstrip("/")
    return f"{prefix}/{filename}".strip("/") if prefix else filename


def build_public_s3_image_url(bucket: str, region: str, object_key: str) -> str:
    quoted_key = quote(object_key, safe="/")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{quoted_key}"


SECURED_IMAGE_PATH_PREFIX = "$virtualCacheDirectory:"


def build_oid_image_path_for_mode(cfg: "ConfigManager", image_filename: str, secured: bool) -> str:
    """
    Build an ImagePath for an explicit delivery mode, independent of the current
    ``aws.secured_delivery.enabled`` flag.

    This is the shared primitive behind both publishing (generate_oid_service) and
    migration (oid_storage_migration). Keeping the two path forms defined in exactly
    one place means an Esri-side change to the secured path format only edits here.

    secured=True  -> "$virtualCacheDirectory:<prefix>/<filename>"
    secured=False -> "https://<bucket>.s3.<region>.amazonaws.com/<prefix>/<filename>"
    """
    object_key = build_oid_object_key(cfg, image_filename=image_filename, secured_mode=secured)

    if secured:
        return f"{SECURED_IMAGE_PATH_PREFIX}{object_key}"

    bucket = resolve_oid_target_bucket(cfg, secured_mode=False)
    region = resolve_oid_target_region(cfg, secured_mode=False)
    return build_public_s3_image_url(bucket, region, object_key)


def build_oid_image_path(cfg: "ConfigManager", image_filename: str) -> str:
    return build_oid_image_path_for_mode(cfg, image_filename, is_secured_storage_enabled(cfg))


def extract_filename_from_image_path(image_path: str) -> Optional[str]:
    """
    Recover the bare image filename from either ImagePath form.

    Accepts:
      - "$virtualCacheDirectory:<prefix>/<filename>"
      - "https://<bucket>.s3.<region>.amazonaws.com/<prefix>/<filename>"
      - a bare "<prefix>/<filename>" or "<filename>"
    Returns None when nothing filename-like can be parsed.
    """
    if not isinstance(image_path, str):
        return None

    text = image_path.strip()
    if not text:
        return None

    if text.startswith(SECURED_IMAGE_PATH_PREFIX):
        text = text[len(SECURED_IMAGE_PATH_PREFIX):]

    # Drop scheme/host for URL forms; everything after the last '/' is the filename.
    text = text.split("?", 1)[0].rstrip("/")
    if not text:
        return None

    filename = text.split("/")[-1]
    return filename or None
