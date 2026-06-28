"""Unit tests for utils/shared/oid_storage_migration.py.

arcpy is available in the ArcGIS Pro test environment (other suites import it at
module load), so the cursor-backed functions are exercised by monkeypatching
arcpy.da.UpdateCursor / SearchCursor. All S3 access is faked via the module-level
seams (_s3_client, _list_bucket_keys, _http_head_ok) so no boto3/network is used.
"""

import arcpy
import pytest

from utils.shared import oid_storage_migration as osm
from utils.shared.oid_storage_paths import (
    build_oid_image_path_for_mode,
    extract_filename_from_image_path,
)


# -----------------------------------------------------------------------------
# Fixtures / fakes
# -----------------------------------------------------------------------------
class DummyCfg:
    def __init__(self, **overrides):
        self.values = {
            "aws.secured_delivery.enabled": False,
            "aws.s3_bucket_folder": "proj",
            "aws.s3_bucket_panos_unsecured": "legacy-bucket",
            "aws.s3_bucket_panos_secured": "secured-bucket",
            "aws.region": "us-east-1",
            "project.slug": "proj",
        }
        self.values.update(overrides)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def resolve(self, value):
        return value


class DummyUpdateCursor:
    """Context-manager cursor over single-field rows; records updateRow calls."""

    def __init__(self, rows):
        self.rows = [list(r) for r in rows]
        self.updated = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        for r in self.rows:
            yield r

    def updateRow(self, row):
        self.updated.append(list(row))


class DummySearchCursor:
    def __init__(self, rows):
        self.rows = [tuple(r) for r in rows]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self.rows)


def _patch_update_cursor(monkeypatch, cursor):
    monkeypatch.setattr(arcpy.da, "UpdateCursor", lambda *a, **k: cursor)
    return cursor


def _patch_search_cursor(monkeypatch, cursor):
    monkeypatch.setattr(arcpy.da, "SearchCursor", lambda *a, **k: cursor)
    return cursor


def _logger():
    from unittest.mock import MagicMock

    return MagicMock()


def _legacy_url(name):
    return f"https://legacy-bucket.s3.us-east-1.amazonaws.com/proj/{name}"


# -----------------------------------------------------------------------------
# Path/parse round-trip (the bidirectional, idempotent contract)
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("secured", [True, False])
def test_path_filename_round_trip(secured):
    cfg = DummyCfg()
    built = build_oid_image_path_for_mode(cfg, "img_0001.jpg", secured=secured)
    assert extract_filename_from_image_path(built) == "img_0001.jpg"


# -----------------------------------------------------------------------------
# rewrite_oid_image_paths
# -----------------------------------------------------------------------------
def test_rewrite_legacy_to_secured_applies(monkeypatch):
    cfg = DummyCfg()
    cur = _patch_update_cursor(
        monkeypatch, DummyUpdateCursor([[_legacy_url("a.jpg")], [_legacy_url("b.jpg")]])
    )

    result = osm.rewrite_oid_image_paths(cfg, "oid", target_secured=True, logger=_logger(), dry_run=False)

    assert result.changed == 2
    assert result.unchanged == 0
    assert cur.updated == [
        ["$virtualCacheDirectory:proj/a.jpg"],
        ["$virtualCacheDirectory:proj/b.jpg"],
    ]


def test_rewrite_dry_run_writes_nothing(monkeypatch):
    cfg = DummyCfg()
    cur = _patch_update_cursor(monkeypatch, DummyUpdateCursor([[_legacy_url("a.jpg")]]))

    result = osm.rewrite_oid_image_paths(cfg, "oid", target_secured=True, logger=_logger(), dry_run=True)

    assert result.changed == 1
    assert cur.updated == []  # nothing written in dry run


def test_rewrite_is_idempotent(monkeypatch):
    cfg = DummyCfg()
    cur = _patch_update_cursor(
        monkeypatch, DummyUpdateCursor([["$virtualCacheDirectory:proj/a.jpg"]])
    )

    result = osm.rewrite_oid_image_paths(cfg, "oid", target_secured=True, logger=_logger(), dry_run=False)

    assert result.changed == 0
    assert result.unchanged == 1
    assert cur.updated == []


def test_rewrite_counts_unparseable(monkeypatch):
    cfg = DummyCfg()
    _patch_update_cursor(monkeypatch, DummyUpdateCursor([[""], [None], [_legacy_url("a.jpg")]]))

    result = osm.rewrite_oid_image_paths(cfg, "oid", target_secured=True, logger=_logger(), dry_run=True)

    assert result.unparseable == 2
    assert result.changed == 1


