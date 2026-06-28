# =============================================================================
# 🛤️ Corridor Thinning Validator (utils/validators/corridor_thinning_validator.py)
# -----------------------------------------------------------------------------
# Purpose:             Validate the optional corridor_thinning config section and
#                      the top-level thinning_mode switch.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Description:
#   The corridor_thinning section is OPTIONAL (the stage tools expose all values on
#   their dialogs and carry code defaults). This validator only fails when present
#   values are malformed, so it is safe to run during full-config validation even
#   when pre-thinning is not used.
#
# File Location:        /utils/validators/corridor_thinning_validator.py
# Called By:            utils/manager/config_manager.py (TOOL_VALIDATORS / full config)
# =============================================================================

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from utils.shared.rmi_exceptions import ConfigValidationError

if TYPE_CHECKING:
    from utils.manager.config_manager import ConfigManager

__all__ = ["validate"]


def validate(cfg: "ConfigManager") -> bool:
    """Validate thinning_mode + the optional corridor_thinning section.

    Returns True when valid. Raises ConfigValidationError (via logger.error) on a
    malformed present value. A missing corridor_thinning section is valid.
    """
    logger = cfg.get_logger()

    # thinning_mode (top-level, optional; default "post")
    mode = cfg.get("thinning_mode", "post")
    if mode is not None and str(mode).strip().lower() not in ("post", "pre"):
        logger.error(
            f"thinning_mode must be 'post' or 'pre', got {mode!r}.",
            error_type=ConfigValidationError,
        )

    section = cfg.get("corridor_thinning")
    if section is None:
        # Pre-thin not configured here — fine. Tools supply values on the dialog.
        if str(mode).strip().lower() == "pre":
            logger.warning(
                "thinning_mode is 'pre' but no corridor_thinning section is present; "
                "ensure the manifest path is supplied on the tool dialog.",
                indent=1,
            )
        return True

    if not isinstance(section, dict):
        logger.error("corridor_thinning: expected a mapping/dict.", error_type=ConfigValidationError)
        return False

    # wkid
    wkid = section.get("wkid")
    if wkid is not None and not isinstance(wkid, int):
        logger.error(
            f"corridor_thinning.wkid: expected an integer WKID, got {type(wkid).__name__}.",
            error_type=ConfigValidationError,
        )

    # eps_miles
    eps = section.get("eps_miles")
    if eps is not None and (not isinstance(eps, (int, float)) or eps <= 0):
        logger.error(
            f"corridor_thinning.eps_miles: expected a positive number, got {eps!r}.",
            error_type=ConfigValidationError,
        )

    # thin thresholds
    thin = section.get("thin", {})
    if thin and isinstance(thin, dict):
        thr = thin.get("threshold_meters")
        if thr is not None and (not isinstance(thr, (int, float)) or thr <= 0):
            logger.error(
                f"corridor_thinning.thin.threshold_meters: expected a positive number, got {thr!r}.",
                error_type=ConfigValidationError,
            )
        trim = thin.get("trim_meters")
        if trim is not None and (not isinstance(trim, (int, float)) or trim < 0):
            logger.error(
                f"corridor_thinning.thin.trim_meters: expected a non-negative number, got {trim!r}.",
                error_type=ConfigValidationError,
            )

    # filename_regex compiles
    rgx = section.get("filename_regex")
    if rgx:
        try:
            re.compile(rgx)
        except re.error as e:
            logger.error(
                f"corridor_thinning.filename_regex: invalid regular expression ({e}).",
                error_type=ConfigValidationError,
            )

    return True
