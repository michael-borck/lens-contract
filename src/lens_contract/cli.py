"""CLI scaffolding for the lens family's two shared subcommands.

Every member's CLI handles `<tool> manifest` and `<tool> serve` identically; only
the bare-positional "analyse" path is bespoke. `run_contract_subcommands` absorbs
the two shared ones and returns False when the caller should parse its own args.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .manifest import Manifest


def run_contract_subcommands(
    manifest: Manifest,
    *,
    app_path: str,
    default_port: int,
    env_prefix: str,
    argv: list[str] | None = None,
) -> bool:
    """Handle the family's two shared subcommands; return True if one ran.

        <tool> manifest              -> print the capability manifest as JSON
        <tool> serve [--host --port] -> uvicorn.run(app_path, ...)

    Returns False when the first arg is neither (so the caller parses its own
    analyse arguments). Host/port also read `{ENV_PREFIX}_HOST` / `{ENV_PREFIX}_PORT`.

    Args:
        manifest: the member's MANIFEST (printed by `manifest`).
        app_path: uvicorn import string, e.g. "conversation_analyser.api:app".
        default_port: the member's assigned port (see CONVENTIONS.md).
        env_prefix: env-var prefix, e.g. "CONVERSATION_ANALYSER".
        argv: override argv for testing; defaults to sys.argv[1:].
    """
    args = sys.argv[1:] if argv is None else argv
    if not args:
        return False

    if args[0] == "manifest":
        print(json.dumps(manifest, indent=2))
        return True

    if args[0] == "serve":
        import uvicorn

        parser = argparse.ArgumentParser(prog=f"{manifest['name']} serve")
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv(f"{env_prefix}_PORT", str(default_port))),
        )
        parser.add_argument(
            "--host",
            default=os.getenv(f"{env_prefix}_HOST", "127.0.0.1"),
        )
        ns = parser.parse_args(args[1:])
        uvicorn.run(app_path, host=ns.host, port=ns.port)
        return True

    return False
