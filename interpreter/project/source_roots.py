"""Source root discovery — finds source directories in multi-module projects.

Each language/build system can have its own discovery strategy. The
discovered roots are injected into the import resolver at construction time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

_MAVEN_SOURCE_DIR = Path("src") / "main" / "java"


class SourceRootDiscovery(ABC):
    """Strategy for discovering source root directories in a project."""

    @abstractmethod
    def discover(self, project_root: Path) -> list[Path]: ...


class ExplicitSourceRootDiscovery(SourceRootDiscovery):
    """Returns explicitly provided source roots. For testing and non-standard layouts."""

    def __init__(self, roots: list[Path]):
        self._roots = list(roots)

    def discover(self, project_root: Path) -> list[Path]:
        return self._roots


class MavenSourceRootDiscovery(SourceRootDiscovery):
    """Discover src/main/java/ trees in Maven multi-module projects.

    Recursively scans project_root for directories matching the Maven
    source layout convention. Handles sibling modules, nested modules,
    and single-module projects.
    """

    def discover(self, project_root: Path) -> list[Path]:
        return sorted(
            candidate
            for candidate in project_root.rglob(str(_MAVEN_SOURCE_DIR))
            if candidate.is_dir()
        )
