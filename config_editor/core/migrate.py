# =============================================================================
# ⬆️ Config upgrade / migration (config_editor/core/migrate.py)
# -----------------------------------------------------------------------------
# Upgrade = load the TARGET version's sample skeleton (new structure + comments +
# defaults), overlay the old config's values, apply explicit rename/remove rules
# for keys that moved between versions, and set schema_version. Output preserves
# the new structure and comments while keeping the user's values. A report lists
# exactly what changed so the upgrade is reviewable.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from config_editor.core import paths
from config_editor.core.config_io import extract_values, load_yaml, render_from_skeleton


@dataclass
class UpgradeReport:
    source_version: Any = None
    target_version: Any = None
    added_keys: List[str] = field(default_factory=list)      # new in target, given defaults
    removed_keys: List[str] = field(default_factory=list)    # in old, gone from target
    renamed: List[str] = field(default_factory=list)         # "old -> new"
    carried_over: int = 0                                     # user leaf values preserved


@dataclass
class UpgradeResult:
    config: Any                  # CommentedMap ready to dump
    report: UpgradeReport


# --- dotted-path helpers -----------------------------------------------------
def _flatten(d: Any, prefix: str = "") -> Dict[str, Any]:
    """Flatten nested mappings to {dotted.path: leaf_value}. Lists are leaves."""
    out: Dict[str, Any] = {}
    if isinstance(d, Mapping):
        for k, v in d.items():
            out.update(_flatten(v, f"{prefix}{k}."))
    else:
        out[prefix.rstrip(".")] = d
    return out


def _get(d: Dict[str, Any], dotted: str):
    cur: Any = d
    for part in dotted.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None, False
        cur = cur[part]
    return cur, True


def _set(d: Dict[str, Any], dotted: str, value: Any) -> None:
    cur = d
    parts = dotted.split(".")
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _del(d: Dict[str, Any], dotted: str) -> bool:
    cur = d
    parts = dotted.split(".")
    for part in parts[:-1]:
        cur = cur.get(part) if isinstance(cur, Mapping) else None
        if not isinstance(cur, dict):
            return False
    return cur.pop(parts[-1], _MISSING) is not _MISSING


_MISSING = object()


def apply_rules(values: Dict[str, Any], rules: Optional[List[dict]]) -> List[str]:
    """Apply transform rules in place. Supported ops: rename, remove, set.
    Returns a list of human-readable rename descriptions."""
    renamed: List[str] = []
    for rule in rules or []:
        op = rule.get("op")
        if op == "rename":
            src, dst = rule["from"], rule["to"]
            val, ok = _get(values, src)
            if ok:
                _set(values, dst, val)
                _del(values, src)
                renamed.append(f"{src} -> {dst}")
        elif op == "remove":
            _del(values, rule["path"])
        elif op == "set":
            _set(values, rule["path"], rule["value"])
    return renamed


def _prune_empty(d: Any) -> Any:
    """Drop keys whose value is an empty mapping (recursively). Used after rules so
    a section emptied by a rename/remove is not re-emitted as ``section: {}``."""
    if not isinstance(d, Mapping):
        return d
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, Mapping):
            pruned = _prune_empty(v)
            if pruned:
                out[k] = pruned
        else:
            out[k] = v
    return out


def upgrade(old_values: Dict[str, Any],
            target_skeleton_path: Optional[Path] = None,
            rules: Optional[List[dict]] = None) -> UpgradeResult:
    """Upgrade ``old_values`` onto the target skeleton, returning config + report."""
    target_skeleton_path = target_skeleton_path or paths.sample_config_path()

    old_values = dict(extract_values(old_values))  # defensive copy, plain dict
    source_version = old_values.get("schema_version")

    renamed = apply_rules(old_values, rules)
    old_values = _prune_empty(old_values)

    skeleton = load_yaml(target_skeleton_path)
    target_defaults = extract_values(skeleton)
    target_version = target_defaults.get("schema_version")

    # Always adopt the target schema_version.
    old_values["schema_version"] = target_version

    old_leaves = set(_flatten(old_values))
    target_leaves = set(_flatten(target_defaults))

    added = sorted(target_leaves - old_leaves)
    removed = sorted(old_leaves - target_leaves)
    carried = len(old_leaves & target_leaves)

    # @repeatable collections are user data — keep the old config's exact entry set
    # rather than merging the skeleton's example entries on top.
    from config_editor.core import fields
    replace_paths = set(fields.collection_paths(fields.build_form_schema(target_skeleton_path)))
    config = render_from_skeleton(old_values, target_skeleton_path, replace_paths=replace_paths)

    report = UpgradeReport(
        source_version=source_version,
        target_version=target_version,
        added_keys=added,
        removed_keys=removed,
        renamed=renamed,
        carried_over=carried,
    )
    return UpgradeResult(config=config, report=report)
