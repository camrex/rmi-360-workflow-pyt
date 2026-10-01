# =============================================================================
# 🧊 PyInstaller spec (config_editor/packaging/config_editor.spec)
# -----------------------------------------------------------------------------
# Builds a standalone windowed exe of the RMI 360 Config Editor.
#
#   config_editor/.venv/Scripts/python -m PyInstaller config_editor/packaging/config_editor.spec `
#       --noconfirm --distpath config_editor/dist --workpath config_editor/build/work
#
# Run from the toolbox root. Output: config_editor/dist/RMI360ConfigEditor.exe
# (dist/ and build/ are gitignored; packaging/ holds the tracked build sources.)
#
# Why the datas layout matters: core/paths.py resolves TOOLBOX_ROOT as
# Path(__file__).parents[2]. In a frozen app __file__ lives under sys._MEIPASS,
# so bundling configs/ and utils/manager/ at the same relative positions makes
# every path in paths.py resolve without code changes. The sample config and
# config_manager.py are therefore FROZEN AT BUILD TIME — rebuild the exe when
# the schema version or config.sample.yaml changes.
# =============================================================================

from pathlib import Path

spec_dir = Path(SPECPATH).resolve()          # config_editor/packaging
editor_root = spec_dir.parent                # config_editor
toolbox_root = editor_root.parent            # toolbox root

datas = [
    (str(editor_root / "app" / "web"), "config_editor/app/web"),
    (str(editor_root / "profiles"), "config_editor/profiles"),
    (str(toolbox_root / "configs" / "config.sample.yaml"), "configs"),
    (str(toolbox_root / "utils" / "manager" / "config_manager.py"), "utils/manager"),
]

a = Analysis(
    [str(spec_dir / "launch.py")],
    pathex=[str(toolbox_root)],
    datas=datas,
    hiddenimports=[
        "boto3",    # imported lazily in core/aws_check.py
        "keyring",  # imported lazily in core/aws_check.py
    ],
    excludes=["pytest", "_pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="RMI360ConfigEditor",
    console=False,           # windowed app; no console flash
    upx=False,
    icon=None,
)
