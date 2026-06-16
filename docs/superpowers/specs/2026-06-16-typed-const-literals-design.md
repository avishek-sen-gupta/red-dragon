# Typed `Const` Literals — Design

**Issue:** red-dragon-v0l2
**Date:** 2026-06-16

## Goal

Remove `_parse_const`'s runtime type-guessing by making the IR `Const`
instruction carry an explicit, required type drawn from the existing `TypeExpr`
ADT. After this change a literal's type is fixed at emit time by the producer,
never re-inferred from a stringified value — eliminating the class of bug where a
numeric-looking string literal (e.g. the COBOL file-status code `"10"`) is
silently coerced to the integer `10`.

This realizes the project's stated "TypeExpr end-to-end, no string roundtrips"
direction; `_parse_const` is the last string-roundtrip offender.

## Background

`Const.value` is `Any` but `_handle_const` (interpreter/handlers/variables.py:50)
discards the producer's type and re-guesses via `_parse_const`
(interpreter/vm/vm.py:378): `int(raw)` → `float(raw)` → quote-strip → str. A
Python `str` value `"10"` becomes `int 10`. The COBOL READ AT END comparison
`status == "10"` then compared `String "10"` to `Int 10`, never matched, and the
read loop never terminated (red-dragon-m0oa.7, fixed there with a quoting
workaround `_status_const_reg`).

The re-guess is currently load-bearing: ~114 numeric-literal sites across all 15
frontends emit `Const(value="0")` / `Const(value=str(i))` and rely on it; the
LLM/text path emits `CONST operands:["1"]` and uses `_parse_const` as its wire
decoder. The implicit convention (numeric → bare string, string literal → quoted,
`None`/`True`/`False` → canonical words, func/class refs → `<function:…>` /
`<class:…>` markers) is a footgun.

The type vocabulary to express literal types already exists:
- `FoundationTypeName` (constants.py:106): `INT`, `FLOAT`, `STRING`, `BOOL`,
  `VOID`, `ANY`, `OBJECT`, … as `TypeName` constants.
- `TypeExpr` ADT (types/type_expr.py): `ScalarType`, `FunctionType`,
  `ParameterizedType`/`metatype(...)`, `UnknownType`, etc.
- `TypedValue(value, type)` and `typed_from_runtime` (types/typed_value.py).

No new enum is introduced; `Const` reuses `TypeExpr`.

## Architecture

`Const` gains a **required, non-optional** `type_expr: TypeExpr` field (no
default, never `None`). `value` carries the **real Python payload** (`int 0`,
`str "10"`, `True`, `None`, or a label string for refs). `_handle_const` builds
`TypedValue(value, type_expr)` directly. `_parse_const` and the string-convention
decoding are deleted once every producer is migrated.

Migration is **atomic at the branch level**: because the field is required with
no default, partially-migrated code will not construct, so all construction sites
and all consumers land together on one branch. Individual commits on the branch
may be red; the branch is green before merge.

## Type assignment for each literal form

| Literal | `value` payload | `type_expr` |
|---------|-----------------|-------------|
| integer | Python `int` | `scalar(FoundationTypeName.INT)` |
| float | Python `float` | `scalar(FoundationTypeName.FLOAT)` |
| string | Python `str` (unquoted) | `scalar(FoundationTypeName.STRING)` |
| boolean | Python `bool` | `scalar(FoundationTypeName.BOOL)` |
| null/None | `None` | `scalar(FoundationTypeName.NULL)` — the `Null` scalar |
| function ref | label `str` (e.g. `func_foo_0`) | `FunctionType(...)` |
| class ref | label `str` | `metatype(scalar(<class>))` |

`scalar` is the existing `types/type_expr` constructor. A `null`/`None` literal is
definitively of the **Null** type, which already exists in the ADT
(`type_expr.py:346`, `_NULL = ScalarType(TypeName("Null"))`, used by
`optional_of`/`Union[T, Null]`). It is **not** `UnknownType` — "unknown" means the
type could not be determined, whereas a null literal's type is known. We expose
the canonical name by adding `FoundationTypeName.NULL = TypeName("Null")` and have
emit helpers use `scalar(FoundationTypeName.NULL)` (identical to the existing
`_NULL`). `typed_from_runtime(None)` currently returns `UnknownType`; aligning it
to the `Null` scalar is a small follow-up (see "Follow-up" below), not required
for this change since the Const literal carries its `type_expr` explicitly.

## Components

### 0. Type vocabulary — `interpreter/constants.py`, `interpreter/types/type_expr.py`
- Add `FoundationTypeName.NULL = TypeName("Null")` so the null literal type has a
  canonical public name. It denotes the same `ScalarType(TypeName("Null"))` as the
  existing private `_NULL` in `type_expr.py`; consider exporting `_NULL` (or
  defining it via `scalar(FoundationTypeName.NULL)`) so there is one source of truth.

### 1. `Const` instruction — `interpreter/instructions.py`
- Add required `type_expr: TypeExpr` (positional/keyword, no default).
- `operands` currently returns `[self.value] if self.value != "" else []`; this
  drops empty-string literals. Replace the `!= ""` guard with an explicit
  "has value" notion so an empty `STRING` literal is preserved. (The IR no longer
  needs `value` to round-trip through a string, so `operands` may instead expose
  `[value, type_expr]` for display/serialization — see the LLM path.)

