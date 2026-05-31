from __future__ import annotations

import csv
import math
import os
import shutil
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import arcpy

from utils.manager.config_manager import ConfigManager

__all__ = ["prepare_delivery_subset"]


def _haversine_meters(x1: float, y1: float, x2: float, y2: float) -> float:
    r = 6371000.0
    p1 = math.radians(y1)
    p2 = math.radians(y2)
    dp = math.radians(y2 - y1)
    dl = math.radians(x2 - x1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return r * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _safe_float(value) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_delivery_oid_path(oid_fc: str) -> str:
    oid_gdb = os.path.dirname(oid_fc)
    oid_name = os.path.splitext(os.path.basename(oid_fc))[0]
    return os.path.join(oid_gdb, f"{oid_name}_delivery")


def _fetch_records(oid_fc: str) -> List[Dict]:
    fields = {f.name for f in arcpy.ListFields(oid_fc)}
    read_fields = ["OID@", "ImagePath", "AcquisitionDate", "SHAPE@XY"]

    optional_fields = ["Reel", "MP_Pre", "MP_Num"]
    present_optional = [f for f in optional_fields if f in fields]
    read_fields.extend(present_optional)

    records: List[Dict] = []
    with arcpy.da.SearchCursor(oid_fc, read_fields) as cursor:
        for row in cursor:
            row_map = dict(zip(read_fields, row))
            xy = row_map.get("SHAPE@XY") or (None, None)
            x_val, y_val = xy if isinstance(xy, tuple) else (None, None)
            image_path = row_map.get("ImagePath")
            records.append(
                {
                    "oid": row_map.get("OID@"),
                    "image_path": image_path,
                    "filename": os.path.basename(image_path) if image_path else None,
                    "acq": row_map.get("AcquisitionDate"),
                    "reel": row_map.get("Reel") if "Reel" in row_map else None,
                    "mp_pre": row_map.get("MP_Pre") if "MP_Pre" in row_map else None,
                    "mp_num": _safe_float(row_map.get("MP_Num") if "MP_Num" in row_map else None),
                    "x": _safe_float(x_val),
                    "y": _safe_float(y_val),
                }
            )
    return records


def _choose_spacing_ids(records: Sequence[Dict], cfg: ConfigManager, logger) -> Tuple[set, List[str]]:
    spacing_cfg = cfg.get("delivery_subset.spacing_selector", {}) or {}
    notes: List[str] = []

    target_spacing = float(cfg.get("delivery_subset.target_spacing_meters"))
    source_spacing = float(cfg.get("delivery_subset.source_capture_spacing_meters"))
    mode = spacing_cfg.get("mode", "auto_stride")
    stride = spacing_cfg.get("stride_override")
    if mode == "auto_stride":
        stride = max(1, int(round(target_spacing / source_spacing)))
    else:
        if stride is None:
            stride = 1
            notes.append("stride_override was not set; defaulted to 1.")
        else:
            stride = int(stride)

    group_by_reel = bool(spacing_cfg.get("group_by_reel", True))
    validate_distance = bool(spacing_cfg.get("validate_distance", True))
    tolerance_pct = float(spacing_cfg.get("tolerance_percent", 10.0))
    max_adjust = int(spacing_cfg.get("max_local_adjustments_per_pick", 2))
    correction = spacing_cfg.get("correction_strategy", "nearest_candidate")
    on_fail = cfg.get("delivery_subset.on_validation_failure", "warn_and_continue")

    groups: Dict[str, List[Dict]] = {}
    if group_by_reel:
        for rec in records:
            key = str(rec.get("reel") or "__NO_REEL__")
            groups.setdefault(key, []).append(rec)
    else:
        groups["__ALL__"] = list(records)

    selected_ids = set()
    lower = target_spacing * (1.0 - tolerance_pct / 100.0)
    upper = target_spacing * (1.0 + tolerance_pct / 100.0)
    max_warning_samples = 8

    for group_name, group_records in groups.items():
        group_records = sorted(group_records, key=lambda r: (r.get("acq") is None, r.get("acq"), r.get("oid")))
        if not group_records:
            continue

        failure_count = 0
        failure_samples: List[Tuple[int, float]] = []

        chosen_idx: List[int] = list(range(0, len(group_records), stride))
        if not chosen_idx or chosen_idx[0] != 0:
            chosen_idx.insert(0, 0)

        if validate_distance and len(chosen_idx) > 1:
            for pos in range(1, len(chosen_idx)):
                prev_idx = chosen_idx[pos - 1]
                cur_idx = chosen_idx[pos]

                def _distance_for(idx: int) -> Optional[float]:
                    prev = group_records[prev_idx]
                    cur = group_records[idx]
                    if None in (prev.get("x"), prev.get("y"), cur.get("x"), cur.get("y")):
                        return None
                    return _haversine_meters(prev["x"], prev["y"], cur["x"], cur["y"])

                distance = _distance_for(cur_idx)
                if distance is None:
                    notes.append(f"{group_name}: spacing validation skipped (missing coordinates) at index {cur_idx}.")
                    continue

                if lower <= distance <= upper:
                    continue

                best_idx = cur_idx
                best_dist = abs(distance - target_spacing)

                candidates: List[int] = []
                if correction == "forward_only":
                    end = min(len(group_records) - 1, cur_idx + max_adjust)
                    candidates = list(range(cur_idx + 1, end + 1))
                else:
                    start = max(prev_idx + 1, cur_idx - max_adjust)
                    end = min(len(group_records) - 1, cur_idx + max_adjust)
                    candidates = list(range(start, end + 1))

                for cand_idx in candidates:
                    cand_dist = _distance_for(cand_idx)
                    if cand_dist is None:
                        continue
                    cand_err = abs(cand_dist - target_spacing)
                    if cand_err < best_dist:
                        best_dist = cand_err
                        best_idx = cand_idx

                if best_idx != cur_idx:
                    chosen_idx[pos] = best_idx
                    adjusted_dist = _distance_for(best_idx)
                    notes.append(
                        f"{group_name}: adjusted pick from index {cur_idx} to {best_idx} "
                        f"(distance {distance:.2f}m -> {adjusted_dist:.2f}m)."
                    )
                    distance = adjusted_dist

                if distance is not None and not (lower <= distance <= upper):
                    msg = (
                        f"{group_name}: could not satisfy spacing tolerance at index {chosen_idx[pos]} "
                        f"(distance={distance:.2f}m, target={target_spacing:.2f}m, tolerance={tolerance_pct:.1f}%)."
                    )
                    if on_fail == "error":
                        logger.error(msg, error_type=RuntimeError)
                    else:
                        failure_count += 1
                        if len(failure_samples) < max_warning_samples:
                            failure_samples.append((chosen_idx[pos], distance))
                            notes.append(msg)

        for idx in sorted(set(chosen_idx)):
            selected_ids.add(group_records[idx]["oid"])

        if on_fail != "error" and failure_count > 0:
            sample_text = ", ".join(
                [f"idx {idx} ({dist:.2f}m)" for idx, dist in failure_samples]
            )
            logger.warning(
                f"{group_name}: {failure_count} spacing pick(s) were outside tolerance. "
                f"Samples: {sample_text}",
                indent=1,
            )
            notes.append(
                f"{group_name}: {failure_count} spacing pick(s) outside tolerance; "
                f"sample_count={len(failure_samples)}"
            )

    logger.info(f"Delivery spacing selector kept {len(selected_ids)} OID row(s).", indent=1)
    return selected_ids, notes


def _choose_mp_ids(records: Sequence[Dict], cfg: ConfigManager, logger) -> set:
    mp_cfg = cfg.get("delivery_subset.mp_range_selector", {}) or {}
    ranges = mp_cfg.get("ranges", []) or []
    selected = set()
    for rec in records:
        rec_pre = str(rec.get("mp_pre") or "").strip()
        rec_mp = rec.get("mp_num")
        if not rec_pre or rec_mp is None:
            continue
        for item in ranges:
            pre = str(item.get("mp_pre") or "").strip()
            lo = _safe_float(item.get("min"))
            hi = _safe_float(item.get("max"))
            if not pre or lo is None or hi is None:
                continue
            if rec_pre == pre and lo <= rec_mp <= hi:
                selected.add(rec["oid"])
                break
    logger.info(f"Delivery MP range selector kept {len(selected)} OID row(s).", indent=1)
    return selected


def _estimate_reel_median_spacing(group_records: Sequence[Dict]) -> Optional[float]:
    ordered = sorted(group_records, key=lambda r: (r.get("acq") is None, r.get("acq"), r.get("oid")))
    if len(ordered) < 2:
        return None

    distances: List[float] = []
    for idx in range(1, len(ordered)):
        prev = ordered[idx - 1]
        cur = ordered[idx]
        if None in (prev.get("x"), prev.get("y"), cur.get("x"), cur.get("y")):
            continue
        dist = _haversine_meters(prev["x"], prev["y"], cur["x"], cur["y"])
        if dist <= 0:
            continue
        distances.append(dist)

    if not distances:
        return None

    raw_median = statistics.median(distances)
    if raw_median <= 0:
        return None

    # Trim extreme outliers (stops/teleports) while preserving normal cadence variation.
    lower = raw_median * 0.25
    upper = raw_median * 4.0
    filtered = [d for d in distances if lower <= d <= upper]
    if not filtered:
        filtered = distances

    return float(statistics.median(filtered))


def _validate_source_capture_spacing(records: Sequence[Dict], cfg: ConfigManager, logger) -> None:
    configured = float(cfg.get("delivery_subset.source_capture_spacing_meters"))
    max_dev_pct = float(cfg.get("delivery_subset.capture_spacing_validation.max_deviation_percent", 25.0))
    min_reels = int(cfg.get("delivery_subset.capture_spacing_validation.min_reels_with_estimate", 1))
    on_fail = cfg.get("delivery_subset.on_validation_failure", "warn_and_continue")

    groups: Dict[str, List[Dict]] = {}
    for rec in records:
        reel_key = str(rec.get("reel") or "__NO_REEL__")
        groups.setdefault(reel_key, []).append(rec)

    reel_medians: List[float] = []
    for reel_key, group in groups.items():
        reel_med = _estimate_reel_median_spacing(group)
        if reel_med is not None:
            reel_medians.append(reel_med)
        else:
            logger.info(f"Capture spacing estimate skipped for reel '{reel_key}' (insufficient valid geometry).", indent=2)

    if len(reel_medians) < min_reels:
        logger.warning(
            "Capture spacing validation skipped: insufficient per-reel spacing estimates.",
            indent=1,
        )
        return

    observed = float(statistics.median(reel_medians))
    deviation_pct = abs(observed - configured) / configured * 100.0

    summary = (
        f"Capture spacing check: configured={configured:.2f}m, observed_median={observed:.2f}m "
        f"across {len(reel_medians)} reel(s), deviation={deviation_pct:.1f}%."
    )

    if deviation_pct > max_dev_pct:
        message = (
            f"{summary} This exceeds max deviation ({max_dev_pct:.1f}%). "
            "Consider updating delivery_subset.source_capture_spacing_meters."
        )
        if on_fail == "error":
            logger.error(message, error_type=RuntimeError)
        else:
            logger.warning(message, indent=1)
    else:
        logger.info(summary, indent=1)


def _write_manifest(manifest_path: Path, selected_records: Sequence[Dict], notes: Sequence[str]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "oid",
                "filename",
                "local_path",
                "reel",
                "acquisition_date",
                "mp_pre",
                "mp_num",
            ],
        )
        writer.writeheader()
        for rec in selected_records:
            writer.writerow(
                {
                    "oid": rec.get("oid"),
                    "filename": rec.get("filename") or "",
                    "local_path": rec.get("image_path") or "",
                    "reel": rec.get("reel") or "",
                    "acquisition_date": rec.get("acq") or "",
                    "mp_pre": rec.get("mp_pre") or "",
                    "mp_num": "" if rec.get("mp_num") is None else rec.get("mp_num"),
                }
            )

    if notes:
        note_path = manifest_path.with_suffix(".notes.txt")
        with open(note_path, "w", encoding="utf-8") as f:
            for note in notes:
                f.write(f"{note}\n")


