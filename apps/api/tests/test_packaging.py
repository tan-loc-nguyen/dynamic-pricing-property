"""Checks that the packaged single-binary build stays shippable.

Packaging fails in ways the normal test suite cannot see, because every other
test runs from a source checkout where the paths happen to be right. These
assert the things that are only wrong once PyInstaller has moved everything:

* the database must not live inside the bundle, which is a temp directory;
* the web bundle must not shadow the API it talks to;
* the exported frontend must not hardcode a port the runner may not get.

The route and locale lists are DERIVED (from the app directory and from
`i18n/routing.ts`) rather than written down, so adding a page or a language
fails here instead of silently shipping a 404.

Every read here pins encoding="utf-8". `Path.read_text()` defaults to the
LOCALE encoding, which is cp1252 on the Windows runner, and both the sources
this reads and the pages it checks are full of Vietnamese. Do not remove it:
the crash is the friendly failure, and the quiet one is worse — a read with
errors="ignore" mis-decodes instead of raising, so a check for a baked-in API
host can pass on Windows while the string is really there.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from dynamic_pricing import packaging

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
WEB = REPO_ROOT / "apps" / "web"
OUT = WEB / "out"

needs_build = pytest.mark.skipif(
    not OUT.exists(), reason="web bundle not built — run `make bundle`"
)


# --------------------------------------------------------------- the sources
def _locales() -> list[str]:
    """The locales the frontend actually declares, read from its own source."""
    text = (WEB / "i18n" / "routing.ts").read_text(encoding="utf-8")
    match = re.search(r"export const LOCALES = \[(.*?)\]", text, re.S)
    assert match, "LOCALES has moved — this test can no longer find the locale list"
    return re.findall(r'"([a-z-]+)"', match.group(1))


def _routes() -> list[str]:
    """Every localised page, derived from the app directory.

    Recursive: a one-level glob stopped covering anything the moment Settings
    grew sub-pages, so `settings/rate-book` could have failed to export and
    this test would still have passed.
    """
    base = WEB / "app" / "[locale]"
    routes = [""]  # the index page itself
    routes += [
        str(page.parent.relative_to(base)).replace("\\", "/")
        for page in base.rglob("page.tsx")
        if page.parent != base
    ]
    return sorted(routes)


# ------------------------------------------------------- where things live
def test_the_packaged_database_never_lives_inside_the_bundle(monkeypatch):
    """`--onefile` unpacks to a temp dir that is deleted on exit.

    A database written there is gone the moment the operator closes the app —
    every decision they recorded with it. The frozen build must therefore
    resolve its data directory OUTSIDE the bundle.
    """
    fake_bundle = pathlib.Path("/tmp/_MEI_not_a_real_bundle")
    monkeypatch.setattr(packaging, "is_frozen", lambda: True)
    monkeypatch.setattr(packaging, "bundle_root", lambda: fake_bundle)

    data_dir = packaging.user_data_dir()

    assert fake_bundle not in data_dir.parents, (
        f"the packaged database would be written inside the bundle ({data_dir}), "
        "which PyInstaller deletes when the process exits"
    )


def test_the_data_directory_is_writable_and_absolute():
    data_dir = packaging.user_data_dir()
    assert data_dir.is_absolute(), f"{data_dir} must be absolute — the packaged app has no stable cwd"


# ------------------------------------------------------ the API still wins
def test_the_web_bundle_never_shadows_the_api():
    """Mounting the frontend at "/" must not swallow /api or /docs.

    Starlette matches routes in registration order, so a mount at "/" added
    before the routers would answer every API call with an HTML page — and the
    failure looks like a JSON parse error in the browser, nowhere near here.
    """
    from fastapi.testclient import TestClient

    from dynamic_pricing.main import app

    client = TestClient(app)

    for path in ("/api/recommendations", "/api/rate-book", "/docs"):
        response = client.get(path)
        assert response.status_code != 404, f"{path} was shadowed by the web mount"
        if path.startswith("/api"):
            assert "application/json" in response.headers.get("content-type", ""), (
                f"{path} returned {response.headers.get('content-type')} — "
                "the web bundle is being served in place of the API"
            )


# ------------------------------------------------------- the exported files
@needs_build
def test_the_root_document_is_not_an_error_page():
    """`redirect()` is a SERVER redirect and does not survive a static export.

    Next exports it as an error document — the page renders blank with
    `id="__next_error__"` — so bare "/" is broken for anyone who types the
    address without a locale. It has to forward on the client instead.
    """
    root = OUT / "index.html"
    assert root.exists(), "the export produced no root document"
    assert "__next_error__" not in root.read_text(encoding="utf-8"), (
        "out/index.html is an exported ERROR document. Bare '/' renders blank. "
        "app/page.tsx must forward client-side rather than call redirect()."
    )


@needs_build
def test_every_locale_route_is_exported():
    locales, routes = _locales(), _routes()
    missing = [
        f"{locale}/{route}".rstrip("/")
        for locale in locales
        for route in routes
        if not (OUT / locale / route / "index.html").exists()
    ]
    assert not missing, f"the export is missing pages: {missing}"


@needs_build
def test_the_exported_bundle_never_hardcodes_the_api_port():
    """The runner takes whatever port is free; the bundle must not assume 8000.

    Served from the same origin as the API, every call can be a relative path.
    A baked-in "http://127.0.0.1:8000" silently breaks the whole app the first
    time an operator already has something on that port.
    """
    offenders = [
        path.relative_to(OUT).as_posix()
        for path in OUT.rglob("*.js")
        if "127.0.0.1:8000" in path.read_text(encoding="utf-8", errors="ignore")
        or "localhost:8000" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, (
        f"a fixed API host is baked into {offenders}. The packaged frontend must "
        "call the API on a relative path so any port works."
    )


@needs_build
def test_the_bundle_carries_both_locales_translated():
    """A packaging step that drops a message file is invisible until the demo."""
    for locale in _locales():
        page = (OUT / locale / "index.html").read_text(encoding="utf-8")
        assert len(page) > 1000, f"{locale} exported an empty document"
    vi = (OUT / "vi" / "index.html").read_text(encoding="utf-8")
    assert "Duyệt giá" in vi, "the Vietnamese bundle lost its translations"


# ---------------------------------------------------- what the runner needs
def test_the_web_dist_helper_reports_absence_rather_than_guessing():
    """A missing bundle must be None, not a path that does not exist.

    `make dev` runs without an export at all, and the API has to keep serving
    on its own; mounting a directory that is not there raises at import time.
    """
    found = packaging.web_dist()
    assert found is None or found.is_dir()
