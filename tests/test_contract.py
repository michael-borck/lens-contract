"""Tests for the lens-contract scaffolding."""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lens_contract import (
    add_contract_routes,
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
