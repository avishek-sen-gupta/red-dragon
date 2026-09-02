# pyright: standard
"""AstStore — a per-run, parallel, disk-backed cache of parsed COBOL ASGs.

The knowledge-graph path parses every batch program; holding every CobolASG in
RAM does not scale. AstStore parses in parallel (thread pool over the JVM bridge)
and keeps only the bridge's raw JSON on disk, deserializing one ASG at a time on
``get()``, where the preprocessor is applied. Indexed by the FULL md5 hex digest
of the path (never truncated — truncation collides at scale).

There used to be a MEMORY strategy holding parsed ASGs, and a matching
``AstStrategy`` enum. Nothing constructed either: the one call site asked for
DISK, so every strategy branch had one live arm and the enum's other value was
dead. Both are gone, along with the optional ``cache_dir`` no caller passed —
``temp_ast_store`` is how a run gets a cache it does not have to name.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from tqdm import tqdm

from cobol_asg.asg_types import CobolASG

_IDENTITY: Callable[[dict], dict] = lambda d: d  # noqa: E731


class AsgJsonParser(Protocol):
    """The one thing the store needs of a bridge: JSON for a program, on disk.

    ``parse_to_file`` rather than a return value because the raw JSON is large and
    is freed as soon as it is written — that is what keeps peak memory at one
    program rather than the whole corpus.
    """

    def parse_to_file(self, source: bytes, out: Path) -> None: ...


class AstParseError(Exception):
    """A program the bridge would not parse, named.

    The bridge reads a program on stdin and writes it to a temp file of its own
    naming, so what it raises identifies the syntax but not the corpus member: on a
    3779-program corpus the failure arrives thousands of subprocesses deep with
    nothing in it to say which file to open. This carries the name, and chains what
    the bridge raised so the original message and traceback survive.
    """


def _digest(path: Path) -> str:
    return hashlib.md5(str(path).encode()).hexdigest()  # FULL hex, no [:8]


def _parse_one(
    path: Path, source: bytes, parser: AsgJsonParser, cache_dir: Path
) -> tuple[str, Path]:
    """One program's bridge output, written to the cache. Runs on a worker thread.

    The cache filename carries the stem for a human reading the directory, and the
    digest for uniqueness: two libraries can hold programs of the same name.

    A failure is re-raised named rather than handled: the parses run on a pool, so
    the name has to travel with the failure -- which program the sweep stopped on
    is not recoverable from where it stopped. Everything is caught, not just
    CobolParseError, because the class name is part of what the caller has to be
    told: a rejected program and a full disk are the same stack trace otherwise.
    """
    digest = _digest(path)
    out = cache_dir / f"{path.stem}-{digest}.ast.json"
    try:
        parser.parse_to_file(source, out)  # raw JSON, freed immediately
    except Exception as exc:
        raise AstParseError(f"{path.name}: {type(exc).__name__}: {exc}") from exc
    return digest, out


class AstStore:
    """Parse-once, get-many store of CobolASG, backed by bridge JSON on disk."""

    def __init__(self, cache_dir: Path, max_workers: int = 4) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._dir = cache_dir
        self._max_workers = max_workers
        self._preprocessor: Callable[[dict], dict] = _IDENTITY
        self._cached: dict[str, Path] = {}

    @property
    def cache_dir(self) -> Path:
        return self._dir

    def parse_all(
        self,
        sources: Mapping[Path, bytes],
        parser: AsgJsonParser,
        preprocessor: Callable[[dict], dict] = _IDENTITY,
        desc: str = "parse COBOL",
    ) -> None:
        """Parse every source in parallel, replacing whatever was cached before.

        The bar is not decoration. This is minutes of JVM subprocesses on a real
        corpus and it reported nothing, so the phase read as a hang to anyone
        watching -- the same defect the JCL store had. ``desc`` names the phase so
        a second caller would not be mistaken for this one. tqdm writes to stderr,
        so it survives a stdout pipe.
        """
        self._preprocessor = preprocessor
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = [
                executor.submit(_parse_one, path, source, parser, self._dir)
                for path, source in sources.items()
            ]
            results = [
                future.result()
                for future in tqdm(
                    as_completed(futures),
                    total=len(futures),
                    desc=desc,
                    unit="program",
                )
            ]
        self._cached = dict(results)

    def get(self, path: Path) -> CobolASG:
        """The program's ASG, deserialized now, with the preprocessor applied."""
        raw = json.loads(self._cached[_digest(path)].read_text(encoding="utf-8"))
        return CobolASG.from_dict(self._preprocessor(raw))  # preprocessor on load


@contextmanager
def temp_ast_store(max_workers: int = 4) -> Iterator[AstStore]:
    """A store whose cache is a temp directory, removed on the way out."""
    with tempfile.TemporaryDirectory() as tmp:
        yield AstStore(Path(tmp), max_workers)
