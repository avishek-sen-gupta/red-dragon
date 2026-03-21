# Unified Match Expression Lowering Framework — Design Spec

**Date:** 2026-03-21
**Issue:** red-dragon-lgsk
**Type:** Refactor — extract shared code, no behavior change

## Summary

Extract the duplicated match/switch expression lowering skeleton from Rust, Scala, Kotlin, and C# into `interpreter/frontends/common/match_expr.py`. Zero behavior change — pure deduplication.

## Interface

```python
# interpreter/frontends/common/match_expr.py

@dataclass(frozen=True)
class MatchArmSpec:
    """Language-specific callbacks for decomposing match arms."""
    extract_arms: Callable[[object], list[object]]
    pattern_of: Callable[[TreeSitterEmitContext, object], Pattern]
    guard_of: Callable[[TreeSitterEmitContext, object], object | None]
    body_of: Callable[[TreeSitterEmitContext, object], str]

def lower_match_as_expr(
    ctx: TreeSitterEmitContext,
    subject_reg: str,
    body_node: object,
    spec: MatchArmSpec,
) -> str:
    """Emit IR for expression-style match. Returns result register."""
```

## What the framework hides

The `_lower_arm` internal function handles (once, not 4 times):
1. Irrefutability shortcut — `WildcardPattern`/`CapturePattern` without guard skips test
2. Pre-guard binding protocol — `_needs_pre_guard_bindings` + conditional rebind suppression
3. Guard folding — `BINOP && test_reg guard_reg`
4. `BRANCH_IF` / `LABEL` / `BRANCH` / `DECL_VAR` skeleton per arm
5. `result_var` / `end_label` allocation and final `LOAD_VAR` epilogue

## Per-language migration

Each language provides 4 small callbacks in a `MatchArmSpec` and a thin wrapper:

**Rust:** `_rust_pattern_of`, `_rust_guard_of`, `_rust_body_of` + `extract_arms` lambda. ~30 lines replaces ~80 lines.

**Scala:** `_scala_pattern_of`, `_scala_guard_of`, `_scala_body_of` + `extract_arms` lambda. ~25 lines replaces ~80 lines. Guard extraction: find `GUARD` child, unwrap inner named child.

**Kotlin:** `_kotlin_pattern_of`, `_kotlin_body_of` + `extract_arms` lambda + `guard_of=lambda ctx, e: None`. ~20 lines replaces ~60 lines. Subjectless `when` stays in caller — not pattern matching.

**C#:** `_csharp_pattern_of`, `_csharp_body_of` + `extract_arms` lambda + `guard_of=lambda ctx, a: None`. ~10 lines replaces ~50 lines.

## What's excluded

- Kotlin subjectless `when` — boolean dispatch, not patterns
- C# switch statement — uses `break_target_stack`, different semantics
- Python `compile_match` — statement-style, uses `lower_block`

## Testing

Pure refactor — all existing tests must pass with zero changes. No new tests needed (the behavior is identical). Run full suite before and after.
