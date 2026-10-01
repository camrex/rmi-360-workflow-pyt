# Debug launcher: probes the API headlessly (does the frozen data path work?),
# then starts the GUI with verbose logging + devtools. Console build only.

import logging
import sys
import time

logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)


def probe() -> None:
    from config_editor.app.api import ConfigEditorAPI
    from config_editor.core import paths

    print(f"TOOLBOX_ROOT={paths.TOOLBOX_ROOT}", flush=True)
    print(f"sample exists={paths.sample_config_path().exists()}", flush=True)
    print(f"config_manager exists={paths.config_manager_source().exists()}", flush=True)

    t0 = time.time()
    api = ConfigEditorAPI()
    schema = api.get_schema()
    print(f"get_schema OK: {len(schema.get('sections', []))} sections in {time.time() - t0:.2f}s", flush=True)
    print(f"profiles: {api.list_profiles()}", flush=True)
    t0 = time.time()
    new = api.new_config()
    print(f"new_config OK: {len(new['values'])} top-level keys in {time.time() - t0:.2f}s", flush=True)


if __name__ == "__main__":
    probe()
    import webview
    _orig_start = webview.start
    webview.start = lambda *a, **k: _orig_start(*a, **{**k, "debug": True})
    from config_editor.app.main import main
    main()
