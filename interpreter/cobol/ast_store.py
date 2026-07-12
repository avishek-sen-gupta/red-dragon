# pyright: standard
"""AstStore — a per-run, parallel, strategy-backed cache of parsed COBOL ASGs.

The knowledge-graph and multi-file-compile paths parse many programs; holding
every CobolASG in RAM does not scale. AstStore parses in parallel (thread pool
over the JVM bridge) and, under the DISK strategy, keeps only raw bridge JSON on
disk, deserializing one ASG at a time on get(). MEMORY holds parsed ASGs. Both
strategies apply the same preprocessor so they return identical ASGs. Keyed by
the FULL md5 hex of the path (never truncated — truncation collides at scale).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from pathlib import Path
from typing import Any

from interpreter.cobol.asg_types import CobolASG

_IDENTITY: Callable[[dict], dict] = lambda d: d  # noqa: E731


class AstStrategy(Enum):
    MEMORY = "memory"
    DISK = "disk"


def _key(path: Path) -> str:
    return hashlib.md5(str(path).encode()).hexdigest()  # FULL hex, no [:8]


class AstStore:
    """Parse-once, get-many store of CobolASG, MEMORY or DISK backed."""

    def __init__(
        self,
        strategy: AstStrategy = AstStrategy.DISK,
        *,
        cache_dir: Path | None = None,
        max_workers: int = 4,
    ) -> None:
        self._strategy = strategy
        self._max_workers = max_workers
        self._preprocessor: Callable[[dict], dict] = _IDENTITY
        self._owned_tmp: tempfile.TemporaryDirectory[str] | None = None
        if strategy is AstStrategy.DISK:
            if cache_dir is None:
                self._owned_tmp = tempfile.TemporaryDirectory()
                self._dir = Path(self._owned_tmp.name)
            else:
                cache_dir.mkdir(parents=True, exist_ok=True)
                self._dir = cache_dir
        self._mem: dict[str, CobolASG] = {}
        self._disk: dict[str, Path] = {}

    def parse_all(
        self,
        sources: dict[Path, bytes],
        parser: Any,
        preprocessor: Callable[[dict], dict] = _IDENTITY,
    ) -> None:
        """Parse every source in parallel, populating the cache."""
        self._preprocessor = preprocessor

        def _one(item: tuple[Path, bytes]) -> tuple[str, Any]:
            path, source = item
            k = _key(path)
            if self._strategy is AstStrategy.MEMORY:
                return k, parser.parse(source, preprocessor)
            out = self._dir / f"{path.stem}-{k}.ast.json"
            parser.parse_to_file(source, out)  # raw JSON, freed immediately
            return k, out

        with ThreadPoolExecutor(max_workers=self._max_workers) as ex:
            futures = [ex.submit(_one, it) for it in sources.items()]
            for fut in as_completed(futures):
                k, val = fut.result()
                if self._strategy is AstStrategy.MEMORY:
                    self._mem[k] = val
                else:
                    self._disk[k] = val

    def get(self, path: Path) -> CobolASG:
        k = _key(path)
        if self._strategy is AstStrategy.MEMORY:
            return self._mem[k]
        raw = json.loads(self._disk[k].read_text(encoding="utf-8"))
        return CobolASG.from_dict(self._preprocessor(raw))  # preprocessor on load

    def close(self) -> None:
        if self._owned_tmp is not None:
            self._owned_tmp.cleanup()
            self._owned_tmp = None

    def __enter__(self) -> AstStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
