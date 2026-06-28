from utils.shared.oid_storage_paths import (
    build_oid_object_key,
    build_oid_image_path,
    resolve_oid_target_bucket,
)


class DummyCfg:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)

    def resolve(self, value):
        return value


def test_build_oid_object_key_legacy_mode():
    cfg = DummyCfg({
        "aws.secured_delivery.enabled": False,
        "aws.s3_bucket_folder": "proj-slug",
        "project.slug": "proj-slug",
    })
    assert build_oid_object_key(cfg, "img.jpg", secured_mode=False) == "proj-slug/img.jpg"


def test_build_oid_image_path_secured_mode():
    cfg = DummyCfg({
        "aws.secured_delivery.enabled": True,
        "aws.s3_bucket_folder": "proj-slug",
        "aws.s3_bucket_panos_secured": "secured-bucket",
        "aws.region": "us-east-2",
        "project.slug": "proj-slug",
    })
    assert build_oid_image_path(cfg, "img.jpg") == "$virtualCacheDirectory:proj-slug/img.jpg"


def test_resolve_oid_target_bucket_secured_mode():
    cfg = DummyCfg({
        "aws.secured_delivery.enabled": True,
        "aws.s3_bucket_panos_secured": "secured-bucket",
        "aws.s3_bucket_panos_unsecured": "legacy-bucket",
    })
    assert resolve_oid_target_bucket(cfg, secured_mode=True) == "secured-bucket"
