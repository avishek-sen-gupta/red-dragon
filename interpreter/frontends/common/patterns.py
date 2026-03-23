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
class StarPattern(Pattern):
    """Captures remaining elements in a sequence pattern. Python's ``*rest``."""

    name: str


@dataclass(frozen=True)
class ValuePattern(Pattern):
    """Match against a named constant via dotted lookup. Python's ``Color.RED``."""

    parts: tuple[str, ...]


@dataclass(frozen=True)
class DerefPattern(Pattern):
    """Dereference the subject, then match the inner pattern. Rust's ``&val``."""

    inner: Pattern


@dataclass(frozen=True)
class RelationalPattern(Pattern):
    """Compare subject against a value using a relational operator.

    C#'s ``> 5``, ``< 10``, ``>= 0``, ``<= 100``.
    """

    operator: str  # ">", "<", ">=", "<=", "=="
    value: object  # the literal to compare against


@dataclass(frozen=True)
class AndPattern(Pattern):
    """Both sub-patterns must match. C#'s ``> 0 and < 10``."""

    left: Pattern
    right: Pattern


@dataclass(frozen=True)
class NegatedPattern(Pattern):
    """Inner pattern must NOT match. C#'s ``not 0``."""

    inner: Pattern


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


def _has_star(elems: tuple[Pattern, ...]) -> bool:
    """Return True if elements contain a StarPattern."""
    return any(isinstance(e, StarPattern) for e in elems)


def _star_index(elems: tuple[Pattern, ...]) -> int:
    """Return index of StarPattern in elements. Only call when _has_star is True."""
    return next(i for i, e in enumerate(elems) if isinstance(e, StarPattern))


def _compile_after_star_element_test(
    ctx: TreeSitterEmitContext,
    subject_reg: str,
    len_reg: str,
    after_count: int,
    after_offset: int,
    elem_pat: Pattern,
) -> str:
    """Load an after-star element by computing index = len - (after_count - after_offset)."""
    offset_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST, result_reg=offset_reg, operands=[str(after_count - after_offset)]
    )
    idx_reg = _emit_binop(ctx, "-", len_reg, offset_reg)
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[subject_reg, idx_reg])
    return compile_pattern_test(ctx, elem_reg, elem_pat)


def _and_all(ctx: TreeSitterEmitContext, regs: list[str]) -> str:
    """AND a list of boolean registers together with BINOP &&."""
    return reduce(lambda acc, reg: _emit_binop(ctx, "&&", acc, reg), regs[1:], regs[0])


def _or_any(ctx: TreeSitterEmitContext, regs: list[str]) -> str:
    """OR a list of boolean registers together with BINOP ||."""
    return reduce(lambda acc, reg: _emit_binop(ctx, "||", acc, reg), regs[1:], regs[0])


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
            has_star = _has_star(elems)
            len_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", subject_reg]
            )

            if not has_star:
                # No star — exact length match
                expected_len_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CONST,
                    result_reg=expected_len_reg,
                    operands=[str(len(elems))],
                )
                len_ok_reg = _emit_binop(ctx, "==", len_reg, expected_len_reg)
                sub_results = [len_ok_reg] + [
                    _compile_indexed_element(ctx, subject_reg, i, elem_pat)
                    for i, elem_pat in enumerate(elems)
                ]
            else:
                # Star present — minimum length match
                star_idx = _star_index(elems)
                fixed_count = len(elems) - 1
                min_len_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CONST, result_reg=min_len_reg, operands=[str(fixed_count)]
                )
                len_ok_reg = _emit_binop(ctx, ">=", len_reg, min_len_reg)
                sub_results = [len_ok_reg]
                # Before star: literal indices
                sub_results.extend(
                    _compile_indexed_element(ctx, subject_reg, i, elem_pat)
                    for i, elem_pat in enumerate(elems[:star_idx])
                )
                # After star: computed indices
                after_count = len(elems) - star_idx - 1
                sub_results.extend(
                    _compile_after_star_element_test(
                        ctx, subject_reg, len_reg, after_count, k, elem_pat
                    )
                    for k, elem_pat in enumerate(elems[star_idx + 1 :])
                )
                # StarPattern itself: no test (skipped)
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
        case OrPattern(alternatives=alts):
            sub_results = [compile_pattern_test(ctx, subject_reg, alt) for alt in alts]
            return _or_any(ctx, sub_results)
        case AsPattern(pattern=inner, name=_):
            return compile_pattern_test(ctx, subject_reg, inner)
        case StarPattern():
            return _const_true(ctx)
        case DerefPattern(inner=inner):
            # Dereference subject via LOAD_INDIRECT, then test inner pattern
            deref_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.LOAD_INDIRECT,
                result_reg=deref_reg,
                operands=[subject_reg],
            )
            return compile_pattern_test(ctx, deref_reg, inner)
        case ValuePattern(parts=parts):
            # LOAD_VAR first part, then LOAD_FIELD for each remaining part
            reg = ctx.fresh_reg()
            ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[parts[0]])
            for part in parts[1:]:
                next_reg = ctx.fresh_reg()
                ctx.emit(Opcode.LOAD_FIELD, result_reg=next_reg, operands=[reg, part])
                reg = next_reg
            cmp_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP, result_reg=cmp_reg, operands=["==", subject_reg, reg]
            )
            return cmp_reg
        case RelationalPattern(operator=op, value=v):
            const_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=const_reg, operands=[str(v)])
            cmp_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=cmp_reg,
                operands=[op, subject_reg, const_reg],
            )
            return cmp_reg
        case AndPattern(left=left, right=right):
            left_reg = compile_pattern_test(ctx, subject_reg, left)
            right_reg = compile_pattern_test(ctx, subject_reg, right)
            and_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=and_reg,
                operands=["and", left_reg, right_reg],
            )
            return and_reg
        case NegatedPattern(inner=inner):
            inner_reg = compile_pattern_test(ctx, subject_reg, inner)
            neg_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.UNOP,
                result_reg=neg_reg,
                operands=["not", inner_reg],
            )
            return neg_reg
        case _:
            raise NotImplementedError(f"compile_pattern_test: {type(pattern).__name__}")


