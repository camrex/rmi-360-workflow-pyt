from unittest.mock import MagicMock

from config_editor.core import aws_check


class FakeKeyring:
    def __init__(self, store):
        self.store = store  # {(service, item): value}

    def get_password(self, service, item):
        return self.store.get((service, item))


class FakeClientError(Exception):
    """Mimics botocore ClientError enough for _error_code (has .response)."""
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeSession:
    def __init__(self, sts_ok=True, bucket_error=None, account="123456789012", arn="arn:aws:iam::x:user/y"):
        self._sts_ok, self._bucket_error, self._account, self._arn = sts_ok, bucket_error, account, arn

    def client(self, name):
        c = MagicMock()
        if name == "sts":
            if self._sts_ok:
                c.get_caller_identity.return_value = {"Account": self._account, "Arn": self._arn}
            else:
                c.get_caller_identity.side_effect = Exception("InvalidClientTokenId")
        elif name == "s3" and self._bucket_error:
            c.head_bucket.side_effect = FakeClientError(self._bucket_error)
        return c


def _statuses(checks):
    return {c.name: c.status for c in checks}


def test_keyring_all_ok():
    vals = {"aws": {"auth_mode": "keyring", "keyring_service_name": "aws_s3",
                    "region": "us-east-2", "s3_bucket_panos_unsecured": "b1"}}
    km = FakeKeyring({("aws_s3", "aws_access_key_id"): "AK", ("aws_s3", "aws_secret_access_key"): "SK"})
    checks = aws_check.check_aws_auth(vals, keyring_mod=km, session_factory=lambda **k: FakeSession())
    st = _statuses(checks)
    assert st["Credentials valid"] == "ok"
    assert all(c.status != "error" for c in checks)
    assert any(c.name == "S3 bucket b1" and c.status == "ok" for c in checks)


def test_keyring_missing_item_skips_validation():
    vals = {"aws": {"auth_mode": "keyring", "keyring_service_name": "aws_s3"}}
    km = FakeKeyring({("aws_s3", "aws_access_key_id"): "AK"})  # secret missing
    checks = aws_check.check_aws_auth(vals, keyring_mod=km, session_factory=lambda **k: FakeSession())
    assert any(c.status == "error" and "aws_secret_access_key" in c.name for c in checks)
    assert any(c.name == "Validate credentials" and c.status == "warn" for c in checks)


def test_config_placeholder_is_error():
    vals = {"aws": {"auth_mode": "config", "access_key": "<ACCESS_KEY_ID>", "secret_key": "SK"}}
    checks = aws_check.check_aws_auth(vals, session_factory=lambda **k: FakeSession())
    assert any(c.status == "error" and "access_key" in c.name for c in checks)


def test_config_valid_keys_but_auth_fails():
    vals = {"aws": {"auth_mode": "config", "access_key": "AK", "secret_key": "SK", "region": "us-east-2"}}
    checks = aws_check.check_aws_auth(vals, session_factory=lambda **k: FakeSession(sts_ok=False),
                                     check_buckets=False)
    assert any(c.name == "Credentials valid" and c.status == "error" for c in checks)


def test_instance_mode_ok():
    vals = {"aws": {"auth_mode": "instance", "region": "us-east-2"}}
    checks = aws_check.check_aws_auth(vals, session_factory=lambda **k: FakeSession(), check_buckets=False)
    assert any(c.name == "Credentials valid" and c.status == "ok" for c in checks)


def test_bucket_missing_is_error():
    vals = {"aws": {"auth_mode": "instance", "s3_bucket_panos_unsecured": "b1"}}
    checks = aws_check.check_aws_auth(vals, session_factory=lambda **k: FakeSession(bucket_error="404"))
    bucket = next(c for c in checks if c.name == "S3 bucket b1")
    assert bucket.status == "error" and "does not exist" in bucket.detail
    assert any(c.name == "Credentials valid" and c.status == "ok" for c in checks)  # auth still ok


def test_bucket_forbidden_is_warning():
    vals = {"aws": {"auth_mode": "instance", "s3_bucket_panos_unsecured": "b1"}}
    checks = aws_check.check_aws_auth(vals, session_factory=lambda **k: FakeSession(bucket_error="403"))
    bucket = next(c for c in checks if c.name == "S3 bucket b1")
    assert bucket.status == "warn" and "access denied" in bucket.detail


def test_set_keyring_ok():
    stored = {}
    km = MagicMock()
    km.set_password.side_effect = lambda svc, item, val: stored.__setitem__((svc, item), val)
    c = aws_check.set_keyring_credentials("aws_s3", "AK", "SK", keyring_mod=km)
    assert c.status == "ok"
    assert stored == {("aws_s3", "aws_access_key_id"): "AK", ("aws_s3", "aws_secret_access_key"): "SK"}


def test_set_keyring_requires_both():
    km = MagicMock()
    c = aws_check.set_keyring_credentials("aws_s3", "AK", "", keyring_mod=km)
    assert c.status == "error"
    km.set_password.assert_not_called()
