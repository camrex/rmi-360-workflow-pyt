from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

from utils.shared.rmi_exceptions import ConfigValidationError

if TYPE_CHECKING:
    from utils.manager.config_manager import ConfigManager


_CACHE_KEY = "__secured_storage_deployment_validation__"
_LOG = logging.getLogger(__name__)


def _normalize_admin_base_url(raw_url: str) -> Optional[str]:
    """Normalize a Server URL to an admin base URL suitable for /data/* calls."""
    if not isinstance(raw_url, str):
        return None

    url = raw_url.strip().rstrip("/")
    if not url:
        return None

    # Already an admin URL.
    if re.search(r"/admin(?:$|/)", url, re.IGNORECASE):
        return re.sub(r"/+$", "", url)

    # Convert typical service endpoints to admin root.
    # Example: https://host/server/rest/services -> https://host/server/admin
    url = re.sub(r"/rest/services(?:/.*)?$", "/admin", url, flags=re.IGNORECASE)

    # Convert machine/service endpoint style.
    # Example: https://host/server/services -> https://host/server/admin
    url = re.sub(r"/services(?:/.*)?$", "/admin", url, flags=re.IGNORECASE)

    # If still not explicit admin and URL appears to end at /server, append /admin.
    if re.search(r"/server$", url, re.IGNORECASE):
        url = f"{url}/admin"

    # If there is no clear /admin segment after normalization, treat as unusable.
    if not re.search(r"/admin(?:$|/)", url, re.IGNORECASE):
        return None

    return url.rstrip("/")


def _parse_version_tuple(raw_version: Any) -> Optional[Tuple[int, int]]:
    """Return (major, minor) parsed from a version value, or None when not parseable."""
    if raw_version is None:
        return None

    text = str(raw_version).strip()
    if not text:
        return None

    # Accept forms like 12, 12.0, 12.1.0, or text containing a leading numeric version.
    match = re.search(r"(\d+)(?:\.(\d+))?", text)
    if not match:
        return None

    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    return major, minor


def _is_version_at_least(raw_version: Any, minimum: Tuple[int, int]) -> Optional[bool]:
    parsed = _parse_version_tuple(raw_version)
    if parsed is None:
        return None
    return parsed >= minimum


def _safe_get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    if hasattr(obj, "get"):
        try:
            return obj.get(key, default)
        except Exception:
            return default
    return getattr(obj, key, default)


