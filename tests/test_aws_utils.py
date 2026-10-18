"""Unit tests for utils/shared/aws_utils.py — sessions come only from a NAMED AWS
profile (aws.profile, else AWS_PROFILE), never the default chain.

No network: sessions are built against a temporary AWS config file with fake static
keys and only their resolved credentials are inspected. (Requires the ArcGIS Pro
env to import utils.shared.)
"""

from unittest.mock import MagicMock

import pytest

from utils.shared import aws_utils


@pytest.fixture
def aws_env(tmp_path, monkeypatch):
    """Isolated AWS config: profile 'proj' with fake keys; env keys that must be ignored."""
    config = tmp_path / "config"
    config.write_text(
        "[profile proj]\n"
        "aws_access_key_id = AKIAPROFILEFAKE\n"
        "aws_secret_access_key = profilesecretfake\n"
        "region = us-east-2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAENVFAKE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "envsecretfake")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_PROFILE", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    return monkeypatch


def make_cfg(profile=None, region="us-east-2"):
    values = {"aws.profile": profile, "aws.region": region}
    cfg = MagicMock()
    cfg.get_logger.return_value = MagicMock()
    cfg.get.side_effect = lambda k, d=None: values.get(k, d)
    return cfg


# --- resolve_profile_name ---------------------------------------------------

def test_explicit_profile_wins_over_env(aws_env):
    aws_env.setenv("AWS_PROFILE", "from-env")
    assert aws_utils.resolve_profile_name("proj") == "proj"


def test_env_profile_used_when_blank(aws_env):
    aws_env.setenv("AWS_PROFILE", "from-env")
    assert aws_utils.resolve_profile_name("") == "from-env"
    assert aws_utils.resolve_profile_name(None) == "from-env"


def test_no_profile_refuses(aws_env):
    with pytest.raises(RuntimeError, match="No AWS profile"):
        aws_utils.resolve_profile_name(None)


@pytest.mark.parametrize("name", ["default", "Default", " DEFAULT "])
def test_default_profile_refused(aws_env, name):
    with pytest.raises(RuntimeError, match="'default' is refused"):
        aws_utils.resolve_profile_name(name)


def test_default_profile_refused_from_env(aws_env):
    aws_env.setenv("AWS_PROFILE", "default")
    with pytest.raises(RuntimeError, match="'default' is refused"):
        aws_utils.resolve_profile_name(None)


# --- profile_session -----------------------------------------------------------

def test_session_uses_profile_not_env_keys(aws_env):
    session = aws_utils.profile_session("proj")
    assert session.profile_name == "proj"
    creds = session.get_credentials()
    assert creds.access_key == "AKIAPROFILEFAKE"   # not AKIAENVFAKE


def test_session_region_override(aws_env):
    assert aws_utils.profile_session("proj", "us-west-2").region_name == "us-west-2"
    assert aws_utils.profile_session("proj").region_name == "us-east-2"  # from the profile


def test_missing_profile_points_to_sso_login(aws_env):
    with pytest.raises(RuntimeError, match="aws sso login --profile nope"):
        aws_utils.profile_session("nope")


# --- get_boto3_session -------------------------------------------------------------

def test_get_boto3_session_reads_cfg(aws_env):
    session = aws_utils.get_boto3_session(make_cfg(profile="proj", region="us-west-2"))
    assert session.profile_name == "proj" and session.region_name == "us-west-2"


def test_get_boto3_session_falls_back_to_env(aws_env):
    aws_env.setenv("AWS_PROFILE", "proj")
    assert aws_utils.get_boto3_session(make_cfg(profile="")).profile_name == "proj"


def test_get_boto3_session_refuses_without_profile(aws_env):
    cfg = make_cfg(profile=None)
    with pytest.raises(RuntimeError, match="No AWS profile"):
        aws_utils.get_boto3_session(cfg)
    cfg.get_logger.return_value.error.assert_called()


# --- other entry points share the same rules ---------------------------------------

def test_upload_script_session_uses_profile(aws_env):
    from utils.shared import s3_upload_helpers
    session = s3_upload_helpers.resolve_session("proj", "us-east-2")
    assert session.get_credentials().access_key == "AKIAPROFILEFAKE"
    with pytest.raises(RuntimeError, match="No AWS profile"):
        s3_upload_helpers.resolve_session(None)


def test_s3_utils_client_uses_profile(aws_env):
    from utils import s3_utils
    seen = {}

    def fake_profile_session(profile=None, region=None):
        seen["profile"], seen["region"] = profile, region
        return MagicMock()

    aws_env.setattr(aws_utils, "profile_session", fake_profile_session)
    s3_utils._client("proj", "us-west-2")
    assert seen == {"profile": "proj", "region": "us-west-2"}


def test_s3_utils_client_refuses_without_profile(aws_env):
    from utils import s3_utils
    with pytest.raises(RuntimeError, match="No AWS profile"):
        s3_utils._client()
