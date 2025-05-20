# =============================================================================
# 🚨 Custom Exception Definitions (utils/shared/rmi_exceptions.py)
# -----------------------------------------------------------------------------
# Purpose:             Defines custom exception classes for error handling in the RMI 360 workflow
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.1
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
# Last Updated:        2025-05-20
#
# Description:
#   Contains project-specific exception classes, such as ConfigValidationError, to standardize error handling
#   and improve clarity in exception reporting across the codebase.
#
# File Location:        /utils/shared/rmi_exceptions.py
# Called By:            utils/validators/validate_full_config.py, other validation and config modules
# Notes:                Extend this file with additional exceptions as needed for future features.
# =============================================================================

class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    def __init__(self, message, invalid_keys=None, validation_context=None):
        """
        Args:
            message (str): Error description.
            invalid_keys (list, optional): List of configuration keys that failed validation.
            validation_context (dict, optional): Additional context about the validation failure.
        """
        self.invalid_keys = invalid_keys or []
        self.validation_context = validation_context
        super().__init__(message)

    def __str__(self):
        base = super().__str__()
        details = []

        if self.invalid_keys:
            details.append(f"Invalid keys: {self.invalid_keys}")
        if self.validation_context:
            details.append(f"Context: {self.validation_context}")

        if details:
            return f"{base} — {' | '.join(details)}"
        return base
