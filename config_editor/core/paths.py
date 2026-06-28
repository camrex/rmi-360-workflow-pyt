# =============================================================================
# 📁 Path resolution (config_editor/core/paths.py)
# -----------------------------------------------------------------------------
# Locates the toolbox's config.sample.yaml (the editor's template), the configs
# dir, the config_manager source (single source of truth for supported schema
# versions), and the bundled/user profile directories.
# =============================================================================

from __future__ import annotations

from pathlib import Path

# config_editor/core/paths.py -> config_editor -> <toolbox root>
TOOLBOX_ROOT = Path(__file__).resolve().parents[2]
CONFIG_EDITOR_ROOT = Path(__file__).resolve().parents[1]


def sample_config_path() -> Path:
    """Path to config.sample.yaml — the comment-bearing template."""
    return TOOLBOX_ROOT / "configs" / "config.sample.yaml"


def configs_dir() -> Path:
    return TOOLBOX_ROOT / "configs"


def config_manager_source() -> Path:
    """Source file holding SUPPORTED_SCHEMA_VERSIONS (parsed, not imported, to stay
    arcpy-free)."""
    return TOOLBOX_ROOT / "utils" / "manager" / "config_manager.py"


def bundled_profiles_dir() -> Path:
    """Profiles shipped with the editor (e.g. the RMI Valuation org profile)."""
    return CONFIG_EDITOR_ROOT / "profiles"


def user_profiles_dir() -> Path:
    """Per-user profiles directory (created on demand)."""
    d = Path.home() / ".rmi360" / "config_profiles"
    return d
