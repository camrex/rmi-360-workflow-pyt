# =============================================================================
# 👤 Profiles (config_editor/core/profiles.py)
# -----------------------------------------------------------------------------
# A profile is a PARTIAL config (overlay) that prefills org/user-standard values.
# "New from profile" = sample defaults + profile overlay, rendered through the
# comment-preserving skeleton. Profiles live in two places: bundled (shipped with
# the editor, e.g. RMI Valuation) and user (~/.rmi360/config_profiles).
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from config_editor.core import paths
from config_editor.core.config_io import (
    dump_yaml,
    extract_values,
    load_yaml,
    render_from_skeleton,
)


@dataclass(frozen=True)
class ProfileRef:
    name: str
    path: Path
    source: str  # "bundled" | "user"


def _iter_profile_files(directory: Path, source: str) -> List[ProfileRef]:
    if not directory.is_dir():
        return []
    refs = []
    for p in sorted(directory.glob("*.yaml")):
        refs.append(ProfileRef(name=p.stem, path=p, source=source))
    return refs


def list_profiles() -> List[ProfileRef]:
    """All available profiles (user profiles shadow bundled ones of the same name)."""
    bundled = _iter_profile_files(paths.bundled_profiles_dir(), "bundled")
    user = _iter_profile_files(paths.user_profiles_dir(), "user")
    by_name: Dict[str, ProfileRef] = {r.name: r for r in bundled}
    by_name.update({r.name: r for r in user})  # user overrides bundled
    return [by_name[n] for n in sorted(by_name)]


def find_profile(name: str) -> Optional[ProfileRef]:
    for ref in list_profiles():
        if ref.name == name:
            return ref
    return None


def load_profile(name: str) -> Dict[str, Any]:
    """Return a profile's overlay as a plain dict, or {} if not found."""
    ref = find_profile(name)
    if ref is None:
        return {}
    return extract_values(load_yaml(ref.path)) or {}


def save_profile(name: str, values: Dict[str, Any]) -> Path:
    """Write a user profile (partial overlay). Returns the written path."""
    out_dir = paths.user_profiles_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}.yaml"
    dump_yaml(values, out_path)
    return out_path


def new_config_from_profile(profile_name: Optional[str] = None,
                            skeleton_path: Optional[Path] = None,
                            extra_values: Optional[Dict[str, Any]] = None):
    """Build a fresh, fully-commented config: sample defaults + profile + extra.

    Returns a CommentedMap ready to dump. ``extra_values`` (e.g. project-specific
    edits already entered) overlay on top of the profile.
    """
    skeleton_path = skeleton_path or paths.sample_config_path()
    overlay: Dict[str, Any] = {}
    if profile_name:
        overlay.update(load_profile(profile_name))
    if extra_values:
        # deep-merge extra over profile
        overlay = _deep_merge(overlay, extra_values)
    return render_from_skeleton(overlay, skeleton_path)


def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(out.get(k), dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