def _compile_after_star_element_binding(
    ctx: TreeSitterEmitContext,
    subject_reg: str,
    len_reg: str,
    after_count: int,
    after_offset: int,
    elem_pat: Pattern,
) -> None:
    """Bind an after-star element by computing index = len - (after_count - after_offset)."""
    offset_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST, result_reg=offset_reg, operands=[str(after_count - after_offset)]
    )
    idx_reg = _emit_binop(ctx, "-", len_reg, offset_reg)
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[subject_reg, idx_reg])
    compile_pattern_bindings(ctx, elem_reg, elem_pat)


def compile_pattern_bindings(
    ctx: TreeSitterEmitContext, subject_reg: str, pattern: Pattern
) -> None:
    """Emit IR that binds variables from a matched pattern."""
    match pattern:
        case CapturePattern(name=name):
            ctx.emit(Opcode.STORE_VAR, operands=[name, subject_reg])
        case LiteralPattern() | WildcardPattern():
            pass  # no bindings
        case RelationalPattern():
            pass  # no bindings — comparison only
        case AndPattern():
            pass  # no bindings — test only
        case NegatedPattern():
            pass  # no bindings — test only
        case SequencePattern(elements=elems):
            if not _has_star(elems):
                # No star — bind each element by literal index
                for i, elem_pat in enumerate(elems):
                    elem_reg = ctx.fresh_reg()
                    ctx.emit(
                        Opcode.LOAD_INDEX,
                        result_reg=elem_reg,
                        operands=[subject_reg, str(i)],
                    )
                    compile_pattern_bindings(ctx, elem_reg, elem_pat)
            else:
                # Star present — need length for after-star index computation
                star_idx = _star_index(elems)
                len_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CALL_FUNCTION,
                    result_reg=len_reg,
                    operands=["len", subject_reg],
                )
                after_count = len(elems) - star_idx - 1
                # Before star: literal indices
                for i, elem_pat in enumerate(elems[:star_idx]):
                    elem_reg = ctx.fresh_reg()
                    ctx.emit(
                        Opcode.LOAD_INDEX,
                        result_reg=elem_reg,
                        operands=[subject_reg, str(i)],
                    )
                    compile_pattern_bindings(ctx, elem_reg, elem_pat)
                # Star element: slice(subject, star_idx, len - after_count)
                star_pat = elems[star_idx]
                if isinstance(star_pat, StarPattern) and star_pat.name != "_":
                    start_reg = ctx.fresh_reg()
                    ctx.emit(
                        Opcode.CONST, result_reg=start_reg, operands=[str(star_idx)]
                    )
                    after_reg = ctx.fresh_reg()
                    ctx.emit(
                        Opcode.CONST, result_reg=after_reg, operands=[str(after_count)]
                    )
                    stop_reg = _emit_binop(ctx, "-", len_reg, after_reg)
                    slice_reg = ctx.fresh_reg()
                    ctx.emit(
                        Opcode.CALL_FUNCTION,
                        result_reg=slice_reg,
                        operands=["slice", subject_reg, start_reg, stop_reg],
                    )
                    ctx.emit(Opcode.STORE_VAR, operands=[star_pat.name, slice_reg])
                # After star: computed indices
                for k, elem_pat in enumerate(elems[star_idx + 1 :]):
                    _compile_after_star_element_binding(
                        ctx, subject_reg, len_reg, after_count, k, elem_pat
                    )
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
        case OrPattern(alternatives=alts):
            # Mini linear chain: re-test each alternative, bind from first match
            or_done = ctx.fresh_label("or_bind_done")
            for alt in alts:
                test_reg = compile_pattern_test(ctx, subject_reg, alt)
                bind_label = ctx.fresh_label("or_bind")
                next_label = ctx.fresh_label("or_next")
                ctx.emit(
                    Opcode.BRANCH_IF,
                    operands=[test_reg],
                    label=f"{bind_label},{next_label}",
                )
                ctx.emit(Opcode.LABEL, label=bind_label)
                compile_pattern_bindings(ctx, subject_reg, alt)
                ctx.emit(Opcode.BRANCH, label=or_done)
                ctx.emit(Opcode.LABEL, label=next_label)
            ctx.emit(Opcode.LABEL, label=or_done)
        case AsPattern(pattern=inner, name=name):
            compile_pattern_bindings(ctx, subject_reg, inner)
            ctx.emit(Opcode.STORE_VAR, operands=[name, subject_reg])
        case StarPattern(name=name):
            if name != "_":
                ctx.emit(Opcode.STORE_VAR, operands=[name, subject_reg])
        case DerefPattern(inner=inner):
            # Dereference subject via LOAD_INDIRECT, then bind inner pattern
            deref_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.LOAD_INDIRECT,
                result_reg=deref_reg,
                operands=[subject_reg],
            )
            compile_pattern_bindings(ctx, deref_reg, inner)
        case ValuePattern():
            pass  # no bindings — it's a constant
        case _:
            raise NotImplementedError(
                f"compile_pattern_bindings: {type(pattern).__name__}"
            )