def _as_plain_dict(obj: Any) -> Dict[str, Any]:
    """Best-effort conversion of SDK property objects to plain dicts."""
    if isinstance(obj, dict):
        return obj
    if obj is None:
        return {}

    for attr in ("as_dict", "to_dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                value = fn()
                if isinstance(value, dict):
                    return value
            except Exception as ex:
                _LOG.debug("_as_plain_dict: %s conversion failed: %s", attr, ex)

    # ArcGIS API PropertyMap objects usually support dict().
    try:
        value = dict(obj)
        if isinstance(value, dict):
            return value
    except Exception as ex:
        _LOG.debug("_as_plain_dict: dict(obj) conversion failed: %s", ex)

    return {}


def _flatten_data_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize possible find-data-items response shapes into a list of item dicts."""
    for key in ("items", "dataItems", "rootItems"):
        value = payload.get(key)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, dict)]
    return []


def _extract_cloud_store_name(item: Dict[str, Any]) -> Optional[str]:
    """Try common cloud store name fields first, then derive from path."""
    for key in ("name", "itemName", "title"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    path = item.get("path")
    if isinstance(path, str) and path.strip():
        segments = [part for part in path.strip("/").split("/") if part]
        if segments:
            return segments[-1]

    return None


def _extract_object_store(item: Dict[str, Any]) -> Optional[str]:
    """Return objectStore if present in item or nested properties."""
    direct = item.get("objectStore")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    for nested_key in ("properties", "info", "storeProperties"):
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            val = nested.get("objectStore")
            if isinstance(val, str) and val.strip():
                return val.strip()

    return None


def _extract_secured_capability(item: Dict[str, Any]) -> Optional[bool]:
    """
    Return secured-storage capability flag when an explicit boolean is exposed.
    Returns None when the API response does not expose a reliable flag.
    """
    candidate_keys = (
        "supportsSecuredStorage",
        "supportsSecuredAccess",
        "isSecuredStorage",
        "securedStorage",
    )

    for key in candidate_keys:
        value = item.get(key)
        if isinstance(value, bool):
            return value

    for nested_key in ("properties", "info", "storeProperties"):
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            for key in candidate_keys:
                value = nested.get(key)
                if isinstance(value, bool):
                    return value

    return None


def _extract_bucket_name(object_store: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse objectStore string and return (bucket, folder_or_none).
    Accepts forms like:
      - bucket
      - bucket/folder
      - s3://bucket/folder
      - /bucket/folder
    """
    if not isinstance(object_store, str):
        return None, None

    text = object_store.strip()
    if not text:
        return None, None

    text = re.sub(r"^[a-zA-Z0-9+.-]+://", "", text)
    text = text.strip("/")
    if not text:
        return None, None

    parts = [p for p in text.split("/") if p]
    if not parts:
        return None, None

    bucket = parts[0]
    folder = "/".join(parts[1:]) if len(parts) > 1 else None
    return bucket, folder


def _iter_hosting_server_urls(gis: Any) -> Iterable[str]:
    """Yield candidate hosting server admin URLs for cloud store enumeration."""
    yielded = set()

    # Prefer helperServices hostingServers metadata from portal self.
    helper_services = _safe_get(_safe_get(gis, "properties", {}), "helperServices", {})
    hosting_servers = _safe_get(helper_services, "hostingServers", [])
    if isinstance(hosting_servers, list):
        for hs in hosting_servers:
            if not isinstance(hs, dict):
                continue
            for key in ("adminUrl", "url"):
                candidate = hs.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    normalized = _normalize_admin_base_url(candidate)
                    if not normalized:
                        continue
                    if normalized not in yielded:
                        yielded.add(normalized)
                        yield normalized

    # Fallback: portal admin server listing if available.
    try:
        servers_obj = _safe_get(_safe_get(gis, "admin", None), "servers", None)
        if servers_obj and hasattr(servers_obj, "list"):
            for server in servers_obj.list() or []:
                role = str(_safe_get(server, "serverRole", "")).upper()
                if "HOSTING" not in role:
                    continue
                for key in ("admin_url", "adminUrl", "url"):
                    candidate = _safe_get(server, key)
                    if isinstance(candidate, str) and candidate.strip():
                        normalized = _normalize_admin_base_url(candidate)
                        if not normalized:
                            continue
                        if normalized not in yielded:
                            yielded.add(normalized)
                            yield normalized
    except Exception:
        return


def _iter_hosting_server_objects(gis: Any) -> Iterable[Any]:
    """Yield hosting server objects from the active portal admin context."""
    try:
        servers_obj = _safe_get(_safe_get(gis, "admin", None), "servers", None)
        if not servers_obj or not hasattr(servers_obj, "list"):
            return
        for server in servers_obj.list() or []:
            role = str(_safe_get(server, "serverRole", "")).upper()
            if "HOSTING" in role:
                yield server
    except Exception:
        return


def _extract_cloud_store_items_via_python_api(gis: Any) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    Preferred cloud store enumeration path using ArcGIS Python API object model:
    hosting server -> datastores.list().

    Returns:
      - (items, source) when list() succeeds (items can be empty)
      - (None, None) when the API path is unavailable or fails
    """
    attempted = False

    for server in _iter_hosting_server_objects(gis):
        attempted = True
        datastores_obj = _safe_get(server, "datastores", None)
        if datastores_obj is None:
            datastores_obj = _safe_get(server, "data_stores", None)
        if datastores_obj is None or not hasattr(datastores_obj, "list"):
            continue

        try:
            stores = datastores_obj.list() or []
        except Exception:
            continue

        items: List[Dict[str, Any]] = []
        for store in stores:
            props = _as_plain_dict(_safe_get(store, "properties", {}))
            info = _as_plain_dict(_safe_get(props, "info", {}))

            path = _safe_get(props, "path") or _safe_get(store, "path")
            if not isinstance(path, str) or "/cloudstores/" not in path.lower():
                continue

            item: Dict[str, Any] = {
                "path": path,
                "properties": props,
            }

            if info:
                item["info"] = info

            object_store = (
                _safe_get(info, "objectStore")
                or _safe_get(props, "objectStore")
                or _safe_get(store, "objectStore")
            )
            if isinstance(object_store, str) and object_store.strip():
                item["objectStore"] = object_store.strip()

            items.append(item)

        return items, "hosting_server.datastores.list()"

    if attempted:
        # We reached server enumeration but could not complete datastore listing.
        return None, None
    return None, None


def _fetch_cloud_store_items(gis: Any) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    Enumerate cloud stores from server admin API.

    Returns:
      - items list when successful, and the URL used
      - (None, None) when no endpoint could be reached
    """
    # Preferred path: ArcGIS Python API object model in active Pro session.
    py_items, py_source = _extract_cloud_store_items_via_python_api(gis)
    if py_items is not None:
        return py_items, py_source

    # Fallback path: raw REST via active GIS connection object.
    con = _safe_get(gis, "_con", None)
    if con is None:
        return None, None

    payloads = (
        {"f": "json", "ancestorPath": "/cloudStores", "types": "cloudStore"},
        {"f": "json", "parentPath": "/cloudStores"},
    )

    for base_url in _iter_hosting_server_urls(gis):
        for endpoint in (f"{base_url}/data/findItems", f"{base_url}/data/findDataItems"):
            for params in payloads:
                try:
                    response = con.post(endpoint, params)
                except Exception:
                    continue

                if not isinstance(response, dict):
                    continue
                items = _flatten_data_items(response)
                if items:
                    return items, endpoint
                # A successful call can return an empty list.
                if any(k in response for k in ("items", "dataItems", "rootItems")):
                    return [], endpoint

    return None, None


def validate_secured_storage_deployment(cfg: "ConfigManager") -> bool:
    """
    Tiered secured-storage deployment validation.

    Runs only when secured_storage.enabled is true. Check order:
      Tier 1: Enterprise version >= 12.0
      Tier 2: cloud_store_name exists among registered cloud stores
      Tier 3: cloud store objectStore bucket agrees with secured_storage.s3_bucket

    Permissions and endpoint reachability issues degrade to warnings to avoid
    blocking non-admin users on otherwise valid deployments.

    Note: This is preflight validation only. True end-to-end verification still
    requires test publish and viewer image access.
    """
    logger = cfg.get_logger()
    secured = cfg.get("secured_storage", {}) or {}

    if not isinstance(secured, dict) or not secured.get("enabled", False):
        return True

    cache = cfg.raw.get(_CACHE_KEY)
    if isinstance(cache, bool):
        return cache

    # Tier 0: get ArcGIS Pro active portal session.
    try:
        from arcgis.gis import GIS  # type: ignore
    except Exception as ex:
        logger.warning(
            f"Secured storage validation warning: could not load ArcGIS GIS('pro') session for deployment checks ({ex})."
        )
        cfg.raw[_CACHE_KEY] = True
        return True

    try:
        gis = GIS("pro")
    except Exception as ex:
        logger.warning(
            f"Secured storage validation warning: could not access ArcGIS Pro signed-in session ({ex})."
        )
        cfg.raw[_CACHE_KEY] = True
        return True

    # Tier 1: Enterprise version gate.
    version_raw = _safe_get(_safe_get(gis, "properties", {}), "currentVersion")
    if version_raw is None:
        try:
            portal_url = str(_safe_get(gis, "url", "")).rstrip("/")
            if portal_url:
                info = _safe_get(gis, "_con", None).get(f"{portal_url}/sharing/rest/info", {"f": "json"})
                if isinstance(info, dict):
                    version_raw = info.get("currentVersion")
        except Exception:
            version_raw = None

    version_ok = _is_version_at_least(version_raw, (12, 0))
    if version_ok is None:
        logger.warning(
            "Secured storage validation warning: could not verify Enterprise version; continuing with unverified deployment state."
        )
        cfg.raw[_CACHE_KEY] = True
        return True

    if version_ok is False:
        logger.error(
            "Secured storage validation failed: Enterprise version is below 12.0. "
            "Secured storage requires Enterprise 12.0+; set secured_storage.enabled to false or upgrade.",
            error_type=ConfigValidationError,
        )
        cfg.raw[_CACHE_KEY] = False
        return False

    # Tier 2: cloud_store_name existence and optional secured-capability flag.
    configured_store_name = str(secured.get("cloud_store_name", "")).strip()
    items, source_url = _fetch_cloud_store_items(gis)
    if items is None:
        logger.warning(
            "Secured storage validation warning: cloud store name not verified due to insufficient permissions "
            "or unreachable server admin endpoint."
        )
        cfg.raw[_CACHE_KEY] = True
        return True

    matched_item = None
    for item in items:
        item_name = _extract_cloud_store_name(item)
        if isinstance(item_name, str) and item_name.lower() == configured_store_name.lower():
            matched_item = item
            break

    if matched_item is None:
        logger.error(
            f"Secured storage validation failed: secured_storage.cloud_store_name '{configured_store_name}' was not "
            f"found among registered cloud stores from {source_url}. Verify the name in Server Manager.",
            error_type=ConfigValidationError,
        )
        cfg.raw[_CACHE_KEY] = False
        return False

    capability = _extract_secured_capability(matched_item)
    if capability is False:
        logger.error(
            f"Secured storage validation failed: cloud store '{configured_store_name}' is not marked as secured-storage capable.",
            error_type=ConfigValidationError,
        )
        cfg.raw[_CACHE_KEY] = False
        return False
    if capability is None:
        logger.warning(
            "Secured storage validation note: no explicit secured-capability flag was found in cloud store enumeration; "
            "validated by cloud store name only."
        )

    # Tier 3: objectStore bucket agreement.
    object_store = _extract_object_store(matched_item)
    if not object_store:
        logger.warning("Secured storage validation warning: bucket agreement not verified; cloud store objectStore was not readable.")
        cfg.raw[_CACHE_KEY] = True
        return True

    bucket_from_store, folder_from_store = _extract_bucket_name(object_store)
    if not bucket_from_store:
        logger.warning(
            f"Secured storage validation warning: bucket agreement not verified; could not parse objectStore '{object_store}'."
        )
        cfg.raw[_CACHE_KEY] = True
        return True

    config_bucket = str(secured.get("s3_bucket", "")).strip()
    if bucket_from_store.lower() != config_bucket.lower():
        logger.error(
            f"Secured storage validation failed: configured secured bucket '{config_bucket}' does not match cloud store "
            f"objectStore bucket '{bucket_from_store}'. Images may upload to one bucket while viewer access targets another.",
            error_type=ConfigValidationError,
        )
        cfg.raw[_CACHE_KEY] = False
        return False

    # ImagePath keys are written as root-relative keys ({slug}/{filename}) because
    # the deployment expects a bucket-root cloud store registration.
    # If a folder is registered at the cloud store, the ImagePath base may need review.
    if folder_from_store:
        logger.warning(
            f"Secured storage validation warning: cloud store '{configured_store_name}' objectStore includes folder "
            f"'{folder_from_store}'. Current ImagePath keys are bucket-root-relative and may require base-path review."
        )

    cfg.raw[_CACHE_KEY] = True
    return True