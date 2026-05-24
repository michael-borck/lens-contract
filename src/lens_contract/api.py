"""FastAPI scaffolding for the lens family's HTTP contract.

Two constant routes are identical across every member — `GET /health` and
`GET /manifest` — and the `POST /analyse` body always spools an upload to a temp
file (analysers are path-based). Those live here. `POST /analyse` itself stays in
each repo when it takes extra form fields (e.g. `llm`); `make_app` covers the
common path-only case.
"""
from __future__ import annotations

import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile

from .manifest import Manifest


@contextmanager
def upload_tempfile(content: bytes, filename: str | None) -> Iterator[Path]:
    """Spool uploaded bytes to a temp file (preserving the upload's suffix), yield
    its path, and always delete it. Used by `/analyse` routes because the analysers
    take a filesystem path, and the suffix is what drives extension-based routing.
    """
    suffix = Path(filename or "upload.txt").suffix or ".txt"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(content)
    try:
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)


def add_contract_routes(app: FastAPI, manifest: Manifest) -> None:
    """Wire the two constant contract routes onto an existing app.

    `GET /health` -> {status, uptime, version}; `GET /manifest` -> the manifest.
    The caller owns `POST /analyse` (its form fields and response_model vary).
    """
    start = time.time()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "uptime": round(time.time() - start, 1),
            "version": manifest["version"],
        }

    @app.get("/manifest")
    def get_manifest() -> Manifest:
        return manifest


def make_app(manifest: Manifest, analyse: Callable[[Path], Any]) -> FastAPI:
    """Build a complete app for the common case: `analyse(path) -> pydantic model`
    with no extra form fields.

    Members that need extra fields (e.g. an `llm` toggle) or a typed
    `response_model` in their OpenAPI schema should instead create their own
    `FastAPI()`, call `add_contract_routes`, and define `POST /analyse` with
    `upload_tempfile`.
    """
    app = FastAPI(title=manifest["name"], version=manifest["version"])
    add_contract_routes(app, manifest)

    @app.post("/analyse")
    async def analyse_route(file: UploadFile = File(...)) -> Any:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=422, detail="Empty file")
        with upload_tempfile(content, file.filename) as path:
            try:
                return analyse(path)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app
