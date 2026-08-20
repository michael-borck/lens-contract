"""FastAPI scaffolding for the lens family's HTTP contract.

Two constant routes are identical across every member — `GET /health` and
`GET /manifest` — and the `POST /analyse` body always spools an upload to a temp
file (analysers are path-based). Those live here. `POST /analyse` itself stays in
each repo when it takes extra form fields (e.g. `llm`); `make_app` covers the
common path-only case.
"""
from __future__ import annotations

import os
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


def add_cors(app: FastAPI, *, env_prefix: str) -> None:
    """Add CORS with one consistent configuration so any family member can front a
    browser/Electron app via environment variables — no code changes:

        {PREFIX}_MODE=desktop
            allow localhost / 127.0.0.1 / file:// / null origins (Electron), no
            credentials. Use this when the analyser is embedded in a desktop app.
        otherwise (web mode)
            allow {PREFIX}_ALLOWED_ORIGINS (comma-separated; defaults to the common
            Vite/CRA dev ports), with credentials.

    Never defaults to "*": an unset web-mode origin list falls back to localhost dev
    ports, not "allow everything". Safe to call on any member; lean/CLI-only members
    simply don't call it.
    """
    from fastapi.middleware.cors import CORSMiddleware

    if os.getenv(f"{env_prefix}_MODE") == "desktop":
        app.add_middleware(
            CORSMiddleware,
            allow_origin_regex=(
                r"^(https?://localhost(:\d+)?"
                r"|https?://127\.0\.0\.1(:\d+)?"
                # Tauri packaged-webview origins: tauri://localhost on
                # macOS/Linux (WKWebView/WebKitGTK), http(s)://tauri.localhost
                # on Windows (WebView2). Without these, every fetch from a
                # packaged Tauri app fails CORS preflight while dev
                # (http://localhost:<port>) works — a silent prod-only break.
                r"|tauri://localhost"
                r"|https?://tauri\.localhost"
                r"|file://.*"
                r"|null)$"
            ),
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        return

    origins = [
        o.strip()
        for o in os.getenv(
            f"{env_prefix}_ALLOWED_ORIGINS",
            "http://localhost:3000,http://localhost:5173",
        ).split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )


def add_rate_limit(
    app: FastAPI, *, env_prefix: str, default_limit: str = "60/minute"
) -> None:
    """Opt-in, service-wide rate limiting (needs the `lens-contract[ratelimit]` extra).

    No-op unless {PREFIX}_RATE_LIMIT_ENABLED=true, so it's safe to call
    unconditionally. The limit is read from {PREFIX}_RATE_LIMIT (slowapi syntax,
    e.g. "60/minute"), defaulting to `default_limit`, and is applied to every route
    via SlowAPIMiddleware.
    """
    if os.getenv(f"{env_prefix}_RATE_LIMIT_ENABLED", "false").lower() != "true":
        return

    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware
        from slowapi.util import get_remote_address
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            f"{env_prefix}_RATE_LIMIT_ENABLED is set but slowapi is not installed. "
            "Install the extra: pip install 'lens-contract[ratelimit]'."
        ) from exc

    limit = os.getenv(f"{env_prefix}_RATE_LIMIT", default_limit)
    limiter = Limiter(key_func=get_remote_address, default_limits=[limit])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)


def add_auth(app: FastAPI, *, env_prefix: str) -> None:
    """Opt-in bearer-token gate, applied one consistent way across the family.

    No-op unless ``{PREFIX}_AUTH_TOKEN`` is set, so it's safe to call
    unconditionally. When the token is present, every request must carry
    ``Authorization: Bearer <token>`` EXCEPT:

      - ``GET /health`` and ``GET /manifest`` — liveness + contract probes,
        carry no secrets, and a desktop host's health check must reach them
        without holding the token;
      - CORS preflight (``OPTIONS``) requests, which never carry the header.

    Intended use:
      - Desktop host: generate a random token at launch, pass it to the
        spawned backend via ``{PREFIX}_AUTH_TOKEN``, and send it from the
        client. Stops other local processes from driving the loopback port.
      - Web deployment: set the env var (behind a real auth proxy for anything
        internet-facing — this token is a backstop, not the whole story).

    Call this BEFORE ``add_cors`` so CORS stays the outermost middleware and
    can attach its headers even to a 401 response. Comparison is constant-time.
    """
    import secrets

    from starlette.requests import Request
    from starlette.responses import JSONResponse

    token = os.getenv(f"{env_prefix}_AUTH_TOKEN")
    if not token:
        return

    open_paths = {"/health", "/manifest"}
    expected = f"Bearer {token}"

    @app.middleware("http")
    async def _require_token(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method == "OPTIONS" or request.url.path in open_paths:
            return await call_next(request)
        provided = request.headers.get("Authorization", "")
        if not secrets.compare_digest(provided, expected):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)


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
