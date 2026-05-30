from __future__ import annotations

from urllib.parse import quote
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from utils.manager.config_manager import ConfigManager


def is_secured_storage_enabled(cfg: "ConfigManager") -> bool:
    return bool(cfg.get("secured_storage.enabled", False))


def _normalize_prefix(prefix: Optional[str]) -> str:
    if not prefix:
        return ""
    return str(prefix).strip().strip("/")


def resolve_oid_key_prefix(cfg: "ConfigManager", secured_mode: Optional[bool] = None) -> str:
    secured = is_secured_storage_enabled(cfg) if secured_mode is None else bool(secured_mode)
    expr = cfg.get("secured_storage.s3_bucket_folder") if secured else cfg.get("aws.s3_bucket_folder")

    resolved = cfg.resolve(expr) if expr else ""
    prefix = _normalize_prefix(resolved)

    if not prefix:
        # Safe fallback to project slug if expression is missing.
        prefix = _normalize_prefix(cfg.get("project.slug", ""))

    return prefix


def resolve_oid_target_bucket(cfg: "ConfigManager", secured_mode: Optional[bool] = None) -> str:
    secured = is_secured_storage_enabled(cfg) if secured_mode is None else bool(secured_mode)
    return cfg.get("secured_storage.s3_bucket") if secured else cfg.get("aws.s3_bucket")


def resolve_oid_target_region(cfg: "ConfigManager", secured_mode: Optional[bool] = None) -> str:
    secured = is_secured_storage_enabled(cfg) if secured_mode is None else bool(secured_mode)
    return cfg.get("secured_storage.region") if secured else cfg.get("aws.region")


def build_oid_object_key(cfg: "ConfigManager", image_filename: str, secured_mode: Optional[bool] = None) -> str:
    prefix = resolve_oid_key_prefix(cfg, secured_mode=secured_mode)
    filename = str(image_filename).strip().lstrip("/")
    return f"{prefix}/{filename}".strip("/") if prefix else filename


def build_public_s3_image_url(bucket: str, region: str, object_key: str) -> str:
    quoted_key = quote(object_key, safe="/")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{quoted_key}"


def build_oid_image_path(cfg: "ConfigManager", image_filename: str) -> str:
    secured = is_secured_storage_enabled(cfg)
    object_key = build_oid_object_key(cfg, image_filename=image_filename, secured_mode=secured)

    if secured:
        return f"$virtualCacheDirectory:{object_key}"

    bucket = resolve_oid_target_bucket(cfg, secured_mode=False)
    region = resolve_oid_target_region(cfg, secured_mode=False)
    return build_public_s3_image_url(bucket, region, object_key)
