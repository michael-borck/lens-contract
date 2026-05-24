# lens-contract

The shared **contract surface** for the [lens analyser family](https://github.com/michael-borck/lens-analysers).
Every Python member exposes the same manifest, the same `GET /health` + `GET /manifest`
routes, and the same `serve` / `manifest` CLI subcommands. This package is that
common surface, so a contract change is one release here instead of an edit in every
analyser.

It is **infrastructure, not an analyser** (`role: library`): it does not appear in
the family table and is not auto-routable.

## What it provides

| Helper | Replaces the per-repo… |
|---|---|
| `make_manifest(...)` | `_version()` try/except + `MANIFEST` dict in `manifest.py` |
| `add_contract_routes(app, MANIFEST)` | hand-written `GET /health` + `GET /manifest` |
| `make_app(MANIFEST, analyse)` | the whole `api.py` for the path-only common case |
| `upload_tempfile(content, filename)` | the `POST /analyse` upload→tempfile→cleanup dance |
| `run_contract_subcommands(...)` | the `serve` + `manifest` dispatch in `cli.py` |

## What it deliberately does **not** provide

Per the family principle *share the contract, not forced abstraction*: the
`analyse()` business logic, the human-readable CLI output (`rich`), and the rich
analyse-CLI flags stay in each repo. `rich` is not even a dependency here.

## Usage

```python
# manifest.py
from lens_contract import make_manifest
MANIFEST = make_manifest(
    name="name-analyser", accepts=["..."], produces="NameAnalysis",
    extensions=[".ext"], auto_routable=True,
)

# api.py — common case
from lens_contract import make_app
from name_analyser import NameAnalyser
app = make_app(MANIFEST, lambda path: NameAnalyser().analyse(path))

# cli.py
from lens_contract import run_contract_subcommands
def main():
    if run_contract_subcommands(MANIFEST, app_path="name_analyser.api:app",
                                default_port=8010, env_prefix="NAME_ANALYSER"):
        return
    ...  # bespoke analyse argparse + human output
```

Members needing extra `/analyse` form fields (e.g. `--llm`) build their own app with
`add_contract_routes` + `upload_tempfile` — see `conversation-analyser` as the
reference adopter.

## Develop

```bash
uv venv && uv pip install -e '.[dev]'
uv run pytest
```
