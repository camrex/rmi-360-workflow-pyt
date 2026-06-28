# =============================================================================
# ✅ Standalone config validation (config_editor/core/validate.py)
# -----------------------------------------------------------------------------
# Arcpy-free structural validation for the editor: schema_version support,
# completeness vs the sample skeleton, stray keys, and unfilled "<PLACEHOLDER>"
# values. The set of supported schema versions is read straight from the toolbox's
# config_manager.py via ast (single source of truth, no import side effects).
#
# Deep, semantic validation (expression resolution, cross-field rules) lives in
# utils/validators and runs inside ArcGIS Pro; this layer gives fast inline
# feedback while editing.
# =============================================================================

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Mapping, Optional, Set

from config_editor.core import paths

_PLACEHOLDER = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Issue:
    level: str   # "error" | "warning"
    path: str
    message: str


def read_supported_versions(config_manager_path: Optional[Path] = None) -> Set[str]:
    """Parse SUPPORTED_SCHEMA_VERSIONS from config_manager.py without importing it."""
    src_path = config_manager_path or paths.config_manager_source()
    try:
        tree = ast.parse(Path(src_path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SUPPORTED_SCHEMA_VERSIONS":
                    try:
                        value = ast.literal_eval(node.value)
                        return {str(v) for v in value}
                    except (ValueError, TypeError):
                        return set()
    return set()


def _placeholder_leaves(data: Any, prefix: str = "") -> List[str]:
    out: List[str] = []
    if isinstance(data, Mapping):
        for k, v in data.items():
            out.extend(_placeholder_leaves(v, f"{prefix}{k}."))
    elif isinstance(data, str) and _PLACEHOLDER.search(data):
        out.append(prefix.rstrip("."))
    return out


def validate_structure(values: Mapping[str, Any],
                       skeleton_values: Mapping[str, Any],
                       supported_versions: Optional[Set[str]] = None) -> List[Issue]:
    """Validate a config's values against the sample skeleton.

    Checks: schema_version present & supported; all skeleton top-level sections
    present; no unknown top-level sections; no unfilled <PLACEHOLDER> values.
    """
    if supported_versions is None:
        supported_versions = read_supported_versions()

    issues: List[Issue] = []

    version = values.get("schema_version")
    if version is None:
        issues.append(Issue("error", "schema_version", "Missing schema_version."))
    elif supported_versions and str(version) not in supported_versions:
        issues.append(Issue(
            "error", "schema_version",
            f"Unsupported schema_version '{version}'. Supported: {sorted(supported_versions)}. "
            "Use Upgrade to migrate.",
        ))

    skeleton_top = set(skeleton_values.keys())
    values_top = set(values.keys())

    for missing in sorted(skeleton_top - values_top):
        issues.append(Issue("error", missing, f"Missing required top-level section '{missing}'."))

    for unknown in sorted(values_top - skeleton_top):
        issues.append(Issue("warning", unknown,
                            f"Unknown top-level section '{unknown}' (not in the sample schema)."))

    for path in _placeholder_leaves(values):
        issues.append(Issue("warning", path, "Unfilled placeholder value (still '<...>')."))

    return issues


def has_errors(issues: List[Issue]) -> bool:
    return any(i.level == "error" for i in issues)
