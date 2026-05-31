import importlib.util
import pathlib
import sys
import types
from unittest.mock import MagicMock


_MISSING = object()

# Targeted stubs for imports used by delivery_subset_validator.py.
utils_mod = types.ModuleType("utils")
shared_mod = types.ModuleType("utils.shared")
manager_mod = types.ModuleType("utils.manager")
rmi_ex_mod = types.ModuleType("utils.shared.rmi_exceptions")
cfg_mgr_mod = types.ModuleType("utils.manager.config_manager")


class ConfigValidationError(Exception):
    pass


class ConfigManager:  # pragma: no cover - typing-only import target
    pass


rmi_ex_mod.ConfigValidationError = ConfigValidationError
cfg_mgr_mod.ConfigManager = ConfigManager

utils_mod.shared = shared_mod
utils_mod.manager = manager_mod
shared_mod.rmi_exceptions = rmi_ex_mod
manager_mod.config_manager = cfg_mgr_mod

_STUBBED_MODULE_NAMES = [
    "utils",
    "utils.shared",
    "utils.manager",
    "utils.shared.rmi_exceptions",
    "utils.manager.config_manager",
]
_snapshots = {name: sys.modules.get(name, _MISSING) for name in _STUBBED_MODULE_NAMES}
try:
    sys.modules["utils"] = utils_mod
    sys.modules["utils.shared"] = shared_mod
    sys.modules["utils.manager"] = manager_mod
    sys.modules["utils.shared.rmi_exceptions"] = rmi_ex_mod
    sys.modules["utils.manager.config_manager"] = cfg_mgr_mod

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    validator_path = repo_root / "utils" / "validators" / "delivery_subset_validator.py"
    spec = importlib.util.spec_from_file_location("delivery_subset_validator_under_test", validator_path)
    validator = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(validator)
finally:
    for _name, _prior in _snapshots.items():
        if _prior is _MISSING:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _prior


class DummyCfg:
    def __init__(self, raw):
        self._raw = raw
        self._logger = MagicMock()

    def get_logger(self):
        return self._logger

    def get(self, key_path, default=None):
        value = self._raw
        for part in key_path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value


def _valid_delivery_subset_block():
    return {
        "delivery_subset": {
            "enabled": True,
            "source_capture_spacing_meters": 1.0,
            "target_spacing_meters": 5.0,
            "spacing_selector": {
                "enabled": True,
                "mode": "auto_stride",
                "stride_override": None,
                "group_by_reel": True,
                "validate_distance": True,
                "tolerance_percent": 10.0,
                "max_local_adjustments_per_pick": 2,
                "correction_strategy": "nearest_candidate",
            },
            "mp_range_selector": {
                "enabled": True,
                "ranges": [
                    {"mp_pre": "M", "min": 1.0, "max": 2.0},
                    {"mp_pre": "N", "min": 5.0, "max": 6.0},
                ],
            },
            "output": {
                "strategy": "manifest",
                "manifest_filename": "delivery_subset_manifest.csv",
                "subset_folder_name": "delivery_subset",
            },
            "on_validation_failure": "warn_and_continue",
        }
    }


def test_delivery_subset_validator_success():
    cfg = DummyCfg(_valid_delivery_subset_block())
    assert validator.validate(cfg) is True


def test_delivery_subset_validator_requires_selector_when_enabled():
    raw = _valid_delivery_subset_block()
    raw["delivery_subset"]["spacing_selector"]["enabled"] = False
    raw["delivery_subset"]["mp_range_selector"]["enabled"] = False
    cfg = DummyCfg(raw)

    assert validator.validate(cfg) is False


def test_delivery_subset_validator_fixed_stride_requires_override():
    raw = _valid_delivery_subset_block()
    raw["delivery_subset"]["spacing_selector"]["mode"] = "fixed_stride"
    raw["delivery_subset"]["spacing_selector"]["stride_override"] = None
    cfg = DummyCfg(raw)

    assert validator.validate(cfg) is False


def test_delivery_subset_validator_mp_ranges_must_be_ordered():
    raw = _valid_delivery_subset_block()
    raw["delivery_subset"]["mp_range_selector"]["ranges"][0] = {"mp_pre": "M", "min": 3.0, "max": 2.0}
    cfg = DummyCfg(raw)

    assert validator.validate(cfg) is False


def test_delivery_subset_validator_output_strategy_validation():
    raw = _valid_delivery_subset_block()
    raw["delivery_subset"]["output"]["strategy"] = "invalid"
    cfg = DummyCfg(raw)

    assert validator.validate(cfg) is False


def test_delivery_subset_validator_target_not_less_than_source():
    raw = _valid_delivery_subset_block()
    raw["delivery_subset"]["source_capture_spacing_meters"] = 5.0
    raw["delivery_subset"]["target_spacing_meters"] = 1.0
    cfg = DummyCfg(raw)

    assert validator.validate(cfg) is False
