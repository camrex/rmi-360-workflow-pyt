# =============================================================================
# 🔧 Schema migration rules (config_editor/core/migrations.py)
# -----------------------------------------------------------------------------
# Declarative rename/remove rules applied by the editor's Upgrade to move an old
# config onto the current schema. Ops: {op: rename, from, to} / {op: remove, path}.
# Renames are no-ops when the source key is absent, so applying them to an
# already-current config is harmless.
# =============================================================================

from __future__ import annotations

from typing import Any, List

# 1.4.0 — consolidate aws + secured_storage into one aws block.
CONSOLIDATE_AWS = [
    {"op": "rename", "from": "aws.s3_bucket", "to": "aws.s3_bucket_panos_unsecured"},
    {"op": "rename", "from": "secured_storage.s3_bucket", "to": "aws.s3_bucket_panos_secured"},
    {"op": "rename", "from": "secured_storage.enabled", "to": "aws.secured_delivery.enabled"},
    {"op": "rename", "from": "secured_storage.cloud_store_name", "to": "aws.secured_delivery.cloud_store_name"},
    {"op": "remove", "path": "secured_storage.region"},
    {"op": "remove", "path": "secured_storage.s3_bucket_folder"},
    {"op": "remove", "path": "aws.keyring_aws"},
]

# All known rules, in apply order. (Single milestone today; append future ones.)
ALL_RULES: List[dict] = CONSOLIDATE_AWS


def rules_for(source_version: Any = None, target_version: Any = None) -> List[dict]:
    """Rules to apply for an upgrade. Currently version-independent (the renames are
    no-ops when their source keys are absent)."""
    return list(ALL_RULES)
