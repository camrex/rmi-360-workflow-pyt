# =============================================================================
# 🌐 Dev preview server (config_editor/app/serve.py)
# -----------------------------------------------------------------------------
# Serves the SAME web UI as the pywebview app over http://127.0.0.1, bridging the
# JS `window.pywebview.api.*` calls to the real ConfigEditorAPI. Lets you see and
# exercise the full editor in a browser without installing pywebview — stdlib only.
#
#   python -m config_editor.app.serve            # opens the browser
#   python -m config_editor.app.serve --no-open --port 8800
#
# File dialogs become browser prompts in this mode; everything else is the real
# backend (schema, validate, upgrade, preview, save to disk on this machine).
# =============================================================================

from __future__ import annotations

import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from config_editor.app.api import ConfigEditorAPI

WEB_DIR = Path(__file__).resolve().parent / "web"
API = ConfigEditorAPI()

_CTYPES = {".html": "text/html", ".js": "application/javascript",
           ".css": "text/css", ".json": "application/json"}

# Injected before app.js: define window.pywebview.api as a fetch proxy, then fire
# the pywebviewready event the app waits for. Dialogs fall back to prompts.
_BRIDGE_JS = """
(function () {
  function call(method) {
    return function () {
      var args = Array.prototype.slice.call(arguments);
      return fetch("/api/" + method, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(args)
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d && d.__error) throw new Error(d.__error);
        return d.result;
      });
    };
  }
  var api = {};
  ["get_schema","list_profiles","new_config","open_config","validate",
   "upgrade","preview","save","check_aws","set_keyring"].forEach(function (m) { api[m] = call(m); });
  api.open_dialog = function () {
    return Promise.resolve(window.prompt("Path to an existing config.yaml to open:") || null);
  };
  api.save_dialog = function (suggested) {
    return Promise.resolve(window.prompt("Save config to path:", suggested || "config.yaml") || null);
  };
  window.pywebview = { api: api };
  window.addEventListener("DOMContentLoaded", function () {
    window.dispatchEvent(new Event("pywebviewready"));
  });
})();
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="text/plain"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
            html = html.replace(
                '<script src="app.js"></script>',
                '<script src="/__bridge.js"></script>\n  <script src="app.js"></script>')
            return self._send(200, html, "text/html")
        if path == "/__bridge.js":
            return self._send(200, _BRIDGE_JS, "application/javascript")

        target = (WEB_DIR / path.lstrip("/")).resolve()
        if WEB_DIR in target.parents and target.is_file():
            ctype = _CTYPES.get(target.suffix, "application/octet-stream")
            return self._send(200, target.read_bytes(), ctype)
        return self._send(404, "not found")

    def do_POST(self):
        if not self.path.startswith("/api/"):
            return self._send(404, "not found")
        method = self.path[len("/api/"):]
        length = int(self.headers.get("Content-Length", 0))
        args = json.loads(self.rfile.read(length) or b"[]")
        fn = getattr(API, method, None)
        if not callable(fn) or method.startswith("_"):
            return self._send(404, json.dumps({"__error": f"unknown method {method}"}), "application/json")
        try:
            result = fn(*args)
            return self._send(200, json.dumps({"result": result}), "application/json")
        except Exception as ex:  # surface backend errors to the UI
            return self._send(200, json.dumps({"__error": f"{type(ex).__name__}: {ex}"}), "application/json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"RMI 360 Config Editor (dev preview) -> {url}")
    print("Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
