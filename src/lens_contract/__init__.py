"""lens-contract: the shared contract surface for the lens analyser family.

A member declares its capabilities and serves the contract with three helpers:

    # manifest.py
    from lens_contract import make_manifest
    MANIFEST = make_manifest(
        name="name-analyser", accepts=["..."], produces="NameAnalysis",
        extensions=[".ext"], auto_routable=True,
    )

    # api.py — common case (no extra form fields)
    from lens_contract import make_app
    from name_analyser import NameAnalyser
    app = make_app(MANIFEST, lambda path: NameAnalyser().analyse(path))

    # api.py — custom /analyse (extra form fields, typed response_model)
    from lens_contract import add_contract_routes, upload_tempfile
    app = FastAPI(title=MANIFEST["name"], version=MANIFEST["version"])
    add_contract_routes(app, MANIFEST)
    # ... define POST /analyse yourself ...

    # cli.py
    from lens_contract import run_contract_subcommands
    def main():
        if run_contract_subcommands(MANIFEST, app_path="name_analyser.api:app",
                                    default_port=80NN, env_prefix="NAME_ANALYSER"):
            return
        # ... bespoke analyse argparse + human output ...

See CONVENTIONS.md in the lens-analysers umbrella for the full contract.
"""
from __future__ import annotations

from .api import add_contract_routes, make_app, upload_tempfile
from .cli import run_contract_subcommands
from .manifest import Manifest, make_manifest

__all__ = [
    "Manifest",
    "make_manifest",
    "add_contract_routes",
    "make_app",
    "upload_tempfile",
    "run_contract_subcommands",
]
