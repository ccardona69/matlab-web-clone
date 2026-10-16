"""Modo standalone (mirror local ml-mirror): fallback de raíz y script de copia.

Reglas: la instalación (MATLAB_ROOT) gana; si falta, el backend sirve del
mirror local; sin ninguna raíz → 404. El script de mirror nunca sube nada al
repo (ml-mirror/ está en .gitignore).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "mirror_matlab_webgui.py"


def _load_mirror_script():
    spec = importlib.util.spec_from_file_location("mirror_matlab_webgui", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _use_mirror_root(monkeypatch, mirror: Path) -> None:
    monkeypatch.delenv("MATLAB_ROOT", raising=False)
    monkeypatch.delenv("MATLAB_MIRROR", raising=False)
    monkeypatch.setattr("backend.local_assets._default_mirror_root", lambda: mirror)


def test_ui_asset_falls_back_to_local_mirror(tmp_path, monkeypatch) -> None:
    mirror = tmp_path / "ml-mirror"
    icon = mirror / "ui" / "icons" / "24x24" / "new_script.svg"
    icon.parent.mkdir(parents=True)
    icon.write_text("<svg/>", encoding="utf-8")
    _use_mirror_root(monkeypatch, mirror)

    with TestClient(app) as client:
        response = client.get("/ui/icons/24x24/new_script.svg")
        mw = client.get("/mw/")  # el mirror de prueba no tiene webgui → 404
    assert response.status_code == 200
    assert "svg" in response.text
    assert mw.status_code == 404


def test_install_root_preferred_over_mirror(tmp_path, monkeypatch) -> None:
    install = tmp_path / "install"
    (install / "ui" / "icons").mkdir(parents=True)
    (install / "ui" / "icons" / "x.svg").write_text("INSTALL", encoding="utf-8")
    mirror = tmp_path / "ml-mirror"
    (mirror / "ui" / "icons").mkdir(parents=True)
    (mirror / "ui" / "icons" / "x.svg").write_text("MIRROR", encoding="utf-8")
    monkeypatch.setenv("MATLAB_ROOT", str(install))
    monkeypatch.delenv("MATLAB_MIRROR", raising=False)
    monkeypatch.setattr("backend.local_assets._default_mirror_root", lambda: mirror)

    with TestClient(app) as client:
        response = client.get("/ui/icons/x.svg")
    assert response.text == "INSTALL"


def test_mirror_script_copies_incrementally(tmp_path) -> None:
    script = _load_mirror_script()
    src = tmp_path / "matlab"
    for rel, text in {
        "ui/icons/a.svg": "a",
        "ui/icons/b.svg": "b",
        "toolbox/matlab/rtc_addons/copilot/shared/release/bundle.js": "c",
    }.items():
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    dest = tmp_path / "ml-mirror"
    subdirs = ("ui/icons", "toolbox/matlab/rtc_addons")

    first = script.mirror_tree(src, dest, subdirs=subdirs)
    assert first["copied"] == 3
    assert (dest / "ui" / "icons" / "b.svg").read_text(encoding="utf-8") == "b"

    second = script.mirror_tree(src, dest, subdirs=subdirs)
    assert second["copied"] == 0
    assert second["skipped"] == 3

    dry = script.mirror_tree(src, dest, subdirs=("ui/icons",), force=True, dry_run=True)
    assert dry["copied"] == 2
    # dry_run no toca el destino
    (dest / "ui" / "icons" / "a.svg").write_text("tocado", encoding="utf-8")
    script.mirror_tree(src, dest, subdirs=("ui/icons",), dry_run=True)
    assert (dest / "ui" / "icons" / "a.svg").read_text(encoding="utf-8") == "tocado"

    forced = script.mirror_tree(src, dest, subdirs=("ui/icons",), force=True)
    assert forced["copied"] == 2
    assert (dest / "ui" / "icons" / "a.svg").read_text(encoding="utf-8") == "a"


def test_mirror_script_reports_missing_subdirs(tmp_path) -> None:
    script = _load_mirror_script()
    stats = script.mirror_tree(
        tmp_path / "vacio", tmp_path / "dest", subdirs=("ui/icons", "sys/fonts")
    )
    assert stats["copied"] == 0
    assert stats["missing"] == ["ui/icons", "sys/fonts"]
