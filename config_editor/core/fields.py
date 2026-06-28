# =============================================================================
# 🧾 Form-schema extraction (config_editor/core/fields.py)
# -----------------------------------------------------------------------------
# Turns config.sample.yaml into the form schema the GUI renders — SELF-CONTAINED:
# all field/section metadata is parsed from the sample itself, so there is exactly
# one source of truth.
#
# Annotation convention (in config.yaml comments):
#   Field help  : the inline (end-of-line) comment after a value.
#   @choices[a, b, c] : strict dropdown (value must be one of these).
#   @secret           : password widget; keep out of plaintext.
#   @widget[textarea|number|text|list] : force a widget (type is otherwise inferred).
#   Section header: a line  `# @section: Title | one-line description`  immediately
#                   above a top-level key (raw-scanned at column 0).
# Tags are stripped from the displayed help text.
# =============================================================================

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ruamel.yaml.comments import CommentedMap

from config_editor.core import paths
from config_editor.core.config_io import load_yaml

_TAG_CHOICES = re.compile(r"@choices\[([^\]]*)\]")
_TAG_WIDGET = re.compile(r"@widget\[(\w+)\]")
_TAG_SECRET = re.compile(r"@secret\b")
_TAG_REPEATABLE = re.compile(r"@repeatable\b")
_TAG_ITEMLABEL = re.compile(r"@itemlabel\[(\w+)\]")
_TAG_WHEN = re.compile(r"@when\[([^\]]+)\]")  # @when[other.path=v1,v2] -> active only then
_SECTION_RE = re.compile(r"^#\s*@section:\s*(.+)$")
_TOPKEY_RE = re.compile(r"^([A-Za-z_][\w]*):")

# ESRI field types — a domain constant offered for any record field named "type".
ESRI_FIELD_TYPES = ["TEXT", "DOUBLE", "FLOAT", "SHORT", "LONG", "DATE", "GUID", "BLOB"]


# --- inline help / tags ------------------------------------------------------
def _eol_comment(cm: Mapping, key: str) -> str:
    """Raw end-of-line comment for a key (first line only, '#' stripped)."""
    ca = getattr(cm, "ca", None)
    if ca is None:
        return ""
    slot = ca.items.get(key)
    if not slot or len(slot) < 3 or slot[2] is None:
        return ""
    raw = getattr(slot[2], "value", "") or ""
    return raw.split("\n", 1)[0].lstrip("#").strip()


def _parse_inline_tags(comment: str) -> Tuple[str, Dict[str, Any]]:
    """Split an inline comment into (help_text, meta) where meta may carry
    choices / widget / secret parsed from @tags."""
    meta: Dict[str, Any] = {}
    if not comment:
        return "", meta

    m = _TAG_CHOICES.search(comment)
    if m:
        meta["choices"] = [c.strip() for c in m.group(1).split(",") if c.strip()]
    w = _TAG_WIDGET.search(comment)
    if w:
        meta["widget"] = w.group(1)
    if _TAG_SECRET.search(comment):
        meta["secret"] = True
    if _TAG_REPEATABLE.search(comment):
        meta["repeatable"] = True
    il = _TAG_ITEMLABEL.search(comment)
    if il:
        meta["item_label"] = il.group(1)
    wh = _TAG_WHEN.search(comment)
    if wh and "=" in wh.group(1):
        path, vals = wh.group(1).split("=", 1)
        meta["when"] = {"path": path.strip(),
                        "values": [v.strip() for v in vals.split(",") if v.strip()]}

    help_text = comment
    for rx in (_TAG_CHOICES, _TAG_WIDGET, _TAG_SECRET, _TAG_REPEATABLE, _TAG_ITEMLABEL, _TAG_WHEN):
        help_text = rx.sub("", help_text)
    return help_text.strip(" \t-—|"), meta


# --- section headers (raw scan) ---------------------------------------------
def _clean_doc_block(block: List[str]) -> str:
    """Turn the raw comment block above a section into readable documentation:
    strip leading '#', drop pure divider lines, trim surrounding blanks. Preserves
    internal line breaks / indentation so bullet lists and examples survive."""
    lines: List[str] = []
    for ln in block:
        if ln == "":
            lines.append("")
            continue
        body = ln.lstrip("#")
        if body.startswith(" "):
            body = body[1:]
        body = body.rstrip()
        stripped = body.strip()
        if stripped and set(stripped) <= set("-=—–_*~"):  # divider line
            continue
        lines.append(body)
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def scan_sections(text: str) -> Dict[str, Dict[str, str]]:
    """Map top-level key -> {'title', 'help', 'doc'} from the comment block above it.

    'title'/'help' come from a `# @section: Title | desc` line; 'doc' is the full
    cleaned header comment block (overview/examples) for display in the editor.
    """
    out: Dict[str, Dict[str, str]] = {}
    block: List[str] = []          # consecutive comment/blank lines before a key
    title = ""
    desc = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            m = _SECTION_RE.match(stripped)
            if m:
                payload = m.group(1)
                title, desc = ((payload.split("|", 1) + [""])[:2] if "|" in payload
                               else (payload, ""))
                title, desc = title.strip(), desc.strip()
            else:
                block.append(stripped)
            continue
        if stripped == "":
            if block:
                block.append("")
            continue
        km = _TOPKEY_RE.match(raw)  # column-0 key terminates the header block
        if km:
            doc = _clean_doc_block(block)
            if title or desc or doc:
                out[km.group(1)] = {"title": title, "help": desc, "doc": doc}
        block, title, desc = [], "", ""
    return out


# --- type / widget inference -------------------------------------------------
def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "list"
    if value is None:
        return "null"
    return "str"