# -----------------------------------------------------------------------------
# sync_s3_objects
# -----------------------------------------------------------------------------
class FakeS3:
    def __init__(self, existing=None):
        self.existing = set(existing or [])
        self.copied = []

    def head_object(self, Bucket, Key):  # noqa: N803 - boto3 kwarg names
        if Key not in self.existing:
            raise RuntimeError("404")
        return {}

    def copy_object(self, Bucket, Key, CopySource):  # noqa: N803
        self.copied.append((CopySource["Bucket"], CopySource["Key"], Bucket, Key))


def test_sync_dry_run_lists_without_copy(monkeypatch):
    cfg = DummyCfg()
    monkeypatch.setattr(osm, "_s3_client", lambda cfg, bucket=None: FakeS3())
    monkeypatch.setattr(osm, "_list_bucket_keys", lambda s3, b, p: ["proj/a.jpg", "proj/b.jpg"])

    result = osm.sync_s3_objects(cfg, "legacy-bucket", "secured-bucket", _logger(), dry_run=True)

    assert result.listed == 2
    assert result.copied == 2  # would-copy count
    assert result.failed == 0


def test_sync_copies_and_skips_existing(monkeypatch):
    cfg = DummyCfg()
    fake = FakeS3(existing={"proj/b.jpg"})  # b already at destination
    monkeypatch.setattr(osm, "_s3_client", lambda cfg, bucket=None: fake)
    monkeypatch.setattr(osm, "_list_bucket_keys", lambda s3, b, p: ["proj/a.jpg", "proj/b.jpg"])

    result = osm.sync_s3_objects(
        cfg, "legacy-bucket", "secured-bucket", _logger(), skip_existing=True, dry_run=False
    )

    assert result.copied == 1
    assert result.skipped_existing == 1
    assert fake.copied == [("legacy-bucket", "proj/a.jpg", "secured-bucket", "proj/a.jpg")]


# -----------------------------------------------------------------------------
# audit_oid_vs_s3
# -----------------------------------------------------------------------------
def test_audit_reports_missing_and_orphans(monkeypatch):
    cfg = DummyCfg()
    # OID references a.jpg and b.jpg; bucket has b.jpg and c.jpg.
    _patch_search_cursor(
        monkeypatch, DummySearchCursor([(_legacy_url("a.jpg"),), (_legacy_url("b.jpg"),)])
    )
    monkeypatch.setattr(osm, "_s3_client", lambda cfg, bucket=None: object())
    monkeypatch.setattr(osm, "_list_bucket_keys", lambda s3, b, p: ["proj/b.jpg", "proj/c.jpg"])

    result = osm.audit_oid_vs_s3(cfg, "oid", _logger(), secured_mode=False)

    assert result.oid_keys == 2
    assert result.bucket_keys == 2
    assert result.missing_in_bucket == ["proj/a.jpg"]
    assert result.orphans_in_bucket == ["proj/c.jpg"]


# -----------------------------------------------------------------------------
# validate_imagepath_reachability
# -----------------------------------------------------------------------------
def test_reachability_legacy_uses_http(monkeypatch):
    cfg = DummyCfg()
    _patch_search_cursor(
        monkeypatch, DummySearchCursor([(_legacy_url("a.jpg"),), (_legacy_url("b.jpg"),)])
    )
    seen = []

    def fake_head(url, timeout=10.0):
        seen.append(url)
        return (url.endswith("a.jpg"), "HTTP 200" if url.endswith("a.jpg") else "HTTP 403")

    monkeypatch.setattr(osm, "_http_head_ok", fake_head)

    result = osm.validate_imagepath_reachability(cfg, "oid", _logger(), sample=10, secured_mode=False)

    assert result.sampled == 2
    assert result.ok == 1
    assert result.failed == 1
    assert len(seen) == 2


def test_reachability_secured_checks_key_existence(monkeypatch):
    cfg = DummyCfg()
    _patch_search_cursor(
        monkeypatch,
        DummySearchCursor(
            [("$virtualCacheDirectory:proj/a.jpg",), ("$virtualCacheDirectory:proj/missing.jpg",)]
        ),
    )
    fake = FakeS3(existing={"proj/a.jpg"})
    monkeypatch.setattr(osm, "_s3_client", lambda cfg, bucket=None: fake)

    result = osm.validate_imagepath_reachability(cfg, "oid", _logger(), sample=10, secured_mode=True)

    assert result.secured_mode is True
    assert result.ok == 1
    assert result.failed == 1
