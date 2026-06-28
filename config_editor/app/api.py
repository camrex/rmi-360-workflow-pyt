# =============================================================================
# 🔌 Editor backend API (config_editor/app/api.py)
# -----------------------------------------------------------------------------
# The bridge the web UI calls (via pywebview js_api). Every method returns
# JSON-serializable data and delegates to the headless core. Methods take explicit
# values/paths so the whole API is testable without a window; file dialogs are thin
# helpers that use the attached pywebview window when present.
# =============================================================================

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from config_editor.core import aws_check, config_io, fields, migrate, migrations, paths, profiles, validate


def _jsonable(value: Any) -> Any:
    """Coerce ruamel scalar/seq subclasses to plain JSON-native types."""
    return json.loads(json.dumps(value, default=str))


class ConfigEditorAPI:
    def __init__(self, skeleton_path: Optional[Path] = None, window=None):
        self.skeleton_path = Path(skeleton_path) if skeleton_path else paths.sample_config_path()
        self.window = window  # pywebview window, set by main.py for dialogs

    # --- schema & profiles --------------------------------------------------
    def get_schema(self) -> Dict[str, Any]:
        """Form schema (sections/fields/help) derived from the sample skeleton."""
        return _jsonable(fields.build_form_schema(self.skeleton_path))

    def _replace_paths(self) -> set:
        """@repeatable collection paths — overlaid wholesale so add/remove sticks."""
        return set(fields.collection_paths(fields.build_form_schema(self.skeleton_path)))

    def list_profiles(self) -> List[Dict[str, str]]:
        return [{"name": r.name, "source": r.source} for r in profiles.list_profiles()]

    # --- create / open ------------------------------------------------------
    def new_config(self, profile: Optional[str] = None) -> Dict[str, Any]:
        """Values for a new config = sample defaults + optional profile overlay."""
        cfg = profiles.new_config_from_profile(profile, skeleton_path=self.skeleton_path)
        return {"values": _jsonable(config_io.extract_values(cfg))}

    def open_config(self, path: str) -> Dict[str, Any]:
        """Load an existing config's values for editing; flag if it needs upgrade."""
        values = config_io.extract_values(config_io.load_yaml(path))
        supported = validate.read_supported_versions()
        version = values.get("schema_version")
        needs_upgrade = bool(supported) and str(version) not in supported
        return {
            "values": _jsonable(values),
            "path": str(path),
            "schema_version": _jsonable(version),
            "needs_upgrade": needs_upgrade,
        }

    # --- validate / upgrade -------------------------------------------------
    def validate(self, values: Dict[str, Any]) -> List[Dict[str, str]]:
        skeleton_values = config_io.extract_values(config_io.load_yaml(self.skeleton_path))
        issues = validate.validate_structure(values, skeleton_values)
        return [{"level": i.level, "path": i.path, "message": i.message} for i in issues]

    def check_aws(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """Verify AWS auth: keyring populated / keys set, then authenticate (STS)
        and probe whether configured buckets exist. Makes live AWS calls."""
        checks = aws_check.check_aws_auth(values)
        rows = [{"name": c.name, "status": c.status, "detail": c.detail} for c in checks]
        return {"summary": aws_check.summarize(checks), "checks": rows}

    def set_keyring(self, service_name: str, access_key_id: str, secret_access_key: str) -> Dict[str, Any]:
        """Store AWS credentials in the OS keyring (not in config.yaml)."""
        c = aws_check.set_keyring_credentials(service_name, access_key_id, secret_access_key)
        return {"status": c.status, "detail": c.detail}

    def upgrade(self, values: Dict[str, Any]) -> Dict[str, Any]:
        rules = migrations.rules_for(values.get("schema_version"))
        result = migrate.upgrade(values, target_skeleton_path=self.skeleton_path, rules=rules)
        r = result.report
        return {
            "values": _jsonable(config_io.extract_values(result.config)),
            "report": {
                "source_version": _jsonable(r.source_version),
                "target_version": _jsonable(r.target_version),
                "added_keys": r.added_keys,
                "removed_keys": r.removed_keys,
                "renamed": r.renamed,
                "carried_over": r.carried_over,
            },
        }

    # --- preview / save -----------------------------------------------------
    def preview(self, values: Dict[str, Any]) -> str:
        """Live YAML preview: values rendered through the comment-preserving skeleton."""
        return config_io.dump_yaml_str(
            config_io.render_from_skeleton(values, self.skeleton_path, replace_paths=self._replace_paths())
        )

    def save(self, values: Dict[str, Any], path: str) -> Dict[str, Any]:
        """Render values onto the skeleton (comments preserved) and write to ``path``."""
        cfg = config_io.render_from_skeleton(values, self.skeleton_path, replace_paths=self._replace_paths())
        config_io.dump_yaml(cfg, path)
        return {"ok": True, "path": str(path)}

    # --- dialogs (thin; require a window) -----------------------------------
    def open_dialog(self) -> Optional[str]:
        if self.window is None:
            return None
        import webview
        result = self.window.create_file_dialog(
            webview.OPEN_DIALOG, file_types=("YAML (*.yaml;*.yml)", "All files (*.*)"))
        return result[0] if result else None

    def save_dialog(self, suggested: str = "config.yaml") -> Optional[str]:
        if self.window is None:
            return None
        import webview
        return self.window.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=suggested,
            file_types=("YAML (*.yaml;*.yml)", "All files (*.*)")) or None