def _widget_for(ftype: str, value: Any) -> str:
    if ftype == "bool":
        return "checkbox"
    if ftype in ("int", "float"):
        return "number"
    if ftype == "list":
        return "list"
    if isinstance(value, str) and ("\n" in value or len(value) > 80):
        return "textarea"
    return "text"


def _label(key: str) -> str:
    return key.replace("_", " ").strip()


def _field_node(cm: Mapping, key: str, path: str, value: Any,
                overrides: Dict[str, dict]) -> Dict[str, Any]:
    help_text, tagmeta = _parse_inline_tags(_eol_comment(cm, key))
    ftype = _infer_type(value)
    widget = _widget_for(ftype, value)
    choices = tagmeta.get("choices")
    strict = False

    if tagmeta.get("widget"):
        widget = tagmeta["widget"]
    if tagmeta.get("secret"):
        widget = "secret"
    if choices:
        widget = "select"
        strict = True

    node = {
        "kind": "field", "key": key, "path": path, "label": _label(key),
        "type": ftype, "widget": widget, "help": help_text,
        "default": value, "choices": choices, "strict": strict,
        "when": tagmeta.get("when"),
    }
    if path in overrides:  # programmatic override hook (tests / special cases)
        node.update(overrides[path])
    return node


def _new_item_default(ftype: str, choices) -> Any:
    """Fresh value for a field when the user adds a new collection entry."""
    if choices:
        return choices[0]
    return {"bool": False, "int": None, "float": None, "list": []}.get(ftype, "")


def _collection_node(key: str, path: str, entries: Mapping, help_text: str,
                     meta: Dict[str, Any], overrides: Dict[str, dict]) -> Dict[str, Any]:
    """A @repeatable map of records -> an add/remove collection with an item template.

    The template (record shape) is the union of fields across existing entries, with
    per-field metadata taken from the first entry that defines each field.
    """
    field_order: List[str] = []
    seen = set()
    for rec in entries.values():
        if isinstance(rec, Mapping):
            for fk in rec.keys():
                if fk not in seen:
                    seen.add(fk)
                    field_order.append(fk)

    template: List[Dict[str, Any]] = []
    for fk in field_order:
        repr_entry = next((r for r in entries.values()
                           if isinstance(r, Mapping) and fk in r), None)
        node = _field_node(repr_entry, fk, fk, repr_entry[fk], overrides)
        if fk == "type" and not node.get("choices"):  # ESRI field type dropdown
            node["choices"] = list(ESRI_FIELD_TYPES)
            node["widget"] = "select"
            node["strict"] = True
        node["default"] = _new_item_default(node["type"], node.get("choices"))
        template.append(node)

    item_label = meta.get("item_label") or ("name" if "name" in seen
                                            else (field_order[0] if field_order else "name"))
    return {
        "kind": "collection", "key": key, "path": path, "label": _label(key),
        "help": help_text, "item_label_field": item_label, "item_template": template,
    }


def _walk(cm: Mapping, prefix: str, overrides: Dict[str, dict]) -> List[Dict[str, Any]]:
    children: List[Dict[str, Any]] = []
    for key, value in cm.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            help_text, kmeta = _parse_inline_tags(_eol_comment(cm, key))
            if kmeta.get("repeatable"):
                children.append(_collection_node(key, path, value, help_text, kmeta, overrides))
            else:
                children.append({
                    "kind": "group", "key": key, "path": path, "label": _label(key),
                    "help": help_text, "children": _walk(value, f"{path}.", overrides),
                })
        else:
            children.append(_field_node(cm, key, path, value, overrides))
    return children


def collection_paths(schema: Dict[str, Any]) -> List[str]:
    """Dotted paths of every @repeatable collection (used for replace-on-render)."""
    found: List[str] = []

    def _rec(nodes):
        for n in nodes:
            if n["kind"] == "collection":
                found.append(n["path"])
            elif n["kind"] == "group":
                _rec(n["children"])

    _rec(schema["sections"])
    return found


def build_form_schema(skeleton_path: Optional[Path] = None,
                      overrides: Optional[Dict[str, dict]] = None) -> Dict[str, Any]:
    """Build the GUI form schema from the sample skeleton (self-contained)."""
    skeleton_path = Path(skeleton_path) if skeleton_path else paths.sample_config_path()
    overrides = overrides or {}
    text = skeleton_path.read_text(encoding="utf-8")
    section_meta = scan_sections(text)
    root = load_yaml(skeleton_path)

    sections: List[Dict[str, Any]] = []
    general_fields: List[Dict[str, Any]] = []

    for key, value in root.items():
        meta = section_meta.get(key, {})
        if isinstance(value, Mapping):
            sections.append({
                "kind": "group", "key": key, "path": key,
                "label": meta.get("title") or _label(key),
                "help": meta.get("help", ""),
                "doc": meta.get("doc", ""),
                "children": _walk(value, f"{key}.", overrides),
            })
        else:
            general_fields.append(_field_node(root, key, key, value, overrides))

    if general_fields:
        sections.insert(0, {
            "kind": "group", "key": "general", "path": "general",
            "label": "General", "help": "Top-level settings.", "children": general_fields,
        })

    return {"schema_version": root.get("schema_version"), "sections": sections}


def iter_fields(schema: Dict[str, Any]):
    """Yield concrete field nodes. Collection item-templates are NOT concrete fields
    (they have no fixed path) and are skipped."""
    def _rec(nodes):
        for n in nodes:
            if n["kind"] == "field":
                yield n
            elif n["kind"] == "group":
                yield from _rec(n["children"])
    yield from _rec(schema["sections"])
