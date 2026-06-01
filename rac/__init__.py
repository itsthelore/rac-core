"""RAC — Requirements As Code.

A small CLI for linting and diffing product requirements written in Markdown.
Markdown is the source format; the Product AST (see :mod:`rac.models`) is the
internal model that validation and diffing operate on.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth: the version declared in pyproject.toml and
    # baked into the installed distribution. Keeps `rac --version` in sync.
    __version__ = version("requirements-as-code")
except PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0.0.0+unknown"
