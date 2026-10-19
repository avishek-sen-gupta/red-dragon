"""CopybookSearch — where the bridge looks for the text a COPY names: directories, extensions and OF/IN libraries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cobol_asg.copybook_library import CopybookLibrary


@dataclass(frozen=True)
class CopybookSearch:
    dirs: tuple[Path, ...] = ()
    exts: tuple[str, ...] = ()
    libraries: tuple[CopybookLibrary, ...] = ()


NO_COPYBOOK_SEARCH = CopybookSearch()
