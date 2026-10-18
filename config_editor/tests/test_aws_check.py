from unittest.mock import MagicMock

from config_editor.core import aws_check


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


NO_ENV = {}


def _factory(seen=None, **session_kwargs):
    """Session factory that records the kwargs it was called with."""
    def make(**kwargs):
        if seen is not None:
            seen.update(kwargs)
        return FakeSession(**session_kwargs)
    return make


def test_profile_from_config_ok():
    vals = {"aws": {"profile": "rmi-360-workflow-pyt", "region": "us-east-2",
                    "s3_bucket_panos_unsecured": "b1"}}
    seen = {}
    checks = aws_check.check_aws_auth(vals, session_factory=_factory(seen), environ=NO_ENV)
    st = _statuses(checks)
    assert st["AWS profile"] == "ok" and st["Credentials valid"] == "ok"
    assert seen == {"profile_name": "rmi-360-workflow-pyt", "region_name": "us-east-2"}
    assert any(c.name == "S3 bucket b1" and c.status == "ok" for c in checks)


def test_profile_falls_back_to_env():
    seen = {}
    checks = aws_check.check_aws_auth({"aws": {"profile": ""}}, session_factory=_factory(seen),
                                     environ={"AWS_PROFILE": "from-env"}, check_buckets=False)
    assert seen["profile_name"] == "from-env"
    assert "from AWS_PROFILE" in checks[0].detail


def test_config_profile_wins_over_env():
    seen = {}
    aws_check.check_aws_auth({"aws": {"profile": "cfg"}}, session_factory=_factory(seen),
                             environ={"AWS_PROFILE": "env"}, check_buckets=False)
    assert seen["profile_name"] == "cfg"


def test_no_profile_is_error_and_never_calls_aws():
    def boom(**kwargs):
        raise AssertionError("must not create a session")
    checks = aws_check.check_aws_auth({"aws": {}}, session_factory=boom, environ=NO_ENV)
    assert checks[0].name == "AWS profile" and checks[0].status == "error"
    assert any(c.name == "Validate credentials" and c.status == "warn" for c in checks)


def test_default_profile_is_refused():
    def boom(**kwargs):
        raise AssertionError("must not create a session")
    for vals, env in (({"aws": {"profile": "default"}}, NO_ENV), ({"aws": {}}, {"AWS_PROFILE": "Default"})):
        checks = aws_check.check_aws_auth(vals, session_factory=boom, environ=env)
        assert checks[0].status == "error" and "refused" in checks[0].detail


def test_auth_failure_suggests_sso_login():
    checks = aws_check.check_aws_auth({"aws": {"profile": "p"}}, session_factory=_factory(sts_ok=False),
                                     environ=NO_ENV, check_buckets=False)
    bad = next(c for c in checks if c.name == "Credentials valid")
    assert bad.status == "error" and "aws sso login --profile p" in bad.detail


def test_placeholder_region_is_not_passed():
    seen = {}
    aws_check.check_aws_auth({"aws": {"profile": "p", "region": "<YOUR_AWS_S3_REGION>"}},
                             session_factory=_factory(seen), environ=NO_ENV, check_buckets=False)
    assert seen["region_name"] is None


def test_bucket_missing_is_error():
    vals = {"aws": {"profile": "p", "s3_bucket_panos_unsecured": "b1"}}
    checks = aws_check.check_aws_auth(vals, session_factory=_factory(bucket_error="404"), environ=NO_ENV)
    bucket = next(c for c in checks if c.name == "S3 bucket b1")
    assert bucket.status == "error" and "does not exist" in bucket.detail
    assert any(c.name == "Credentials valid" and c.status == "ok" for c in checks)  # auth still ok


def test_bucket_forbidden_is_warning():
    vals = {"aws": {"profile": "p", "s3_bucket_panos_unsecured": "b1"}}
    checks = aws_check.check_aws_auth(vals, session_factory=_factory(bucket_error="403"), environ=NO_ENV)
    bucket = next(c for c in checks if c.name == "S3 bucket b1")
    assert bucket.status == "warn" and "access denied" in bucket.detail
