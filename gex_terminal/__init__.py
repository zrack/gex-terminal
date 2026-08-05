"""gex-terminal package."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib

_source_pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
if _source_pyproject.is_file():
    # A source checkout can contain stale editable metadata. Read the declared
    # source version so pyproject.toml remains the sole release authority.
    __version__ = str(
        tomllib.loads(_source_pyproject.read_text(encoding="utf-8"))["project"]["version"]
    )
else:
    try:
        __version__ = version("gex-terminal")
    except PackageNotFoundError:
        __version__ = "0+unknown"
