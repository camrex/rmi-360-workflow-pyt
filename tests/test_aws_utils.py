"""Unit tests for aws_utils.get_aws_credentials.

Credential source is driven by aws.auth_mode (instance | keyring | config).
Keyring is monkeypatched; no real keyring/network is touched. (Requires the
ArcGIS Pro env to import utils.shared.)
"""

from unittest.mock import MagicMock

import pytest

from utils.shared import aws_utils


def make_cfg(auth_mode="config", access_key=None, secret_key=None,
             service_name="rmi_s3"):
    values = {
        "aws.auth_mode": auth_mode,
        "aws.keyring_service_name": service_name,
        "aws.access_key": access_key,
        "aws.secret_key": secret_key,
    }
    cfg = MagicMock()
    cfg.get_logger.return_value = MagicMock()
    cfg.get.side_effect = lambda k, d=None: values.get(k, d)
    return cfg


def _mock_keyring(monkeypatch, values):
    km = MagicMock()
    km.get_password.side_effect = values
    monkeypatch.setattr(aws_utils, "keyring", km)
    return km


def test_keyring_via_auth_mode(monkeypatch):
    # auth_mode=keyring is the single switch that triggers keyring resolution.
    cfg = make_cfg(auth_mode="keyring", service_name="aws_s3")
    km = _mock_keyring(monkeypatch, ["AKIAFAKE", "SECRETFAKE"])
    assert aws_utils.get_aws_credentials(cfg) == ("AKIAFAKE", "SECRETFAKE")
    # lowercase item names, under the configured service name
    km.get_password.assert_any_call("aws_s3", "aws_access_key_id")
    km.get_password.assert_any_call("aws_s3", "aws_secret_access_key")


def test_plaintext_config(monkeypatch):
    cfg = make_cfg(auth_mode="config", access_key="AKIAFAKE", secret_key="SECRETFAKE")
    # keyring must not be consulted in config mode
    monkeypatch.setattr(aws_utils, "keyring",
                        MagicMock(get_password=MagicMock(side_effect=AssertionError("keyring used"))))
    assert aws_utils.get_aws_credentials(cfg) == ("AKIAFAKE", "SECRETFAKE")


def test_keyring_missing_raises(monkeypatch):
    cfg = make_cfg(auth_mode="keyring")
    _mock_keyring(monkeypatch, [None, None])
    with pytest.raises(RuntimeError, match="keyring"):
        aws_utils.get_aws_credentials(cfg)


def test_config_missing_raises():
    cfg = make_cfg(auth_mode="config", access_key=None, secret_key=None)
    with pytest.raises(RuntimeError, match="config"):
        aws_utils.get_aws_credentials(cfg)
