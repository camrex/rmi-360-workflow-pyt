from utils import aws_utils
from unittest.mock import MagicMock
import pytest

def make_cfg(use_keyring=False, access_key=None, secret_key=None, service_name='rmi_s3'):
    cfg = MagicMock()
    cfg.get_logger.return_value = MagicMock()
    cfg.get.side_effect = lambda k, d=None: (
        use_keyring if k == 'aws.keyring_aws' else
        service_name if k == 'aws.keyring_service_name' else
        access_key if k == 'aws.access_key' else
        secret_key if k == 'aws.secret_key' else d
    )
    return cfg

def test_aws_credentials_from_keyring():
    cfg = make_cfg(use_keyring=True)
    keyring_mod = MagicMock()
    keyring_mod.get_password.side_effect = ['AKIAFAKE', 'SECRETFAKE']
    logger = MagicMock()
    access_key, secret_key = aws_utils.get_aws_credentials(cfg, keyring_mod=keyring_mod, logger=logger)
    assert access_key == 'AKIAFAKE'
    assert secret_key == 'SECRETFAKE'
    logger.debug.assert_called_with('Retrieved AWS credentials from keyring.')

def test_aws_credentials_from_config():
    cfg = make_cfg(use_keyring=False, access_key='AKIAFAKE', secret_key='SECRETFAKE')
    logger = MagicMock()
    access_key, secret_key = aws_utils.get_aws_credentials(cfg, logger=logger)
    assert access_key == 'AKIAFAKE'
    assert secret_key == 'SECRETFAKE'
    logger.debug.assert_called_with('Retrieved AWS credentials from config.')

def test_aws_credentials_keyring_missing():
    cfg = make_cfg(use_keyring=True)
    keyring_mod = MagicMock()
    keyring_mod.get_password.side_effect = [None, None]
    logger = MagicMock()
    with pytest.raises(RuntimeError) as exc:
        aws_utils.get_aws_credentials(cfg, keyring_mod=keyring_mod, logger=logger)
    assert 'keyring' in str(exc.value)
    logger.error.assert_called()

def test_aws_credentials_config_missing():
    cfg = make_cfg(use_keyring=False, access_key=None, secret_key=None)
    logger = MagicMock()
    with pytest.raises(RuntimeError) as exc:
        aws_utils.get_aws_credentials(cfg, logger=logger)
    assert 'config' in str(exc.value)
    logger.error.assert_called()
