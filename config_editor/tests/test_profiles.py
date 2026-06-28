from config_editor.core import config_io as cio
from config_editor.core import paths, profiles


def test_bundled_rmi_profile_listed():
    names = [r.name for r in profiles.list_profiles()]
    assert "rmi_valuation" in names


def test_load_profile_returns_overlay():
    overlay = profiles.load_profile("rmi_valuation")
    assert overlay["project"]["client"] == "RMI Valuation, LLC"


def test_new_config_from_profile_applies_overlay_and_keeps_comments():
    cfg = profiles.new_config_from_profile("rmi_valuation")
    values = cio.extract_values(cfg)
    assert values["project"]["client"] == "RMI Valuation, LLC"
    # sample defaults still present where the profile didn't touch them
    assert "s3_bucket_panos_unsecured" in values["aws"]
    # comments survived
    out = cio.dump_yaml_str(cfg)
    assert sum(1 for l in out.splitlines() if l.strip().startswith("#")) > 500


def test_extra_values_override_profile():
    cfg = profiles.new_config_from_profile("rmi_valuation",
                                           extra_values={"project": {"slug": "RMI25320"}})
    values = cio.extract_values(cfg)
    assert values["project"]["slug"] == "RMI25320"
    assert values["project"]["client"] == "RMI Valuation, LLC"  # profile still applied


def test_save_and_load_user_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "user_profiles_dir", lambda: tmp_path)
    profiles.save_profile("my_org", {"aws": {"region": "us-west-2"}})
    assert profiles.load_profile("my_org") == {"aws": {"region": "us-west-2"}}
    # user profile shows up in the listing
    assert any(r.name == "my_org" and r.source == "user" for r in profiles.list_profiles())
