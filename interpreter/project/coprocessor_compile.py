"""CoprocessorSpec / compile_program — the generic seam for composing N
RedDragon extension-lowering strategies + dialect parsers into one
compile_cobol() call.

Coprocessor-agnostic: this module never imports anything CICS/SQL-specific
(it only knows RedDragonExtensionLoweringStrategy/DialectParser as Protocols
from interpreter.frontend_extension). Consumers (Cicada, Squall,
red-dragon-forge) each build their own CoprocessorSpec(s) inline and hand
them here — this module has no knowledge of what any of them are for.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from interpreter.frontend_extension import (
    DialectParser,
    NullDialectParser,
    RedDragonExtensionLoweringStrategy,
)
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.types import LinkedProgram


def _identity(source: str) -> str:
    return source


def _no_extra_program_source_dirs() -> Sequence[Path]:
    return ()


@dataclass(frozen=True)
class CoprocessorSpec:
    """One coprocessor's contribution to a composed COBOL program.

    ``make_strategy`` is a zero-arg closure built by a per-coprocessor adapter,
    already bound to whatever runtime state that coprocessor needs.
    ``source_prepass`` runs at the source-text layer, before ProLeap parses
    the program.

    A coprocessor whose strategy construction depends on state its own
    prepass computes (e.g. a dclgen field-metadata sidecar) closes over a
    private mutable one-element list shared between ``source_prepass`` and
    ``make_strategy`` — compile_program guarantees every spec's
    ``source_prepass`` runs before ANY spec's ``make_strategy`` is called, so
    that holder is always populated in time.

    ``owns_execution`` marks the (at most one) coprocessor that imposes
    execution semantics on the compiled program (e.g. a dispatcher loop) —
    consumers decide what to do with this; compile_program itself doesn't
    inspect it.

    ``dialect_parser`` threads compile_cobol's ``dialect_parsers=[...]`` array
    through without this module knowing what any dialect parser does — every
    caller sets one (a real one, or the NullDialectParser default);
    compile_program collects them all unconditionally.

    ``extra_program_source_dirs`` threads compile_cobol's
    ``program_source_dirs=[...]`` search path through the same way — a
    coprocessor whose CALLed subprograms are never on disk under the
    caller's own directory (e.g. IBM Language Environment stubs) sets this to
    contribute that directory, without this module knowing what's in it or
    what any of it is for. compile_program appends every spec's
    contribution, in order, after the caller's own program_source_dirs.
    """

    name: str
    make_strategy: Callable[[], RedDragonExtensionLoweringStrategy]
    source_prepass: Callable[[str], str] = _identity
    owns_execution: bool = False
    dialect_parser: DialectParser = NullDialectParser()
    extra_program_source_dirs: Callable[[], Sequence[Path]] = (
        _no_extra_program_source_dirs
    )


def compile_program(
    source: bytes,
    parser: Any,
    specs: Sequence[CoprocessorSpec],
    *,
    program_source_dirs: Sequence[Path] = (),
) -> tuple[Any, LinkedProgram]:
    """Compile ``source`` with every spec's prepass and strategy composed.

    Every spec's ``source_prepass`` runs, in order, before ANY spec's
    ``make_strategy`` is called — a spec whose strategy construction depends
    on state its own prepass populates relies on this ordering (see
    CoprocessorSpec's docstring).
    """
    text = functools.reduce(
        lambda t, spec: spec.source_prepass(t), specs, source.decode("utf-8")
    )

    strategies = [spec.make_strategy() for spec in specs]
    dialect_parsers = [spec.dialect_parser for spec in specs]
    all_program_source_dirs: tuple[Path, ...] = functools.reduce(
        lambda dirs, spec: (*dirs, *spec.extra_program_source_dirs()),
        specs,
        tuple(program_source_dirs),
    )

    return compile_cobol(
        text.encode("utf-8"),
        parser=parser,
        extension_strategies=strategies,
        dialect_parsers=dialect_parsers,
        program_source_dirs=all_program_source_dirs,
    )
