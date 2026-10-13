"""Finds the programs a COBOL main program statically calls, in ordered search directories."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from interpreter.constants import Language
from interpreter.project.imports import extract_imports
from interpreter.project.resolver import get_resolver
from interpreter.project.source_file import SourceFile
from interpreter.project.types import ImportKind, ImportRef

_MAIN_PATH = Path("__main__.cbl")


def _identity(source: str) -> str:
    return source


def _first_resolving(ref: ImportRef, roots: Sequence[Path]) -> tuple[Path, ...]:
    resolver = get_resolver(Language.COBOL)
    per_root = (
        tuple(
            hit.resolved_path.resolve()
            for hit in resolver.resolve(ref, root)
            if hit.is_resolved()
        )
        for root in roots
    )
    return next((hits for hits in per_root if hits), ())


def _callees(source: bytes, path: Path, roots: Sequence[Path]) -> tuple[Path, ...]:
    return tuple(
        target
        for ref in extract_imports(source, path, Language.COBOL)
        if ref.kind == ImportKind.REQUIRE
        for target in _first_resolving(ref, roots)
    )


_Walk = tuple[tuple[tuple[bytes, Path], ...], Mapping[Path, bytes], frozenset[Path]]


def _step(
    walk: _Walk,
    roots: Sequence[Path],
    source_transform: Callable[[str], str],
) -> _Walk:
    pending, found, seen = walk
    (source, path), rest = pending[-1], pending[:-1]
    callees = _callees(source, path, roots)
    new = tuple(
        t for i, t in enumerate(callees) if t not in seen and t not in callees[:i]
    )
    sources = {t: source_transform(t.read_text()).encode() for t in new}
    return (
        rest + tuple((sources[t], t) for t in new),
        {**found, **sources},
        seen | frozenset(new),
    )


def discover_callee_programs(
    source: bytes,
    search_dirs: Sequence[Path],
    source_transform: Callable[[str], str] = _identity,
) -> tuple[SourceFile, ...]:
    """Every program reachable from *source* by ``CALL 'LITERAL'``, transitively.

    Each target is looked up by program name in *search_dirs* in order; the first
    directory that resolves it wins. *source_transform* is applied to every
    program read. A ``CALL identifier`` names no program statically and is not
    followed.
    """
    roots = tuple(d.resolve() for d in search_dirs)
    start: _Walk = (((source, _MAIN_PATH),), {}, frozenset({_MAIN_PATH.resolve()}))
    walks = itertools.accumulate(
        itertools.count(),
        lambda walk, _: _step(walk, roots, source_transform),
        initial=start,
    )
    found = next(found for pending, found, _ in walks if not pending)
    return tuple(SourceFile(path, text) for path, text in found.items())
