# =============================================================================
# 🔧 Configuration Manager (utils/manager/config_manager.py)
# -----------------------------------------------------------------------------
# Purpose:             Loads, validates, and manages access to YAML configuration and project settings for the RMI 360
#                      Workflow Toolbox.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.3.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-11
# Last Updated:        2025-10-30
#
# Description:
#   Centralized configuration manager for the toolbox. Wraps access to key config
#   values, handles expression resolution, schema validation, and integrates tightly
#   with LogManager and PathManager. Supports both CLI and ArcGIS Pro tools.
#
# File Location:        /utils/manager/config_manager.py
# Called By:            ArcGIS tools, orchestrators, log initializers
# Int. Dependencies:    utils/manager/path_manager, utils/manager/log_manager, utils/validate_full_config,
#                       utils/expression_utils, utils/exceptions, utils/validators
# Ext. Dependencies:    yaml, pathlib, typing, os
#
# Documentation:
#   See: docs_legacy/CONFIG_MANAGER.md
#   (Ensure this doc is current; update if needed.)
#
# Notes:
#   - Automatically populates __project_root__ if project_base is passed
#   - Supports .get(), .resolve(), and .validate() access patterns
#   - Integrates tool-specific validators for robust schema enforcement
# =============================================================================

from __future__ import annotations
import os
import yaml
from typing import Any, Optional, Union, Dict, List, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from utils.manager.path_manager import PathManager
    from utils.manager.log_manager import LogManager  
    from utils.manager.progressor_manager import ProgressorManager

from utils.validators.validate_full_config import validate_full_config
from utils.shared.rmi_exceptions import ConfigValidationError
from utils.shared.expression_utils import resolve_expression

from utils.validators import (
    mosaic_processor_validator,
    build_oid_schema_validator,
    create_oid_validator,
    add_images_to_oid_validator,
    assign_group_index_validator,
    calculate_oid_attributes_validator,
    smooth_gps_noise_validator,
    correct_gps_outliers_validator,
    update_linear_and_custom_validator,
    rename_images_validator,
    apply_exif_metadata_validator,
    geocode_images_validator,
    build_oid_footprints_validator,
    deploy_lambda_monitor_validator,
    copy_to_aws_validator,
    generate_oid_service_validator
)

SUPPORTED_SCHEMA_VERSIONS = {"1.3.0"}


