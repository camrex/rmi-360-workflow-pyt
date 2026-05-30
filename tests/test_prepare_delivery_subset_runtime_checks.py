import importlib.util
import pathlib
import sys
import types


# Minimal stubs for importing prepare_delivery_subset.py in isolation.
arcpy_mod = types.ModuleType("arcpy")
manager_mod = types.ModuleType("utils.manager")
cfg_mgr_mod = types.ModuleType("utils.manager.config_manager")


class ConfigManager:  # pragma: no cover - typing import target
    pass


cfg_mgr_mod.ConfigManager = ConfigManager
sys.modules["arcpy"] = arcpy_mod
sys.modules["utils.manager"] = manager_mod
sys.modules["utils.manager.config_manager"] = cfg_mgr_mod

repo_root = pathlib.Path(__file__).resolve().parents[1]
module_path = repo_root / "utils" / "prepare_delivery_subset.py"
spec = importlib.util.spec_from_file_location("prepare_delivery_subset_under_test", module_path)
prepare_mod = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(prepare_mod)


class DummyLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []
        self.errors = []

    def info(self, msg, indent=0):
        self.infos.append((msg, indent))

    def warning(self, msg, indent=0):
        self.warnings.append((msg, indent))

    def error(self, msg, error_type=None):
        self.errors.append((msg, error_type))


class DummyCfg:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        value = self.values
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value


def _record(oid, reel, x, y, acq):
    return {
        "oid": oid,
        "reel": reel,
        "x": x,
        "y": y,
        "acq": acq,
    }


def test_capture_spacing_validation_warns_on_large_deviation_and_ignores_cross_reel_gap():
    logger = DummyLogger()
    cfg = DummyCfg(
        {
            "delivery_subset": {
                "source_capture_spacing_meters": 1.0,
                "on_validation_failure": "warn_and_continue",
                "capture_spacing_validation": {
                    "max_deviation_percent": 20.0,
                    "min_reels_with_estimate": 1,
                },
            }
        }
    )

    # Reel A has ~2m spacing; Reel B is far away, but cross-reel gap should not be used.
    records = [
        _record(1, "A", -97.000000, 32.000000, "2025-01-01T00:00:00Z"),
        _record(2, "A", -96.999979, 32.000000, "2025-01-01T00:00:01Z"),
        _record(3, "A", -96.999958, 32.000000, "2025-01-01T00:00:02Z"),
        _record(4, "B", -96.500000, 32.500000, "2025-01-01T00:00:00Z"),
        _record(5, "B", -96.499979, 32.500000, "2025-01-01T00:00:01Z"),
    ]

    prepare_mod._validate_source_capture_spacing(records, cfg, logger)

    assert len(logger.warnings) >= 1
    assert any("configured=1.00m" in msg for msg, _ in logger.warnings)


def test_capture_spacing_validation_info_when_within_tolerance():
    logger = DummyLogger()
    cfg = DummyCfg(
        {
            "delivery_subset": {
                "source_capture_spacing_meters": 2.0,
                "on_validation_failure": "warn_and_continue",
                "capture_spacing_validation": {
                    "max_deviation_percent": 25.0,
                    "min_reels_with_estimate": 1,
                },
            }
        }
    )

    records = [
        _record(1, "A", -97.000000, 32.000000, "2025-01-01T00:00:00Z"),
        _record(2, "A", -96.999979, 32.000000, "2025-01-01T00:00:01Z"),
        _record(3, "A", -96.999958, 32.000000, "2025-01-01T00:00:02Z"),
        _record(4, "A", -96.999937, 32.000000, "2025-01-01T00:00:03Z"),
    ]

    prepare_mod._validate_source_capture_spacing(records, cfg, logger)

    assert len(logger.warnings) == 0
    assert any("Capture spacing check:" in msg for msg, _ in logger.infos)