def _materialize_subset_folder(subset_dir: Path, selected_records: Sequence[Dict], logger) -> None:
    subset_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for rec in selected_records:
        src = rec.get("image_path")
        filename = rec.get("filename")
        if not src or not filename:
            continue
        src_path = Path(src)
        if not src_path.is_file():
            continue
        dst_path = subset_dir / filename
        shutil.copy2(src_path, dst_path)
        copied += 1
    logger.info(f"Materialized {copied} image(s) into subset folder: {subset_dir}", indent=1)


def prepare_delivery_subset(cfg: ConfigManager, oid_fc: str, params: Dict) -> Dict:
    logger = cfg.get_logger()
    subset_cfg = cfg.get("delivery_subset", {}) or {}
    if not subset_cfg.get("enabled", False):
        logger.info("Delivery subset is disabled. Using master OID for delivery steps.", indent=1)
        return {"enabled": False}

    cfg.validate(tool="delivery_subset")

    logger.custom("Preparing delivery subset OID and manifest...", emoji="📦", indent=1)
    records = _fetch_records(oid_fc)
    if not records:
        logger.error("No records found in OID; cannot prepare delivery subset.", error_type=RuntimeError)
        return {"enabled": False, "error": "No records found in OID"}

    _validate_source_capture_spacing(records, cfg, logger)

    spacing_enabled = bool(cfg.get("delivery_subset.spacing_selector.enabled", True))
    mp_enabled = bool(cfg.get("delivery_subset.mp_range_selector.enabled", False))

    selector_sets: List[set] = []
    notes: List[str] = []

    if spacing_enabled:
        spacing_ids, spacing_notes = _choose_spacing_ids(records, cfg, logger)
        selector_sets.append(spacing_ids)
        notes.extend(spacing_notes)

    if mp_enabled:
        selector_sets.append(_choose_mp_ids(records, cfg, logger))

    if selector_sets:
        keep_ids = set.intersection(*selector_sets)
    else:
        keep_ids = {r["oid"] for r in records}

    if not keep_ids:
        logger.error("Delivery subset produced zero records. Check selector configuration.", error_type=RuntimeError)
        return {"enabled": False, "error": "Zero records after selection"}

    delivery_oid_fc = _build_delivery_oid_path(oid_fc)
    if arcpy.Exists(delivery_oid_fc):
        arcpy.management.Delete(delivery_oid_fc)
    arcpy.management.Copy(oid_fc, delivery_oid_fc)

    with arcpy.da.UpdateCursor(delivery_oid_fc, ["OID@"]) as cursor:
        for row in cursor:
            if row[0] not in keep_ids:
                cursor.deleteRow()

    selected_records = [r for r in records if r["oid"] in keep_ids]
    selected_records = sorted(selected_records, key=lambda r: (r.get("acq") is None, r.get("acq"), r.get("oid")))

    output_cfg = cfg.get("delivery_subset.output", {}) or {}
    strategy = output_cfg.get("strategy", "manifest")
    manifest_filename = output_cfg.get("manifest_filename", "delivery_subset_manifest.csv")
    subset_folder_name = output_cfg.get("subset_folder_name", "delivery_subset")

    manifest_path = cfg.paths.logs / manifest_filename
    _write_manifest(manifest_path, selected_records, notes)

    delivery_local_dir = None
    if strategy == "subset_folder":
        delivery_local_dir = cfg.paths.panos / subset_folder_name
        _materialize_subset_folder(delivery_local_dir, selected_records, logger)

    params["delivery_oid_fc"] = delivery_oid_fc
    params["delivery_manifest_path"] = str(manifest_path)
    if delivery_local_dir is not None:
        params["delivery_local_dir"] = str(delivery_local_dir)

    logger.success(
        f"Delivery subset prepared: kept {len(selected_records)} of {len(records)} row(s); "
        f"manifest={manifest_path.name}",
        indent=1,
    )

    return {
        "enabled": True,
        "delivery_oid_fc": delivery_oid_fc,
        "delivery_manifest_path": str(manifest_path),
        "delivery_local_dir": str(delivery_local_dir) if delivery_local_dir else None,
        "kept_count": len(selected_records),
        "total_count": len(records),
    }