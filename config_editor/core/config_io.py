# =============================================================================
# 🧩 Comment-preserving config I/O (config_editor/core/config_io.py)
# -----------------------------------------------------------------------------
# The editor never hand-serializes YAML. It loads config.sample.yaml as a living
# TEMPLATE (comments + structure + defaults intact via ruamel round-trip), sets
# values onto that object, and dumps. Comments survive because ruamel binds them
# to the nodes. This single mechanism powers new-config, edit, and upgrade.
# =============================================================================

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


def _represent_none(representer, _data):
    """Render None as the literal ``null`` (ruamel defaults to empty), matching the
    sample's consistent ``key: null`` style."""
    return representer.represent_scalar("tag:yaml.org,2002:null", "null")


def _yaml() -> YAML:
    """A round-trip YAML configured to reproduce the sample faithfully."""
    y = YAML()  # round-trip mode preserves comments, key order, anchors
    y.preserve_quotes = True
    y.width = 4096  # never re-wrap long scalars or comment lines
    y.indent(mapping=2, sequence=4, offset=2)
    y.representer.add_representer(type(None), _represent_none)
    return y


def _normalize(text: str) -> str:
    """Strip trailing whitespace per line so output is deterministic and clean.

    ruamel drops whitespace-only "blank" lines in some positions but keeps truly
    empty ones, so normalizing on load makes round-trips stable and lint-clean
    regardless of the source file's trailing-whitespace hygiene.
    """
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def load_yaml(path: str | Path) -> CommentedMap:
    """Load a YAML file in round-trip mode (comments/structure preserved)."""
    text = Path(path).read_text(encoding="utf-8")
    return _yaml().load(_normalize(text))


def loads_yaml(text: str) -> CommentedMap:
    """Load YAML from a string (round-trip mode)."""
    return _yaml().load(_normalize(text))


def dump_yaml(data: Any, path: str | Path) -> None:
    """Write a (possibly commented) structure to disk, preserving layout."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        _yaml().dump(data, f)


def dump_yaml_str(data: Any) -> str:
    """Serialize to a string (used for diffs / round-trip tests)."""
    buf = io.StringIO()
    _yaml().dump(data, buf)
    return buf.getvalue()


def extract_values(data: Any) -> Any:
    """Strip comments/round-trip wrappers, returning plain dict/list/scalars.

    Used to hand the GUI a clean value tree to bind to, decoupled from layout.
    """
    if isinstance(data, Mapping):
        return {k: extract_values(v) for k, v in data.items()}
    if isinstance(data, list):
        return [extract_values(v) for v in data]
    return data


def overlay_values(target: CommentedMap, values: Mapping[str, Any],
                   replace_paths: Optional[set] = None, _prefix: str = "") -> CommentedMap:
    """Deep-merge ``values`` onto ``target`` IN PLACE, preserving target layout.

    Rules:
      - path in replace_paths -> replace target[k] wholesale (used for @repeatable
        collections, where the user's entry set is authoritative — add/remove work)
      - mapping vs mapping     -> recurse (a sub-map's untouched keys keep comments)
      - everything else        -> replace target[k] with the new value
      - keys only in values    -> added to target (no comment; user's own additions)
    """
    replace_paths = replace_paths or set()
    for key, new_val in values.items():
        path = f"{_prefix}{key}"
        cur = target.get(key, None) if hasattr(target, "get") else None
        if path in replace_paths:
            target[key] = new_val
        elif isinstance(cur, Mapping) and isinstance(new_val, Mapping):
            overlay_values(cur, new_val, replace_paths, f"{path}.")
        else:
            target[key] = new_val
    return target


def render_from_skeleton(values: Mapping[str, Any], skeleton_path: str | Path,
                         replace_paths: Optional[set] = None) -> CommentedMap:
    """Produce a fully-commented config by overlaying ``values`` on a fresh load
    of the skeleton (typically config.sample.yaml).

    This is the heart of the editor:
      - new config  : values = profile overlay (or {})
      - edit config : values = the user's current values (comments restored, any
                      new skeleton keys filled with their documented defaults)
      - upgrade     : skeleton = the NEW version's sample; values = old config

    ``replace_paths`` (dotted) are overlaid wholesale instead of merged — pass the
    @repeatable collection paths so entry add/remove is reflected exactly.
    """
    skeleton = load_yaml(skeleton_path)
    return overlay_values(skeleton, values, replace_paths=replace_paths)
