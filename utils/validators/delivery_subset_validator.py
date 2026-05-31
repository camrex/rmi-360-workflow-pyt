from __future__ import annotations
from typing import TYPE_CHECKING

from utils.shared.rmi_exceptions import ConfigValidationError

if TYPE_CHECKING:
    from utils.manager.config_manager import ConfigManager


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _to_float(value) -> float | None:
    if _is_number(value):
        return float(value)
    return None


def validate(cfg: "ConfigManager") -> bool:
    logger = cfg.get_logger()
    error_count = 0

    block = cfg.get("delivery_subset", None)
    if block is None:
        return True

    if not isinstance(block, dict):
        logger.error("delivery_subset must be a mapping.", error_type=ConfigValidationError)
        return False

    enabled = block.get("enabled", False)
    if not isinstance(enabled, bool):
        logger.error("delivery_subset.enabled must be a boolean.", error_type=ConfigValidationError)
        error_count += 1

    source_spacing = block.get("source_capture_spacing_meters")
    target_spacing = block.get("target_spacing_meters")
    source_spacing_num = _to_float(source_spacing)
    target_spacing_num = _to_float(target_spacing)

    if source_spacing_num is None or source_spacing_num <= 0:
        logger.error(
            "delivery_subset.source_capture_spacing_meters must be a positive number.",
            error_type=ConfigValidationError,
        )
        error_count += 1

    if target_spacing_num is None or target_spacing_num <= 0:
        logger.error(
            "delivery_subset.target_spacing_meters must be a positive number.",
            error_type=ConfigValidationError,
        )
        error_count += 1

    if source_spacing_num is not None and target_spacing_num is not None:
        if target_spacing_num < source_spacing_num:
            logger.error(
                "delivery_subset.target_spacing_meters must be greater than or equal to "
                "delivery_subset.source_capture_spacing_meters.",
                error_type=ConfigValidationError,
            )
            error_count += 1

    spacing_selector = block.get("spacing_selector", {})
    if not isinstance(spacing_selector, dict):
        logger.error("delivery_subset.spacing_selector must be a mapping.", error_type=ConfigValidationError)
        error_count += 1
        spacing_selector = {}

    spacing_enabled = spacing_selector.get("enabled", False)
    if not isinstance(spacing_enabled, bool):
        logger.error("delivery_subset.spacing_selector.enabled must be a boolean.", error_type=ConfigValidationError)
        error_count += 1

    mode = spacing_selector.get("mode", "auto_stride")
    if mode not in ("auto_stride", "fixed_stride"):
        logger.error(
            "delivery_subset.spacing_selector.mode must be one of: auto_stride, fixed_stride.",
            error_type=ConfigValidationError,
        )
        error_count += 1

    stride_override = spacing_selector.get("stride_override", None)
    if mode == "fixed_stride":
        if not isinstance(stride_override, int) or isinstance(stride_override, bool) or stride_override <= 0:
            logger.error(
                "delivery_subset.spacing_selector.stride_override must be a positive integer when mode is fixed_stride.",
                error_type=ConfigValidationError,
            )
            error_count += 1
    else:
        if stride_override is not None and (
            not isinstance(stride_override, int) or isinstance(stride_override, bool) or stride_override <= 0
        ):
            logger.error(
                "delivery_subset.spacing_selector.stride_override must be null or a positive integer.",
                error_type=ConfigValidationError,
            )
            error_count += 1

    for key in ("group_by_reel", "validate_distance"):
        value = spacing_selector.get(key)
        if not isinstance(value, bool):
            logger.error(f"delivery_subset.spacing_selector.{key} must be a boolean.", error_type=ConfigValidationError)
            error_count += 1

    tolerance_percent = spacing_selector.get("tolerance_percent")
    tolerance_percent_num = _to_float(tolerance_percent)
    if tolerance_percent_num is None or tolerance_percent_num < 0:
        logger.error(
            "delivery_subset.spacing_selector.tolerance_percent must be a number greater than or equal to 0.",
            error_type=ConfigValidationError,
        )
        error_count += 1

    local_adjustments = spacing_selector.get("max_local_adjustments_per_pick")
    if not isinstance(local_adjustments, int) or isinstance(local_adjustments, bool) or local_adjustments < 0:
        logger.error(
            "delivery_subset.spacing_selector.max_local_adjustments_per_pick must be an integer >= 0.",
            error_type=ConfigValidationError,
        )
        error_count += 1

    correction_strategy = spacing_selector.get("correction_strategy")
    if correction_strategy not in ("nearest_candidate", "forward_only"):
        logger.error(
            "delivery_subset.spacing_selector.correction_strategy must be one of: nearest_candidate, forward_only.",
            error_type=ConfigValidationError,
        )
        error_count += 1

    mp_selector = block.get("mp_range_selector", {})
    if not isinstance(mp_selector, dict):
        logger.error("delivery_subset.mp_range_selector must be a mapping.", error_type=ConfigValidationError)
        error_count += 1
        mp_selector = {}

    mp_enabled = mp_selector.get("enabled", False)
    if not isinstance(mp_enabled, bool):
        logger.error("delivery_subset.mp_range_selector.enabled must be a boolean.", error_type=ConfigValidationError)
        error_count += 1

    ranges = mp_selector.get("ranges", [])
    if not isinstance(ranges, list):
        logger.error("delivery_subset.mp_range_selector.ranges must be a list.", error_type=ConfigValidationError)
        error_count += 1
        ranges = []

    if mp_enabled and len(ranges) == 0:
        logger.error(
            "delivery_subset.mp_range_selector.ranges must contain at least one range when mp_range_selector.enabled is true.",
            error_type=ConfigValidationError,
        )
        error_count += 1

    for i, entry in enumerate(ranges):
        context = f"delivery_subset.mp_range_selector.ranges[{i}]"
        if not isinstance(entry, dict):
            logger.error(f"{context} must be a mapping.", error_type=ConfigValidationError)
            error_count += 1
            continue

        mp_pre = entry.get("mp_pre")
        min_value = entry.get("min")
        max_value = entry.get("max")

        if not isinstance(mp_pre, str) or not mp_pre.strip():
            logger.error(f"{context}.mp_pre must be a non-empty string.", error_type=ConfigValidationError)
            error_count += 1

        if not _is_number(min_value):
            logger.error(f"{context}.min must be a number.", error_type=ConfigValidationError)
            error_count += 1

        if not _is_number(max_value):
            logger.error(f"{context}.max must be a number.", error_type=ConfigValidationError)
            error_count += 1

        min_num = _to_float(min_value)
        max_num = _to_float(max_value)
        if min_num is not None and max_num is not None and min_num > max_num:
            logger.error(f"{context}.min cannot be greater than {context}.max.", error_type=ConfigValidationError)
            error_count += 1

    output_block = block.get("output", {})
    if not isinstance(output_block, dict):
        logger.error("delivery_subset.output must be a mapping.", error_type=ConfigValidationError)
        error_count += 1
        output_block = {}

    strategy = output_block.get("strategy")
    if strategy not in ("manifest", "subset_folder"):
        logger.error(
            "delivery_subset.output.strategy must be one of: manifest, subset_folder.",
            error_type=ConfigValidationError,
        )
        error_count += 1

    for key in ("manifest_filename", "subset_folder_name"):
        val = output_block.get(key)
        if not isinstance(val, str) or not val.strip():
            logger.error(f"delivery_subset.output.{key} must be a non-empty string.", error_type=ConfigValidationError)
            error_count += 1

    on_failure = block.get("on_validation_failure")
    if on_failure not in ("warn_and_continue", "error"):
        logger.error(
            "delivery_subset.on_validation_failure must be one of: warn_and_continue, error.",
            error_type=ConfigValidationError,
        )
        error_count += 1

    if bool(enabled) and not bool(spacing_enabled) and not bool(mp_enabled):
        logger.error(
            "delivery_subset.enabled is true but no selectors are enabled. Enable spacing_selector or mp_range_selector.",
            error_type=ConfigValidationError,
        )
        error_count += 1

    return error_count == 0