### 2. `_handle_const` — `interpreter/handlers/variables.py`
- Build `TypedValue(value, type_expr)` directly.
- Func/class ref resolution keys on `type_expr` (FunctionType → func symbol
  table → `BoundFuncRef`; metatype → class symbol table → `ClassRef`) instead of
  string-matching `value` against the symbol tables.
- Remove the `_parse_const` import and call.

### 3. Other `_parse_const` consumers
- `interpreter/handlers/memory.py:424` — index/figurative resolution: migrate to
  use the operand's `type_expr`/typed value rather than re-parsing a string.
- `interpreter/handlers/calls.py` — drop the `_parse_const` import/use.
- `interpreter/vm/executor.py:36` — drop the re-export.

### 4. `Const.value` readers that infer type independently
- `interpreter/types/type_inference.py` — must read `Const.type_expr` instead of
  inferring from `value`.
- `interpreter/registry.py`, `interpreter/project/linker.py` — audit for any
  assumption that `value` is a string / needs parsing; switch to typed access.

### 5. Emit helpers — `interpreter/.../emit_context.py` (and per-frontend emit layers)
Add typed constructors so call sites declare type by helper:
`emit_int_const(n)`, `emit_float_const(x)`, `emit_str_const(s)`,
`emit_bool_const(b)`, `emit_null_const()`, `emit_func_ref(label, sig)`,
`emit_class_ref(label)`. Each sets `value` (real Python payload) and the matching
`type_expr`. The COBOL `const_to_reg` and the ~664 raw `Const(...)` sites migrate
to these.

### 6. LLM / text wire path — `interpreter/llm/`, `_const` builder (`instructions.py:1069`)
- The CONST JSON carries an explicit `literal_type` field naming a
  `FoundationTypeName` (`"Int"`, `"Float"`, `"String"`, `"Bool"`), plus `"Null"`,
  `"FuncRef"`, `"ClassRef"` for the non-scalar forms. The `value` field holds the
  payload (for refs, the label). This is chosen over relying on native JSON types
  because it is explicit, uniformly covers refs/null, and is robust to the LLM
  emitting `1` vs `"1"` inconsistently.
- Update the prompt (llm_frontend.py) and `_const` (instructions.py:1069) to
  construct `Const` with `type_expr` decoded from `literal_type`. This is the only
  place text→type decoding legitimately occurs, and it is driven by an explicit
  field, not heuristics.

### 7. Deletions (end of migration)
- `_parse_const` (vm.py) and the string-convention decoding.
- `_status_const_reg` quoting workaround in `interpreter/cobol/lower_io.py`
  (replace its call sites with `emit_str_const("10")` / `emit_str_const("23")`).

### Follow-up (out of scope, tracked separately)
- Align `typed_from_runtime(None)` to return the `Null` scalar instead of
  `UnknownType`, so runtime-wrapped `None` agrees with the null literal type. Not
  required here because the Const literal carries its `type_expr` explicitly.

## Data flow

```
frontend emit_*_const(payload)
  → Const(value=<python payload>, type_expr=<TypeExpr>)
  → _handle_const: TypedValue(value, type_expr)        (no guessing)
LLM JSON CONST {value, literal_type}
  → _const builder: Const(value, type_expr=decode(literal_type))
  → same _handle_const path
```

## Migration sequencing (single branch, green before merge)

1. Add `LiteralKind`-free `type_expr` field to `Const` (required) + emit helpers
   + the new `_handle_const` switch, **and** convert the executor/handlers/
   type-inference consumers. (Core lands first within the branch.)
2. Convert producers area-by-area: COBOL, then each of the 15 frontends, then
   `_base.py`/`common`. Run that area's suite per area.
3. Convert the LLM/text wire path (prompt + `_const` + any fixtures).
4. Delete `_parse_const`, the string-convention decoding, and `_status_const_reg`.
5. Full suite green; merge.

## Error handling / edge cases
- Empty-string literal: preserved via the `operands`/has-value fix (§1).
- Func/class refs: resolved by `type_expr`, not by string-matching `value`.
- Null: the `Null` scalar (`scalar(FoundationTypeName.NULL)`), not `UnknownType`.
- Mismatched payload vs type (e.g. `STRING` with an int payload): `_handle_const`
  trusts `type_expr` for the `TypedValue.type`; helpers guarantee payload/type
  agreement, so this cannot arise from migrated producers.

## Testing
- **Unit (`_handle_const`)**: one test per `type_expr` kind. Critically, a
  `STRING` const with value `"10"` resolves to the string `"10"` (NOT int 10);
  an `INT` const with value `10` resolves to int `10`.
- **Per-language regression**: after each frontend's conversion, that language's
  full suite is green.
- **LLM path**: fixture tests that a CONST JSON with each `literal_type` decodes
  to the right `type_expr`.
- **Guard**: a test/lint asserting `_parse_const` no longer exists and no `Const`
  is constructed without a `type_expr` (e.g. grep-guard or a constructor that
  enforces it).
- **Regression for the original bug**: `tests/integration/test_cobol_read_at_end.py`
  remains green after `_status_const_reg` is replaced by `emit_str_const`.

## Acceptance criteria
- `Const.type_expr` is required and non-optional; no `None` type anywhere.
- `_parse_const` is deleted; no caller remains.
- A `STRING` literal whose value is `"10"` is the string `"10"` at runtime.
- COBOL file-status comparisons work without the quoting workaround.
- Full suite (all 15 languages + COBOL + LLM path) green; NIST `-m nist`
  behavior unchanged by this refactor (still gated; SQ102A still completes).
