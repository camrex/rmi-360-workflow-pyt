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


def test_open_config_round_trip(tmp_path):
    api = _api()
    out = tmp_path / "c.yaml"
    api.save(api.new_config()["values"], str(out))
    opened = api.open_config(str(out))
    assert opened["needs_upgrade"] is False
    assert "aws" in opened["values"]
