# =============================================================================
# 🧪 Deploy Secured Test Set Unit Tests (tests/test_deploy_secured_test_set.py)
# -----------------------------------------------------------------------------
# Purpose:             Guards for the secured-storage test-set deploy util
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Author:              RMI Valuation, LLC
# Created:             2026-10-01
#
# Notes:
#   - Stubs arcpy/arcgis (MagicMock) so production modules import without ArcGIS.
#   - S3 clients are MagicMocks; no AWS calls are made.
# =============================================================================

import sys
from unittest.mock import MagicMock

for _esri_mod in ("arcpy", "arcgis", "arcgis.gis"):
    sys.modules.setdefault(_esri_mod, MagicMock())

import pytest

import utils.deploy_secured_test_set as dst


class _ClientError(Exception):
    """Minimal stand-in for botocore's ClientError (carries .response)."""

    def __init__(self, code):
        super().__init__(f"An error occurred ({code})")
        self.response = {"Error": {"Code": code}}


@pytest.fixture
def logger():
    return MagicMock()


@pytest.fixture
def cfg(logger):
    c = MagicMock()
    c.get_logger.return_value = logger
    return c


@pytest.mark.parametrize("code", ["404", "NoSuchBucket", "NotFound"])
def test_ensure_bucket_creates_only_when_not_found(code, logger):
    s3 = MagicMock()
    s3.head_bucket.side_effect = _ClientError(code)
    assert dst._ensure_bucket(s3, "b", "us-east-2", logger, dry_run=False) == "created"
    s3.create_bucket.assert_called_once()


def test_ensure_bucket_forbidden_raises_instead_of_creating(logger):
    s3 = MagicMock()
    s3.head_bucket.side_effect = _ClientError("403")
    with pytest.raises(RuntimeError):
        dst._ensure_bucket(s3, "b", "us-east-2", logger, dry_run=False)
    s3.create_bucket.assert_not_called()


def test_ensure_bucket_forbidden_dry_run_warns(logger):
    s3 = MagicMock()
    s3.head_bucket.side_effect = _ClientError("403")
    assert dst._ensure_bucket(s3, "b", "us-east-2", logger, dry_run=True) == "inaccessible"
    assert logger.warning.called


@pytest.mark.parametrize("count", [0, -5])
def test_non_positive_test_count_rejected(cfg, count):
    with pytest.raises(ValueError):
        dst.deploy_secured_test_set(cfg, "oid_fc", test_bucket="b", source_bucket="src", test_count=count)


def _run_live_publish(monkeypatch, cfg, sync_result):
    monkeypatch.setattr(dst, "get_boto3_session", lambda cfg: MagicMock())
    monkeypatch.setattr(dst, "_ensure_bucket", lambda *a, **kw: "exists")
    monkeypatch.setattr(dst, "_subset_oid", lambda *a, **kw: ("test_oid", [("f.jpg", "p/f.jpg")]))
    monkeypatch.setattr(dst, "_sync_keys", lambda *a, **kw: sync_result)
    monkeypatch.setattr(dst, "_rewrite_secured", lambda *a, **kw: 1)
    published = []
    monkeypatch.setattr(dst, "_publish", lambda *a, **kw: published.append(1) or "svc")
    dst.deploy_secured_test_set(
        cfg, "oid_fc", test_bucket="b", source_bucket="src", key_prefix="p",
        cloud_store_name="store", publish=True, dry_run=False,
    )
    return published


def test_publish_skipped_when_sync_incomplete(monkeypatch, cfg, logger):
    sync = {"copied": 0, "skipped": 0, "failed": 1, "no_key": 0, "failures": [("k", "e")]}
    assert _run_live_publish(monkeypatch, cfg, sync) == []
    assert logger.warning.called


def test_publish_runs_when_sync_complete(monkeypatch, cfg):
    sync = {"copied": 1, "skipped": 0, "failed": 0, "no_key": 0, "failures": []}
    assert _run_live_publish(monkeypatch, cfg, sync) == [1]
