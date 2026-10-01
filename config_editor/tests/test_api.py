import json

from config_editor.app.api import ConfigEditorAPI
from config_editor.core import config_io


def _api():
    return ConfigEditorAPI()


def test_get_schema_is_jsonable():
    schema = _api().get_schema()
    json.dumps(schema)  # must not raise (no ruamel scalar leakage)
    assert schema["schema_version"]
    assert any(s["key"] == "aws" for s in schema["sections"])


def test_list_profiles_includes_rmi():
    assert any(p["name"] == "rmi_valuation" for p in _api().list_profiles())


def test_new_config_with_profile():
    res = _api().new_config("rmi_valuation")
    json.dumps(res)
    assert res["values"]["project"]["client"] == "RMI Valuation, LLC"


def test_validate_flags_placeholders():
    res = _api().new_config()
    issues = _api().validate(res["values"])
    assert any(i["level"] == "warning" and "placeholder" in i["message"].lower() for i in issues)
    assert not any(i["level"] == "error" for i in issues)  # structurally complete


def test_upgrade_reports():
    res = _api().upgrade({"schema_version": "1.3.1", "project": {"slug": "OLD"}})
    assert res["report"]["target_version"]  # adopts current
    assert len(res["report"]["added_keys"]) > 20
    assert res["values"]["project"]["slug"] == "OLD"


def test_save_preserves_comments(tmp_path):
    api = _api()
    res = api.new_config("rmi_valuation")
    res["values"]["project"]["slug"] = "RMI25320"
    out = tmp_path / "config.yaml"
    saved = api.save(res["values"], str(out))
    assert saved["ok"]
    text = out.read_text(encoding="utf-8")
    assert "RMI25320" in text
    assert sum(1 for l in text.splitlines() if l.strip().startswith("#")) > 500  # comments kept


def test_preview_renders_yaml():
    api = _api()
    yaml_text = api.preview(api.new_config()["values"])
    assert "schema_version" in yaml_text
    assert "# " in yaml_text  # commented


def test_save_reflects_collection_add_remove(tmp_path):
    api = _api()
    v = api.new_config()["values"]
    cf = v["oid_schema_template"]["custom_fields"]
    del cf["custom2"]                                              # remove Track
    cf["custom9"] = {"name": "Zone", "type": "TEXT", "length": 8, "alias": "Zone"}  # add
    out = tmp_path / "config.yaml"
    api.save(v, str(out))

    from config_editor.core import config_io
    reloaded = config_io.extract_values(config_io.load_yaml(out))["oid_schema_template"]["custom_fields"]
    assert set(reloaded.keys()) == {"custom1", "custom9"}         # exactly the user's set
    assert reloaded["custom9"]["name"] == "Zone"
    assert reloaded["custom1"]["name"] == "RR"
    # rest of the file's comments are intact
    assert sum(1 for l in out.read_text(encoding="utf-8").splitlines() if l.strip().startswith("#")) > 500


def test_numeric_wkid_saved_as_int(tmp_path):
    # The web form submits text widgets as strings. local_proj_wkid is declared
    # @type[int] in the sample, so a string "6455" must be written as an int 6455 —
    # otherwise the runtime validator rejects spatial_ref.pcs_horizontal_wkid
    # ("must be int, got str") since it resolves from project.local_proj_wkid.
    api = _api()
    v = api.new_config()["values"]
    v["project"]["local_proj_wkid"] = "6455"          # as the GUI would submit it
    out = tmp_path / "config.yaml"
    api.save(v, str(out))

    reloaded = config_io.extract_values(config_io.load_yaml(out))
    assert reloaded["project"]["local_proj_wkid"] == 6455
    assert isinstance(reloaded["project"]["local_proj_wkid"], int)
    # serialized without quotes
    line = next(l for l in out.read_text(encoding="utf-8").splitlines()
                if l.strip().startswith("local_proj_wkid:"))
    assert "'6455'" not in line and '"6455"' not in line


def test_unfilled_wkid_placeholder_preserved(tmp_path):
    # An unparseable placeholder must pass through untouched (so the structural
    # placeholder warning still fires) rather than being coerced/dropped silently.
    api = _api()
    v = api.new_config()["values"]
    assert isinstance(v["project"]["local_proj_wkid"], str)  # sample placeholder
    out = tmp_path / "config.yaml"
    api.save(v, str(out))
    reloaded = config_io.extract_values(config_io.load_yaml(out))
    assert reloaded["project"]["local_proj_wkid"] == v["project"]["local_proj_wkid"]


def test_open_config_round_trip(tmp_path):
    api = _api()
    out = tmp_path / "c.yaml"
    api.save(api.new_config()["values"], str(out))
    opened = api.open_config(str(out))
    assert opened["needs_upgrade"] is False
    assert "aws" in opened["values"]


class _FakeWindow:
    """Stands in for the pywebview window: create_file_dialog returns a tuple of
    paths (its real contract, even for SAVE dialogs) or None on cancel."""

    def __init__(self, result):
        self._result = result

    def create_file_dialog(self, *args, **kwargs):
        return self._result


def test_save_dialog_returns_single_path_string():
    # WinForms SAVE returns a 1-tuple; passing it through unwrapped made the JS
    # side call save(values, [path]) -> Path(list) TypeError -> silent no-save.
    api = ConfigEditorAPI(window=_FakeWindow((r"C:\somewhere\config.yaml",)))
    assert api.save_dialog() == r"C:\somewhere\config.yaml"


def test_save_dialog_cancel_returns_none():
    api = ConfigEditorAPI(window=_FakeWindow(None))
    assert api.save_dialog() is None


def test_open_dialog_returns_single_path_string():
    api = ConfigEditorAPI(window=_FakeWindow((r"C:\somewhere\config.yaml",)))
    assert api.open_dialog() == r"C:\somewhere\config.yaml"