class ConfigManager:
    """
    Manages configuration for the RMI 360 Imaging Workflow Toolbox.

    This class loads YAML configuration, validates its schema, and exposes helper
    methods for retrieving nested keys, resolving expressions, and integrating with
    logging and path management. Intended for consistent environment setup across tools.

    Attributes:
        _config (dict): The parsed configuration dictionary.
        _config_path (str): Path to the loaded config file.
        _project_base (Path): Project root directory for resolving outputs.
        _paths (PathManager): Path manager instance for resolving file paths.
        _lm (LogManager): Logger instance for logging messages.

    Typical usage:
        cfg = ConfigManager.from_file("path/to/config.yaml", project_base)
        cfg.validate(tool="enhance")
        log = cfg.get_logger()
        path = cfg.paths.logs
    """
    def __init__(self, config: Dict, config_path: Optional[str] = None, project_base: Optional[Union[str, Path]] = None):
        """
        Initialize ConfigManager from a parsed config dictionary.

        Args:
            config (dict): Parsed YAML configuration.
            config_path (str, optional): Path to the loaded config file.
            project_base (str or Path, optional): Project root directory for resolving outputs.
        """
        self._config = config
        self._config_path = config_path or config.get("__source__")

        # Validate project_base is provided
        if not project_base:
            raise ValueError("Project folder must be supplied when initializing ConfigManager. It is required for path "
                             "resolution and logging operations.")

        self._project_base = Path(project_base).resolve()
        self._config["__project_root__"] = str(self._project_base)

        # Initialize path and log managers
        from utils.manager.path_manager import PathManager
        from utils.manager.log_manager import LogManager
        self._paths = PathManager(project_base=self._project_base, config=self._config)
        self._lm = LogManager(messages=None, config=self._config, path_manager=self._paths)

    @classmethod
    def from_file(cls, path: Optional[str] = None, project_base: Optional[Union[str, Path]] = None, *,
                  messages: Optional[list] = None) -> "ConfigManager":
        """
                  Load a YAML configuration file, validate its schema version, and initialize a ConfigManager.
                  
                  Parameters:
                      path (str, optional): Path to a YAML configuration file. If None, the default config path is used.
                      project_base (str | Path, optional): Root project directory used to initialize project-relative managers.
                      messages (list, optional): Optional message sink passed to the temporary LogManager during loading.
                  
                  Returns:
                      ConfigManager: An initialized configuration manager for the loaded config.
                  
                  Raises:
                      FileNotFoundError: If the configuration file does not exist.
                      ValueError: If the file contains invalid YAML or does not parse into a dictionary.
                      RuntimeError: If the config's schema_version is unsupported or an unexpected error occurs while loading.
                  """
        config_path = path or cls._get_default_config_path(messages)
        config = {}
        from utils.manager.log_manager import LogManager
        lm = LogManager(messages=messages, config=config)

        try:
            # Attempt to open and parse the config file
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                    config["__source__"] = os.path.abspath(config_path)
                    lm.config = config
            except FileNotFoundError:
                lm.error(f"Config file not found: {config_path}", error_type=FileNotFoundError)
                raise
            except yaml.YAMLError as e:
                lm.error(f"Invalid YAML in config file: {e}", error_type=ValueError)
                raise ValueError(f"Invalid YAML in config file: {e}") from e

            # Validate the parsed config is a dictionary
            if not isinstance(config, dict):
                error_msg = f"Config file did not parse into a dictionary. Got {type(config).__name__} instead."
                lm.error(error_msg, error_type=ValueError)
                raise ValueError(error_msg)

            # Validate schema version
            version = config.get("schema_version")
            if version not in SUPPORTED_SCHEMA_VERSIONS:
                error_msg = f"⚠️ Expected schema_version {SUPPORTED_SCHEMA_VERSIONS}, got {version}"
                lm.error(error_msg, error_type=RuntimeError)
                raise RuntimeError(error_msg)

            if config.get("debug_messages", False):
                lm.debug(f"Loaded config from {config['__source__']}")

            return cls(config, config_path, project_base=project_base)

        except (FileNotFoundError, ValueError, RuntimeError):
            # These exceptions are already logged and formatted above
            raise
        except Exception as e:
            # Catch any other unexpected exceptions
            lm.error(f"Unexpected error loading config: {e}", error_type=RuntimeError)
            raise RuntimeError(f"Unexpected error loading config: {e}") from e

    @staticmethod
    def _get_default_config_path(messages: Optional[list] = None) -> str:
        """
        Resolve the default configuration file path from the project's configs directory.
        
        Checks for 'config.yaml' first and falls back to 'config.sample.yaml'; returns the absolute path of the first file found.
        
        Parameters:
            messages (list, optional): Optional message sink used to initialize a temporary LogManager.
        
        Returns:
            str: Absolute path to the selected configuration file.
        
        Raises:
            FileNotFoundError: If neither 'config.yaml' nor 'config.sample.yaml' exists in the configs directory.
        """
        lm = LogManager(messages=messages, config={})
        script_base = Path(__file__).resolve().parent.parent
        temp_paths = PathManager(project_base=Path.cwd(), config={}, script_base=script_base)
        primary = temp_paths.primary_config_path
        fallback = temp_paths.fallback_config_path

        if primary.is_file():
            return str(primary)
        elif fallback.is_file():
            return str(fallback)
        else:
            lm.error("No config.yaml or config.sample.yaml found in /configs", error_type=FileNotFoundError)
            raise FileNotFoundError("No config.yaml or config.sample.yaml found in /configs")

    def validate(self, tool: Optional[str] = None) -> None:
        """
        Run schema validation on the config, optionally scoped to a tool.

        Validates the configuration against the expected schema. If a tool name is provided,
        only the configuration for that specific tool is validated. Otherwise, the entire
        configuration is validated.

        Args:
            tool (str, optional): Name of the tool section to validate (e.g., "enhance_images").

        Raises:
            ValueError: If the configuration fails validation.
        """
        try:
            if tool:
                self.validate_tool_config(tool)
            else:
                result = validate_full_config(self)
                if result is False:
                    raise ValueError("Full config validation failed.")
        except ConfigValidationError as e:
            raise ValueError(f"Validation failed for tool '{tool}': {e}") from e

    def has_section(self, section: str) -> bool:
        """
        Check if a specific section exists in the configuration.

        Args:
            section (str): The top-level section name to check for.

        Returns:
            bool: True if the section exists, False otherwise.

        Examples:
            cfg.has_section("logs")
                True
            cfg.has_section("nonexistent_section")
                False
        """
        return section in self._config and isinstance(self._config[section], dict)

    def get_sections(self) -> List[str]:
        """
        Get a list of all top-level sections in the configuration.

        Returns:
            List[str]: List of section names that are dictionaries.

        Examples:
            cfg.get_sections()
                ['logs', 'project', 'camera', 'camera_offset', 'spatial_ref', 'executables', ...]
        """
        return [k for k, v in self._config.items() if isinstance(v, dict)]

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Access a nested config key using dot notation.

        Traverses the configuration dictionary using the dot-separated key path.
        Returns the default value if any part of the path is not found.

        Args:
            key_path (str): Dot-separated key path, e.g., 'logs.process_log'.
            default (Any): Value to return if key is not found.

        Returns:
            Any: Retrieved value or default if the key path doesn't exist.

        Examples:
            cfg.get("logs.process_log")
                "process_log.txt"
            cfg.get("nonexistent.key", "fallback")
                "fallback"
        """
        keys = key_path.split(".")
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def resolve(self, expr: Union[str, int, float], row: Optional[Dict] = None) -> Any:
        """
        Resolve an expression string using config and optional row context.

        Args:
            expr (str|int|float): Expression to resolve.
            row (dict, optional): Row context for field substitution.

        Returns:
            Any: Resolved expression value.
        """
        return resolve_expression(expr, cfg=self, row=row)

    @property
    def raw(self) -> dict:
        """
        Return the full raw config dictionary.

        Returns:
            dict: The raw parsed configuration.
        """
        return self._config

    @property
    def source_path(self) -> Optional[str]:
        """
        Returns the file path from which the config was loaded.

        Returns:
            str or None: Absolute path to config file or None if unknown.
        """
        return self._config_path

    @property
    def paths(self) -> "PathManager":
        """
        Return the initialized PathManager configured for the project.
        
        Returns:
            PathManager: The project's PathManager instance.
        
        Raises:
            RuntimeError: If the PathManager was not initialized because `project_base` was not provided.
        """
        if self._paths is None:
            raise RuntimeError("PathManager was not initialized — project_base is missing.")
        return self._paths

    def get_logger(self, messages: Optional[list] = None) -> "LogManager":
        """
        Get the configured LogManager and optionally replace its message sink.
        
        If `messages` is provided, sets the logger's message sink to that list before returning it.
        
        Parameters:
            messages (list, optional): Message sink list (ArcPy-style) to attach to the logger.
        
        Returns:
            LogManager: The active LogManager associated with this ConfigManager.
        
        Raises:
            RuntimeError: If the LogManager was not initialized (e.g., `project_base` was not provided).
        """
        if messages and self._lm:
            self._lm.messages = messages
        if not self._lm:
            raise RuntimeError("LogManager was not initialized — project_base is missing.")
        return self._lm

    def get_progressor(self, total: int, label: str = "Processing...", step: int = 1) -> "ProgressorManager":
        """
        Create a ProgressorManager bound to the manager's active LogManager.
        
        Parameters:
            total (int): Total number of steps for the progress tracker.
            label (str): Text label displayed alongside progress.
            step (int): Increment applied on each progress update.
        
        Returns:
            ProgressorManager: Progress tracker instance that logs through the manager's LogManager.
        """
        return ProgressorManager(total=total, label=label, step=step, log_manager=self.get_logger())

    TOOL_VALIDATORS = {
        "mosaic_processor": mosaic_processor_validator.validate,
        "build_oid_schema": build_oid_schema_validator.validate,
        "create_oriented_imagery_dataset": create_oid_validator.validate,
        "add_images_to_oid": add_images_to_oid_validator.validate,
        "assign_group_index": assign_group_index_validator.validate,
        "calculate_oid_attributes": calculate_oid_attributes_validator.validate,
        "smooth_gps_noise": smooth_gps_noise_validator.validate,
        "correct_gps_outliers": correct_gps_outliers_validator.validate,
        "update_linear_and_custom": update_linear_and_custom_validator.validate,
        "rename_images": rename_images_validator.validate,
        "apply_exif_metadata": apply_exif_metadata_validator.validate,
        "geocode_images": geocode_images_validator.validate,
        "build_oid_footprints": build_oid_footprints_validator.validate,
        "deploy_lambda_monitor": deploy_lambda_monitor_validator.validate,
        "copy_to_aws": copy_to_aws_validator.validate,
        "generate_oid_service": generate_oid_service_validator.validate
    }

    def validate_tool_config(self, tool: str):
        """
        Validates the configuration for a specified tool using its registered validator.

        If the tool name is not recognized, logs an error and signals a configuration validation failure.

        Args:
            tool: The name of the tool whose configuration should be validated.

        Raises:
            ConfigValidationError: If the tool name is not registered.
        """
        logger = self.get_logger()

        if tool in self.TOOL_VALIDATORS:
            self.TOOL_VALIDATORS[tool](self)
        else:
            logger.error(f"Unknown tool '{tool}'", error_type=ConfigValidationError)