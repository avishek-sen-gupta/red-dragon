"""CoprocessorSpec / compile_program — the generic seam for composing N
RedDragon extension-lowering strategies + dialect parsers into one
compile_cobol() call.

Coprocessor-agnostic: this module never imports anything CICS/SQL-specific
(it only knows RedDragonExtensionLoweringStrategy/DialectParser as Protocols
from cobol_asg.frontend_extension). Consumers (Cicada, Squall,
red-dragon-forge) each build their own CoprocessorSpec(s) inline and hand
them here — this module has no knowledge of what any of them are for.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from cobol_asg.cobol_parser import ProLeapCobolParser
from cobol_asg.frontend_extension import (
    DialectParser,
    NullDialectParser,
)
from interpreter.frontend_extension_lowering import RedDragonExtensionLoweringStrategy
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.cobol_discovery import discover_callee_programs
from interpreter.project.source_file import SourceFile
from interpreter.project.types import LinkedProgram


def _identity(source: str) -> str:
    return source


def _no_source_search_dirs() -> Sequence[Path]:
    return ()


def _no_linked_subprogram_sources() -> Mapping[str, bytes]:
    return {}


@dataclass(frozen=True)
class CoprocessorSpec:
    """One coprocessor's contribution to a composed COBOL program.

    ``make_strategy`` is a zero-arg closure built by a per-coprocessor adapter,
    already bound to whatever runtime state that coprocessor needs.
    ``source_prepass`` runs at the source-text layer, before ProLeap parses
    the program, on every program compiled: the main program, each linked
    subprogram and each callee discovered on the search path.

    A coprocessor whose strategy construction depends on state its own
    prepass computes (e.g. a dclgen field-metadata sidecar) closes over a
    private mutable one-element list shared between ``source_prepass`` and
    ``make_strategy`` — compile_program guarantees every spec's
    ``source_prepass`` runs on every compiled program — the main program, each
    discovered callee and each linked subprogram — before ANY spec's
    ``make_strategy`` is called, so that holder is always populated in time.

    ``owns_execution`` marks the (at most one) coprocessor that imposes
    execution semantics on the compiled program (e.g. a dispatcher loop) —
    consumers decide what to do with this; compile_program itself doesn't
    inspect it.

    ``dialect_parser`` threads compile_cobol's ``dialect_parsers=[...]`` array
    through without this module knowing what any dialect parser does — every
    caller sets one (a real one, or the NullDialectParser default);
    compile_program collects them all unconditionally.

    ``source_search_dirs`` feeds callee discovery (discover_callee_programs)
    — a coprocessor whose CALLed subprograms are never on
    disk under the caller's own directory (e.g. IBM Language Environment stubs)
    sets this to contribute that directory, without this module knowing what's
    in it or what any of it is for. Every spec's contribution is appended, in
    order, after the caller's own: a spec adds to that search path, never
    replaces it.

    ``linked_subprogram_sources`` is the other half of that pair, and the two
    must not be mistaken for each other. A search path resolves callees
    *discovered* from ``CALL 'LITERAL'`` edges; this one links a subprogram
    *unconditionally*, whether or not anything discovered it. It exists for the
    callees no static scan can find — a CALL by data-name, where the program
    name is the variable's runtime contents and the only edge a text scan could
    report is the variable's own name. A coprocessor supplying such a callee
    returns ``{program_name: source_bytes}``; compile_program merges every
    spec's mapping (later specs winning on a repeated name) and compiles each
    entry as one of the programs it hands compile_cobol.

    That contribution is a mapping and not a directory on purpose:
    compile_program reads only what discovery finds on the search path, so
    choosing which ``.cbl`` members to link unconditionally stays with the
    coprocessor that knows which of its own programs it means.
    """

    name: str
    make_strategy: Callable[[], RedDragonExtensionLoweringStrategy]
    source_prepass: Callable[[str], str] = _identity
    owns_execution: bool = False
    dialect_parser: DialectParser = field(default_factory=NullDialectParser)
    source_search_dirs: Callable[[], Sequence[Path]] = _no_source_search_dirs
    linked_subprogram_sources: Callable[[], Mapping[str, bytes]] = (
        _no_linked_subprogram_sources
    )


def compile_program(
    source: bytes,
    parser: ProLeapCobolParser,
    specs: Sequence[CoprocessorSpec],
    *,
    source_search_dirs: Sequence[Path] = (),
    linked_subprogram_sources: Mapping[str, bytes] = {},
    tolerant: bool = False,
) -> LinkedProgram:
    """Compile ``source`` with every spec's prepass and strategy composed.

    The specs' source rewrites run, in order, on every program compiled, before
    ANY spec's ``make_strategy`` is called (see CoprocessorSpec's docstring).
    Callees are discovered here, through the merged search directories, so the
    list handed to compile_cobol is fixed; a linked subprogram wins over a
    discovered callee of the same name, compared without regard to case.

    ``source_search_dirs`` and ``linked_subprogram_sources`` are the caller's
    own contributions to the pairs of the same names on CoprocessorSpec; each
    spec's are added after them.
    """

    def rewrite(text: str) -> str:
        return functools.reduce(lambda t, spec: spec.source_prepass(t), specs, text)

    text = rewrite(source.decode("utf-8"))
    all_source_search_dirs: tuple[Path, ...] = functools.reduce(
        lambda dirs, spec: (*dirs, *spec.source_search_dirs()),
        specs,
        tuple(source_search_dirs),
    )
    linked = {
        name: SourceFile(
            Path(f"{name}.cbl"), rewrite(subprogram.decode("utf-8")).encode("utf-8")
        )
        for name, subprogram in functools.reduce(
            lambda srcs, spec: {**srcs, **spec.linked_subprogram_sources()},
            specs,
            dict(linked_subprogram_sources),
        ).items()
    }
    linked_names = frozenset(name.upper() for name in linked)
    discovered = tuple(
        found
        for found in discover_callee_programs(
            text.encode("utf-8"), all_source_search_dirs, rewrite
        )
        if found.path.stem.upper() not in linked_names
    )

    strategies = [spec.make_strategy() for spec in specs]
    dialect_parsers = [spec.dialect_parser for spec in specs]
    return compile_cobol(
        text.encode("utf-8"),
        parser=parser,
        programs=(*discovered, *linked.values()),
        extension_strategies=strategies,
        dialect_parsers=dialect_parsers,
        tolerant=tolerant,
    )
