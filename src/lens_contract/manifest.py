"""The capability-manifest schema and builder for the lens analyser family.

Every Python member exposes a `MANIFEST` constant (plus a `manifest` CLI
subcommand and `GET /manifest`). `make_manifest` builds that dict with the
installed-version lookup handled once, instead of each repo re-implementing the
`importlib.metadata.version` try/except.

NOTE: this module deliberately defines no module-level `MANIFEST` constant, so
`lens-analysers/scripts/generate_family_table.py` (which loads every workspace
`manifest.py` and reads its `MANIFEST`) skips it — lens-contract is infrastructure,
not an analyser, and must not appear in the family table.
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TypedDict


class Manifest(TypedDict, total=False):
    """The contract descriptor. See CONVENTIONS.md for field meanings.

    `total=False` because non-Python/optional members may add `repo`/`pypi`; the
    seven core keys are always set by `make_manifest`.
    """

    name: str
    version: str
    role: str
    accepts: list[str]
    extensions: list[str]
    auto_routable: bool
    produces: str
    repo: str
    pypi: bool | str


def make_manifest(
    *,
    name: str,
    accepts: list[str],
    produces: str,
    extensions: list[str] | tuple[str, ...] = (),
    role: str = "analyser",
    auto_routable: bool = True,
    **extra: object,
) -> Manifest:
    """Build a capability manifest, resolving `version` from installed metadata.

    Args:
        name: package/distribution name, e.g. "conversation-analyser".
        accepts: content kinds handled, e.g. ["code"] or ["text", "transcript"].
        produces: result model name, e.g. "ConversationAnalysis".
        extensions: file extensions claimed for auto-routing ([] / () if none).
        role: "analyser" (default) or "orchestrator".
        auto_routable: may auto-analyser route to it automatically?
        **extra: extra fields for non-standard members (e.g. repo=, pypi=).

    Returns:
        A Manifest dict. If the distribution isn't installed (e.g. running from a
        source checkout that was never `pip install`-ed), version falls back to
        "0.0.0" rather than raising.
    """
    try:
        ver = version(name)
    except PackageNotFoundError:
        ver = "0.0.0"
    manifest: Manifest = {
        "name": name,
        "version": ver,
        "role": role,
        "accepts": list(accepts),
        "extensions": list(extensions),
        "auto_routable": auto_routable,
        "produces": produces,
    }
    manifest.update(extra)  # type: ignore[typeddict-item]
    return manifest
