# =============================================================================
# 🧷 Manifest → OID Field Join (utils/shared/manifest_fields.py)
# -----------------------------------------------------------------------------
# Purpose:             Populate OID fields from the corridor manifest by image
#                      Name. Shared by custom-field population (Add Images) and
#                      linear-ref override (Update Linear & Custom).
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Description:
#   The corridor manifest (pre-thin) carries per-image values computed with the
#   correct, intended subdivision (mp_pre, mp_meas, track, ...). These helpers
#   join those values onto OID rows by filename, so the orchestrated OID build can
#   honor the manifest's intent instead of re-deriving it (which, for linear
#   referencing, can snap a point to the geometrically nearest — but wrong —
#   subdivision route).
#
#   Stateless. No-op when no manifest is available, so non-manifest (post-thin)
#   runs are unaffected.
#
# File Location:        /utils/shared/manifest_fields.py
# Int. Dependencies:    utils/shared/oid_storage_paths
# Ext. Dependencies:    arcpy (cursors), csv
# =============================================================================

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

from utils.shared.oid_storage_paths import extract_filename_from_image_path

if TYPE_CHECKING:
    from utils.manager.config_manager import ConfigManager

__all__ = [
    "load_manifest_attr_map",
    "resolve_manifest_path",
    "populate_oid_fields_from_manifest",
]

# spec = (oid_field_name, manifest_column, default, field_type)
FieldSpec = Tuple[Optional[str], str, object, Optional[str]]


def load_manifest_attr_map(manifest_path: str, columns: Sequence[str], logger=None) -> dict:
    """Read the manifest and return ``{name_lower: {column_lower: value}}``.

    Keyed by image filename (basename of the ``Name`` column, or derived from
    ``Path`` when ``Name`` is absent). Only the requested ``columns`` are captured.
    """
    wanted = {str(c).lower() for c in columns}
    out: dict = {}
    with open(manifest_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        field_map = {fn.lower(): fn for fn in (reader.fieldnames or [])}
        name_col = field_map.get("name")
        path_col = field_map.get("path")
        for row in reader:
            key = None
            if name_col and row.get(name_col):
                key = Path(str(row[name_col]).strip()).name.lower()
            elif path_col and row.get(path_col):
                key = Path(str(row[path_col]).strip()).name.lower()
            if not key:
                continue
            rec = {}
            for col_lower in wanted:
                src = field_map.get(col_lower)
                if src and row.get(src) is not None:
                    rec[col_lower] = str(row[src]).strip()
            out[key] = rec
    if logger:
        logger.info(
            f"Manifest attributes: loaded {len(out):,} row(s) for column(s) {sorted(wanted)}.", indent=1
        )
    return out


def resolve_manifest_path(cfg: "ConfigManager", explicit: Optional[str] = None) -> Optional[str]:
    """Resolve the manifest path: explicit arg wins; else the configured pre-thin
    manifest when ``thinning_mode`` is ``pre``. Returns None when no manifest applies."""
    if explicit:
        return str(explicit)
    if str(cfg.get("thinning_mode", "post")).lower() == "pre":
        configured = cfg.get("corridor_thinning.manifest.path")
        if configured:
            return str(configured)
    return None


def populate_oid_fields_from_manifest(
    cfg: "ConfigManager",
    oid_fc_path: str,
    specs: List[FieldSpec],
    manifest_path: Optional[str],
    logger,
) -> int:
    """Join manifest values onto OID rows by image filename (from ImagePath).

    ``specs`` is a list of ``(oid_field_name, manifest_column, default, field_type)``.
    Empty/missing manifest cells fall back to ``default`` (None -> leave as-is).
    DOUBLE fields are coerced to float. Fields absent from the OID are skipped with
    a warning. Returns the number of rows updated. No-op when ``specs`` is empty or
    no manifest is available.
    """
    import arcpy

    specs = [s for s in specs if s and s[0] and s[1]]
    if not specs:
        return 0

    if not manifest_path or not Path(manifest_path).is_file():
        logger.warning(
            "Manifest-sourced field(s) declared but no manifest available; leaving them as-is.", indent=1
        )
        return 0

    existing = {f.name for f in arcpy.ListFields(oid_fc_path)}
    active = [s for s in specs if s[0] in existing]
    for name, _col, _default, _ftype in specs:
        if name not in existing:
            logger.warning(f"Manifest-sourced field '{name}' is not present on the OID; skipping.", indent=1)
    if not active:
        return 0

    attr_map = load_manifest_attr_map(manifest_path, [col for _n, col, _d, _t in active], logger)

    target_fields = [name for name, _c, _d, _t in active]

    # Pre-scan the match rate before writing anything. The join keys on the ORIGINAL
    # image filename, so manifest joins must run BEFORE Rename Images. A zero match
    # rate means renaming already happened (or the wrong manifest) — fail fast rather
    # than silently writing defaults/nulls over every row.
    total = 0
    matched = 0
    with arcpy.da.SearchCursor(oid_fc_path, ["ImagePath"]) as cursor:
        for (image_path,) in cursor:
            total += 1
            filename = extract_filename_from_image_path(image_path)
            if filename and filename.lower() in attr_map:
                matched += 1

    if total and matched == 0:
        logger.error(
            f"None of {total:,} OID image name(s) matched the manifest for field(s) {target_fields}. "
            "Manifest joins must run BEFORE Rename Images — check step order or the manifest path.",
            error_type=RuntimeError, indent=1,
        )
    if total and matched < total:
        logger.info(f"Manifest match: {matched:,}/{total:,} OID image(s) found in manifest.", indent=1)

    update_fields = ["ImagePath"] + target_fields
    updated = 0
    with arcpy.da.UpdateCursor(oid_fc_path, update_fields) as cursor:
        for row in cursor:
            filename = extract_filename_from_image_path(row[0])
            rec = attr_map.get(filename.lower(), {}) if filename else {}
            changed = False
            for i, (name, col, default, ftype) in enumerate(active, start=1):
                value = rec.get(col.lower())
                if value is None or value == "":
                    value = default
                if value is None:
                    continue
                if str(ftype).upper() == "DOUBLE":
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        logger.warning(f"Could not convert {name} value '{value}' to float; skipping row.", indent=2)
                        continue
                if row[i] != value:
                    row[i] = value
                    changed = True
            if changed:
                cursor.updateRow(row)
                updated += 1

    logger.success(
        f"Populated manifest-sourced field(s) {target_fields} for {updated:,} row(s).", indent=1
    )
    return updated
