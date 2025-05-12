# =============================================================================
# 🧠 Config Manager Utility (utils/manager/config_manager.py)
# -----------------------------------------------------------------------------
# Purpose:             Loads, validates, and manages access to YAML configuration
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-11
#
# Description:
#   Centralized configuration manager for the toolbox. Wraps access to key config
#   values, handles expression resolution, schema validation, and integrates tightly
#   with LogManager and PathManager. Supports both CLI and ArcGIS Pro tools.
#
# File Location:        /utils/manager/config_manager.py
# Called By:            ArcGIS tools, orchestrators, log initializers
# Int. Dependencies:    utils/path_manager, utils/log_manager, utils/validate_config
# Ext. Dependencies:    yaml, pathlib, typing
#
# Documentation:
#   See: docs_legacy/CONFIG_MANAGER.md
#
# Notes:
#   - Automatically populates __project_root__ if project_base is passed
#   - Supports .get(), .resolve(), and .validate() access patterns
# =============================================================================
import os
import yaml
from typing import Any, Optional, Union, Dict, List
from pathlib import Path
from utils.validate_config import validate_full_config, validate_tool_config
from utils.expression_utils import resolve_expression
from utils.manager.path_manager import PathManager
from utils.manager.log_manager import LogManager

EXPECTED_SCHEMA_VERSION = "1.0.1"


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
        self._project_base = Path(project_base).resolve() if project_base else None
        if self._project_base:
            self._config["__project_root__"] = str(self._project_base)
        self._paths: Optional[PathManager] = PathManager(project_base=self._project_base, config=self._config) \
            if self._project_base else None
        self._lm: Optional[LogManager] = LogManager(messages=None, config=self._config, path_manager=self._paths) \
            if self._paths else None

    @classmethod
    def from_file(cls, path: Optional[str] = None, project_base: Optional[Union[str, Path]] = None, *,
                  messages: Optional[list] = None) -> "ConfigManager":
        """
        Class method to load a config file, validate schema version, and return a ConfigManager.

        Args:
            path (str, optional): Path to a config YAML. Uses default fallback if None.
            project_base (str or Path, optional): Path to the root project directory.
            messages (list, optional): Optional list for ArcPy-style messages.

        Returns:
            ConfigManager: Initialized configuration manager.

        Raises:
            FileNotFoundError: If the config file doesn't exist.
            ValueError: If the config file doesn't parse into a dictionary.
            RuntimeError: If the schema version doesn't match the expected version.
        """
        config_path = path or cls._get_default_config_path(messages)
        config = {}
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
            if version != EXPECTED_SCHEMA_VERSION:
                error_msg = f"⚠️ Expected schema_version {EXPECTED_SCHEMA_VERSION}, got {version}"
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
        Resolve default config path using PathManager.

        Checks for 'config.yaml' or falls back to 'config.sample.yaml' in the configs directory.
        Uses a temporary PathManager to locate the config files.

        Args:
            messages (list, optional): Optional list for ArcPy-style messages.

        Raises:
            FileNotFoundError: If neither config.yaml nor config.sample.yaml exists.

        Returns:
            str: Absolute path to the selected config file.
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

    def validate(self, tool: Optional[str] = None, messages: Optional[list] = None) -> None:
        """
        Run schema validation on the config, optionally scoped to a tool.

        Validates the configuration against the expected schema. If a tool name is provided,
        only the configuration for that specific tool is validated. Otherwise, the entire
        configuration is validated.

        Args:
            tool (str, optional): Name of the tool section to validate (e.g., "enhance_images").
            messages (list, optional): Optional ArcPy-style messages list for logging validation results.

        Raises:
            ValueError: If the configuration fails validation.
        """
        if tool:
            validate_tool_config(self._config, tool, messages=messages)
        else:
            validate_full_config(self._config, messages=messages)

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
        return resolve_expression(expr, config=self._config, row=row)

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
    def paths(self) -> PathManager:
        """
        Access the initialized PathManager.

        Raises:
            RuntimeError: If PathManager was not initialized.

        Returns:
            PathManager: Resolved project/script-aware path helper.
        """
        if self._paths is None:
            raise RuntimeError("PathManager was not initialized — project_base is missing.")
        return self._paths

    def get_logger(self, messages: Optional[list] = None) -> LogManager:
        """
        Return a LogManager instance, optionally updating its message sink.

        If a messages list is provided and a logger already exists, the logger's
        message sink is updated with the new list. If no logger exists yet, a
        RuntimeError is raised.

        Args:
            messages (list, optional): ArcPy-style message list for logging output.

        Returns:
            LogManager: Instance tied to the current config and path.

        Raises:
            RuntimeError: If LogManager was not initialized (project_base is missing).
        """
        if messages and self._lm:
            self._lm.messages = messages
        if not self._lm:
            raise RuntimeError("LogManager was not initialized — project_base is missing.")
        return self._lm
