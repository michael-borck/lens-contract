"""Tests for the lens-contract scaffolding."""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lens_contract import (
    add_contract_routes,
    add_cors,
    add_rate_limit,
    make_app,
    make_manifest,
    run_contract_subcommands,
    upload_tempfile,
)


def _manifest():
    return make_manifest(
        name="example-analyser",
        accepts=["text"],
        produces="ExampleAnalysis",
        extensions=[".txt"],
    )


# --- make_manifest ---------------------------------------------------------

def test_make_manifest_core_fields():
    m = _manifest()
    assert m["name"] == "example-analyser"
    assert m["role"] == "analyser"
    assert m["accepts"] == ["text"]
    assert m["extensions"] == [".txt"]
    assert m["auto_routable"] is True
    assert m["produces"] == "ExampleAnalysis"
    # not installed in the test env -> version falls back, never raises
    assert m["version"] == "0.0.0"


def test_make_manifest_explicit_only_and_extra():
    m = make_manifest(
        name="conversation-analyser",
        accepts=["text", "transcript"],
        produces="ConversationAnalysis",
        auto_routable=False,
        pypi=False,
        repo="https://example.com/x",
    )
    assert m["extensions"] == []
    assert m["auto_routable"] is False
    assert m["pypi"] is False
    assert m["repo"] == "https://example.com/x"


def test_manifest_module_has_no_constant():
    """The table generator reads a module-level MANIFEST; ours must not define one,
    so lens-contract never pollutes the family table."""
    import lens_contract.manifest as mod

    assert not hasattr(mod, "MANIFEST")


# --- HTTP contract routes --------------------------------------------------

def test_health_and_manifest_routes():
    app = FastAPI()
    m = _manifest()
    add_contract_routes(app, m)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.0.0"
    assert "uptime" in body

    assert client.get("/manifest").json() == m


def test_make_app_analyse_roundtrip():
    # analyse receives the spooled temp file; assert it sees the suffix + content
    def analyse(path):
        return {"suffix": path.suffix, "text": path.read_text()}

    app = make_app(_manifest(), analyse)
    client = TestClient(app)

    resp = client.post(
        "/analyse",
        files={"file": ("note.md", b"hello", "text/markdown")},
    )
    assert resp.status_code == 200
    assert resp.json() == {"suffix": ".md", "text": "hello"}

    # empty upload -> 422
    assert client.post("/analyse", files={"file": ("x.txt", b"", "text/plain")}).status_code == 422


def test_make_app_value_error_is_422():
    def analyse(path):
        raise ValueError("bad input")

    client = TestClient(make_app(_manifest(), analyse))
    resp = client.post("/analyse", files={"file": ("x.txt", b"data", "text/plain")})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "bad input"


# --- upload_tempfile -------------------------------------------------------

def test_upload_tempfile_cleans_up():
    with upload_tempfile(b"data", "report.pdf") as path:
        assert path.exists()
        assert path.suffix == ".pdf"
        assert path.read_bytes() == b"data"
    assert not path.exists()


def test_upload_tempfile_default_suffix():
    with upload_tempfile(b"x", None) as path:
        assert path.suffix == ".txt"


# --- CLI subcommands -------------------------------------------------------

def test_cli_manifest_subcommand(capsys):
    m = _manifest()
    handled = run_contract_subcommands(
        m, app_path="x:app", default_port=8009, env_prefix="EXAMPLE", argv=["manifest"]
    )
    assert handled is True
    assert json.loads(capsys.readouterr().out) == m


def test_cli_passes_through_analyse():
    handled = run_contract_subcommands(
        _manifest(), app_path="x:app", default_port=8009, env_prefix="EXAMPLE",
        argv=["report.txt", "--json"],
    )
    assert handled is False


def test_cli_empty_argv():
    handled = run_contract_subcommands(
        _manifest(), app_path="x:app", default_port=8009, env_prefix="EXAMPLE", argv=[]
    )
    assert handled is False


# --- add_cors --------------------------------------------------------------

def _app_with(route_helper):
    app = FastAPI()

    @app.get("/x")
    def x():
        return {"ok": True}

    route_helper(app)
    return TestClient(app)


def test_cors_web_mode_allows_configured_origin_not_others():
    client = _app_with(lambda app: add_cors(app, env_prefix="EXAMPLE"))
    allowed = client.get("/x", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    # an unconfigured origin is NOT echoed (never a blanket "*")
    denied = client.get("/x", headers={"Origin": "http://evil.example.com"})
    assert denied.headers.get("access-control-allow-origin") is None


def test_cors_desktop_mode_allows_any_localhost(monkeypatch):
    monkeypatch.setenv("EXAMPLE_MODE", "desktop")
    client = _app_with(lambda app: add_cors(app, env_prefix="EXAMPLE"))
    resp = client.get("/x", headers={"Origin": "http://localhost:9999"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:9999"


def test_cors_custom_origins_from_env(monkeypatch):
    monkeypatch.setenv("EXAMPLE_ALLOWED_ORIGINS", "https://app.example.com")
    client = _app_with(lambda app: add_cors(app, env_prefix="EXAMPLE"))
    resp = client.get("/x", headers={"Origin": "https://app.example.com"})
    assert resp.headers.get("access-control-allow-origin") == "https://app.example.com"


# --- add_rate_limit --------------------------------------------------------

def test_rate_limit_disabled_is_noop():
    app = FastAPI()
    add_rate_limit(app, env_prefix="EXAMPLE")
    assert getattr(app.state, "limiter", None) is None


def test_rate_limit_enforced_when_enabled(monkeypatch):
    monkeypatch.setenv("EXAMPLE_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("EXAMPLE_RATE_LIMIT", "2/minute")
    client = _app_with(lambda app: add_rate_limit(app, env_prefix="EXAMPLE"))
    assert client.get("/x").status_code == 200
    assert client.get("/x").status_code == 200
    assert client.get("/x").status_code == 429
