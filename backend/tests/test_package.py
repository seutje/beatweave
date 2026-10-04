import json
from pathlib import Path

from beatweave import __version__


def test_package_version() -> None:
    assert __version__ == "0.3.7"


def test_desktop_csp_allows_local_backend_media() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    config = json.loads((repository_root / "src-tauri" / "tauri.conf.json").read_text())
    csp = config["app"]["security"]["csp"]

    directives = {
        parts[0]: set(parts[1:])
        for directive in csp.split(";")
        if (parts := directive.strip().split())
    }

    backend_origin = "http://127.0.0.1:8420"
    assert backend_origin in directives["connect-src"]
    assert backend_origin in directives["img-src"]
    assert backend_origin in directives["media-src"]
