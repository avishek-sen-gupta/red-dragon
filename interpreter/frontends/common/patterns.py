"""Pattern ADT for structural pattern matching.

Language frontends parse tree-sitter ASTs into these types.
The compile_match function (below) emits IR from them.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce

from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.ir import Opcode


@dataclass(frozen=True)
class Pattern:
    """Base for all pattern types."""


@dataclass(frozen=True)
class LiteralPattern(Pattern):
    """Match against a literal value (int, str, bool, None)."""

    value: int | float | str | bool | None


@dataclass(frozen=True)
class WildcardPattern(Pattern):
    """Matches anything, binds nothing. Python's ``_``."""


@dataclass(frozen=True)
class CapturePattern(Pattern):
    """Matches anything, binds the subject to a variable name."""

    name: str


@dataclass(frozen=True)
class SequencePattern(Pattern):
    """Matches a tuple or list — checks length, then matches each element by index."""

    elements: tuple[Pattern, ...]


@dataclass(frozen=True)
class MappingPattern(Pattern):
    """Matches a dict — checks each key exists, then matches the value pattern."""

    entries: tuple[tuple[int | float | str | bool | None, Pattern], ...]


@dataclass(frozen=True)
class ClassPattern(Pattern):
    """Matches by type, then matches positional and keyword sub-patterns."""

    class_name: str
    positional: tuple[Pattern, ...]
    keyword: tuple[tuple[str, Pattern], ...]


@dataclass(frozen=True)
class OrPattern(Pattern):
    """Matches if any alternative matches (short-circuit). No bindings."""

    alternatives: tuple[Pattern, ...]


@dataclass(frozen=True)
class AsPattern(Pattern):
    """Matches inner pattern, then binds subject to name."""

    pattern: Pattern
    name: str


@dataclass(frozen=True)
class NoGuard:
    """Sentinel: this case has no guard clause."""


@dataclass(frozen=True)
class NoBody:
    """Sentinel: this case has no body (used in tests)."""


@dataclass(frozen=True)
class MatchCase:
    """A single case in a match statement."""

    pattern: Pattern
    guard_node: object  # tree-sitter node for guard expression, or NoGuard()
    body_node: object  # tree-sitter node for case body, or NoBody()


def _const_true(ctx: TreeSitterEmitContext) -> str:
    """Emit a CONST True and return the register."""
    true_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=true_reg, operands=["True"])
    return true_reg


def _compile_indexed_element(
    ctx: TreeSitterEmitContext, subject_reg: str, index: int, elem_pat: Pattern
) -> str:
    """Load element at index from subject and compile its pattern test."""
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[subject_reg, str(index)])
    return compile_pattern_test(ctx, elem_reg, elem_pat)


def _emit_binop(ctx: TreeSitterEmitContext, op: str, left: str, right: str) -> str:
    """Emit a single BINOP and return the result register."""
    combined = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=combined, operands=[op, left, right])
    return combined


def _and_all(ctx: TreeSitterEmitContext, regs: list[str]) -> str:
    """AND a list of boolean registers together with BINOP &&."""
    return reduce(lambda acc, reg: _emit_binop(ctx, "&&", acc, reg), regs[1:], regs[0])


def compile_pattern_test(
    ctx: TreeSitterEmitContext, subject_reg: str, pattern: Pattern
) -> str:
    """Emit IR that tests whether subject matches pattern. Returns a boolean register."""
    match pattern:
        case LiteralPattern(value=v):
            const_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=const_reg, operands=[str(v)])
            cmp_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=cmp_reg,
                operands=["==", subject_reg, const_reg],
            )
            return cmp_reg
        case WildcardPattern():
            return _const_true(ctx)
        case CapturePattern():
            return _const_true(ctx)
        case SequencePattern(elements=elems):
            len_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", subject_reg]
            )
            expected_len_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST, result_reg=expected_len_reg, operands=[str(len(elems))]
            )
            len_ok_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=len_ok_reg,
                operands=["==", len_reg, expected_len_reg],
            )
            sub_results = [len_ok_reg] + [
                _compile_indexed_element(ctx, subject_reg, i, elem_pat)
                for i, elem_pat in enumerate(elems)
            ]
            return _and_all(ctx, sub_results)
        case MappingPattern(entries=entries):
            sub_results = []
            for key, val_pat in entries:
                field_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.LOAD_FIELD,
                    result_reg=field_reg,
                    operands=[subject_reg, str(key)],
                )
                val_test = compile_pattern_test(ctx, field_reg, val_pat)
                sub_results.append(val_test)
            return _and_all(ctx, sub_results) if sub_results else _const_true(ctx)
        case ClassPattern(class_name=cls, positional=pos, keyword=kw):
            cls_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=cls_reg, operands=[cls])
            isinstance_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_FUNCTION,
                result_reg=isinstance_reg,
                operands=["isinstance", subject_reg, cls_reg],
            )
            sub_results = [isinstance_reg]
            for i, p in enumerate(pos):
                elem_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.LOAD_INDEX,
                    result_reg=elem_reg,
                    operands=[subject_reg, str(i)],
                )
                sub_results.append(compile_pattern_test(ctx, elem_reg, p))
            for name, p in kw:
                field_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.LOAD_FIELD,
                    result_reg=field_reg,
                    operands=[subject_reg, name],
                )
                sub_results.append(compile_pattern_test(ctx, field_reg, p))
            return _and_all(ctx, sub_results)
        case _:
            raise NotImplementedError(f"compile_pattern_test: {type(pattern).__name__}")


def compile_pattern_bindings(
    ctx: TreeSitterEmitContext, subject_reg: str, pattern: Pattern
) -> None:
    """Emit IR that binds variables from a matched pattern."""
    match pattern:
        case CapturePattern(name=name):
            ctx.emit(Opcode.STORE_VAR, operands=[name, subject_reg])
        case LiteralPattern() | WildcardPattern():
            pass  # no bindings
        case SequencePattern(elements=elems):
            for i, elem_pat in enumerate(elems):
                elem_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.LOAD_INDEX,
                    result_reg=elem_reg,
                    operands=[subject_reg, str(i)],
                )
                compile_pattern_bindings(ctx, elem_reg, elem_pat)
        case MappingPattern(entries=entries):
            for key, val_pat in entries:
                field_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.LOAD_FIELD,
                    result_reg=field_reg,
                    operands=[subject_reg, str(key)],
                )
                compile_pattern_bindings(ctx, field_reg, val_pat)
        case ClassPattern(class_name=_, positional=pos, keyword=kw):
            for i, p in enumerate(pos):
                elem_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.LOAD_INDEX,
                    result_reg=elem_reg,
                    operands=[subject_reg, str(i)],
                )
                compile_pattern_bindings(ctx, elem_reg, p)
            for name, p in kw:
                field_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.LOAD_FIELD,
                    result_reg=field_reg,
                    operands=[subject_reg, name],
                )
                compile_pattern_bindings(ctx, field_reg, p)
        case _:
            raise NotImplementedError(
                f"compile_pattern_bindings: {type(pattern).__name__}"
            )