def _needs_pre_guard_bindings(pattern: Pattern) -> bool:
    """Return True if pattern introduces variable bindings the guard may reference.

    Recursively checks sub-patterns: a SequencePattern containing CapturePatterns
    also needs pre-guard bindings so the guard can reference the captured variables.
    """
    match pattern:
        case CapturePattern() | AsPattern():
            return True
        case SequencePattern(elements=elems):
            return any(_needs_pre_guard_bindings(e) for e in elems)
        case MappingPattern(entries=entries):
            return any(_needs_pre_guard_bindings(v) for _, v in entries)
        case ClassPattern(positional=pos, keyword=kw):
            return any(_needs_pre_guard_bindings(p) for p in pos) or any(
                _needs_pre_guard_bindings(p) for _, p in kw
            )
        case OrPattern(alternatives=alts):
            return any(_needs_pre_guard_bindings(a) for a in alts)
        case DerefPattern(inner=inner):
            return _needs_pre_guard_bindings(inner)
        case _:
            return False


def _compile_refutable_case(
    ctx: TreeSitterEmitContext,
    subject_reg: str,
    case: MatchCase,
    end_label: str,
) -> None:
    """Emit IR for a refutable case (pattern has a test)."""
    test_reg = compile_pattern_test(ctx, subject_reg, case.pattern)

    if not isinstance(case.guard_node, NoGuard):
        # Capture/as-pattern variables must be available when the guard runs.
        if _needs_pre_guard_bindings(case.pattern):
            compile_pattern_bindings(ctx, subject_reg, case.pattern)
        guard_reg = ctx.lower_expr(case.guard_node)
        combined = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP, result_reg=combined, operands=["&&", test_reg, guard_reg]
        )
        test_reg = combined

    case_true = ctx.fresh_label("case_true")
    case_next = ctx.fresh_label("case_next")
    ctx.emit(Opcode.BRANCH_IF, operands=[test_reg], label=f"{case_true},{case_next}")
    ctx.emit(Opcode.LABEL, label=case_true)
    # Only emit bindings in the true-branch if not already emitted pre-guard.
    if not (
        not isinstance(case.guard_node, NoGuard)
        and _needs_pre_guard_bindings(case.pattern)
    ):
        compile_pattern_bindings(ctx, subject_reg, case.pattern)
    if not isinstance(case.body_node, NoBody):
        ctx.lower_block(case.body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=case_next)


def _compile_irrefutable_case(
    ctx: TreeSitterEmitContext,
    subject_reg: str,
    case: MatchCase,
    end_label: str,
) -> None:
    """Emit IR for an irrefutable case (wildcard or bare capture — always matches)."""
    compile_pattern_bindings(ctx, subject_reg, case.pattern)
    if not isinstance(case.body_node, NoBody):
        ctx.lower_block(case.body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)


def compile_match(
    ctx: TreeSitterEmitContext, subject_reg: str, cases: list[MatchCase]
) -> None:
    """Emit IR for a match statement using CPython-style linear chain.

    Two-pass design: all pattern tests (and guard tests) are emitted before
    any bindings. Bindings only appear in the true-branch, after BRANCH_IF.
    Irrefutable patterns (WildcardPattern, CapturePattern) skip the test and
    branch unconditionally.
    """
    end_label = ctx.fresh_label("match_end")

    for case in cases:
        has_guard = not isinstance(case.guard_node, NoGuard)
        is_irrefutable = (
            isinstance(case.pattern, (WildcardPattern, CapturePattern))
            and not has_guard
        )
        if is_irrefutable:
            _compile_irrefutable_case(ctx, subject_reg, case, end_label)
        else:
            _compile_refutable_case(ctx, subject_reg, case, end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
