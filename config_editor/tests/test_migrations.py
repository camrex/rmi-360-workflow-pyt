from config_editor.core import config_io, migrate, migrations


def test_consolidate_aws_upgrade():
    old = {
        "schema_version": "1.3.5",
        "aws": {
            "s3_bucket": "old-public",
            "s3_bucket_raw": "old-raw",
            "region": "us-east-2",
            "keyring_aws": True,
        },
        "secured_storage": {
            "enabled": True,
            "s3_bucket": "old-secured",
            "cloud_store_name": "MyStore",
            "region": "us-east-2",
            "s3_bucket_folder": "config.project.slug",
        },
    }
    res = migrate.upgrade(old, rules=migrations.rules_for("1.3.5"))
    v = config_io.extract_values(res.config)

    aws = v["aws"]
    assert aws["s3_bucket_panos_unsecured"] == "old-public"     # renamed
    assert aws["s3_bucket_panos_secured"] == "old-secured"      # moved from secured_storage
    assert aws["s3_bucket_raw"] == "old-raw"                    # unchanged
    assert aws["secured_delivery"]["enabled"] is True
    assert aws["secured_delivery"]["cloud_store_name"] == "MyStore"
    assert "s3_bucket" not in aws                               # old key renamed away
    assert "keyring_aws" not in aws                             # removed
    assert "secured_storage" not in v                          # emptied + pruned
    assert v["schema_version"] == "1.4.0"                       # adopts current

    renamed = " | ".join(res.report.renamed)
    assert "secured_storage.s3_bucket -> aws.s3_bucket_panos_secured" in renamed
    assert "secured_storage.enabled -> aws.secured_delivery.enabled" in renamed


def test_upgrade_on_current_config_is_noop_for_renames():
    # A config already on the new schema should not gain stray keys from the rules.
    current = {"schema_version": "1.4.0", "aws": {"s3_bucket_panos_unsecured": "b"}}
    res = migrate.upgrade(current, rules=migrations.rules_for("1.4.0"))
    v = config_io.extract_values(res.config)
    assert v["aws"]["s3_bucket_panos_unsecured"] == "b"
    assert "secured_storage" not in v
    assert res.report.renamed == []  # nothing to rename
