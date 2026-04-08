# Strongly-Typed IR — Analysis & Gap Assessment

**Status:** Analysis (not for implementation yet)
**Issue:** red-dragon-ivy5
**Date:** 2026-04-08

## Goal

Ensure that every register, variable, heap object field, and array element
in the IR has a precise, resolved `TypeExpr` through static inference —
so that no runtime value is ever `UNKNOWN` when a type could have been
determined statically.  The IR instructions themselves do not need type
annotations; the type environment must be complete.

---

## 1. Current State

### 1.1 The inference pipeline

Type inference is a single forward pass over the flat IR instruction list,
implemented in `interpreter/types/type_inference.py`.  It populates a
`TypeEnvironment` containing:

- `register_types: Register -> TypeExpr` — per-register inferred types
- `var_types: VarName -> TypeExpr` — per-variable types
- `method_signatures: TypeExpr -> {FuncName -> [FunctionSignature]}` — function/method signatures
- `scoped_var_types: scope -> {VarName -> TypeExpr}` — per-scope var types
- `field_types` (internal): `class_type -> {field_name -> TypeExpr}` — class field types

Seeding comes from `TypeEnvironmentBuilder`, which frontends populate during
lowering with function return types, parameter types, variable types, and
type aliases.

### 1.2 What infers correctly today

| Source | Inference mechanism | Quality |
|---|---|---|
| Integer/float/bool/string literals | `_infer_const_type` parses literal strings | Good — handles `42`, `3.14`, `"hello"`, `true`/`false` |
| Binop results | `type_resolver.resolve_binop(op, left, right)` | Good for numeric/string ops; degrades when operands are UNKNOWN |
| Unop results | Fixed-type map (`not`->Bool, `~`->Int) or propagate operand type | Good |
| Constructor calls | `CallCtorFunction.type_hint` seeded by frontend | Good — frontend already knows the class name |
| Object allocation | `NewObject.type_hint` | Good |
| Variable load/store | Forward propagation from store to load via `var_types` | Good for single-assignment; see gap 2 |
| Builtin functions | Hardcoded `_BUILTIN_RETURN_TYPES` table (~12 entries) | Covers basics (`len`->Int, `str`->String, etc.) |
| Builtin methods | Hardcoded `_BUILTIN_METHOD_RETURN_TYPES` table (~50 entries) | Extensive coverage for string/array methods |
| User-defined functions | Looks up `func_return_types` from builder seeds + inferred `Return_` types | Works when return type is seeded or inferrable from a single return |
| Class methods | `class_method_types` + interface chain walk | Works for declared methods; see gap 5 |
| Array element types | `array_element_types` tracked through `StoreIndex`->`LoadIndex` | Works for homogeneous arrays; see gap 6 |
| Tuple element types | Per-index tracking through `tuple_element_types` | Good — tracks individual positions |

### 1.3 What the VM does with types

The VM **does not rely on** the `TypeEnvironment` for execution correctness.
It wraps every value in `TypedValue(value, type)` at runtime using:

- `typed_from_runtime(val)` — infers type from Python `isinstance` checks
- `binop_coercion.coerce()` — coerces operands and infers result type from runtime values

The `TypeEnvironment` is available to the VM via `ctx.type_env` but is used
primarily for:
- Method signature lookup (overload resolution)
- Type-aware error messages
- LLM resolver type hints

---

## 2. Ideal State

### 2.1 Complete register type coverage

After the inference pass, every register that holds a value should have a
resolved `TypeExpr` in `TypeEnvironment.register_types`.  `UNKNOWN` should
only appear for genuinely dynamic values (Python variables assigned from
dynamic sources, JS `any` types, etc.) — and these should be explicitly
typed as `Dynamic`, not left as `UNKNOWN`.

### 2.2 Complete variable type coverage

Every declared and assigned variable should have a type in `var_types`.
For variables assigned multiple times with different types, the type should
be a `UnionType` of all assigned types — not the last assignment's type.

### 2.3 Complete heap field type coverage

Every object field written via `StoreField` should have a type tracked in
`field_types`, and every `LoadField` should propagate that type to its
result register.  For fields declared in class definitions (Java, TypeScript,
etc.), the declared type should be seeded from the frontend.

### 2.4 Complete collection element type coverage

Array and tuple element types should be tracked precisely:
- Homogeneous arrays: `Array[Int]`, `Array[String]`
- Heterogeneous tuples: per-index types
- Nested collections: `Array[Array[Int]]`
- Map/dict types: `Map[String, Int]`

### 2.5 Dynamic vs Unknown distinction

`UNKNOWN` means "inference failed" (a bug or limitation).
`Dynamic` means "type is determined at runtime by design" (dynamic languages).

After the inference pass:
- For statically-typed languages (Java, Go, TypeScript, Rust, C, C++, Kotlin,
  Swift, Scala): **zero UNKNOWN registers/variables** is the target.
- For dynamically-typed languages (Python, JavaScript, Ruby, PHP, Lua):
  `Dynamic` is acceptable for values whose type genuinely depends on runtime;
  `UNKNOWN` still indicates an inference failure.

---

## 3. Gaps

### Gap 1: Single-pass inference can't handle forward references

The inference pass walks instructions in order.  If a function `foo` calls
`bar`, but `bar` is defined later, `foo`'s call instruction gets `UNKNOWN`
return type because `bar`'s return type hasn't been inferred yet.

**Currently mitigated by:** Frontend seeding — if the frontend populates
`func_return_types` for `bar` during lowering, the call resolves.  But this
only works for languages where the frontend has explicit return type
declarations (Java, Go, TypeScript).

**Not mitigated for:** Python, Ruby, Lua, PHP — where return types are
inferred from the function body, which may not have been processed yet.

**Fix:** Multi-pass inference, or a topological walk over the call graph.

### Gap 2: Variable types — union within scope, but scoping is flat

`store_var_type` (line 219) **does** create `union_of(existing, new_type)`
when a variable is reassigned with a different type within the same function
scope.  However:

- **Cross-scope aggregation is post-hoc:** `flat_var_types()` (line 245)
  unions across scopes after inference completes, so during inference a
  function can't see variable types set in another function.
- **Only two tiers exist:** current function scope + global.  No nested
  scope chain — closures referencing outer function variables get `UNKNOWN`.
- **Seeded types are immutable:** If a frontend pre-seeds a variable type,
  inference never overrides it, even if the variable is reassigned to a
  different type later in the code.

**Fix:** Support a scope chain for nested functions/closures.  Allow
inference to widen seeded types when reassignment is observed.

### Gap 3: LoadField type resolution depends on StoreField ordering

`_infer_load_field` looks up `field_types[class_name][field_name]`.  This
only works if a `StoreField` for that field was seen *earlier in the
instruction stream*.  Fields set in constructors work; fields set in other
methods may not be visible at the load site.

**Additionally:** Frontends for typed languages (Java, TypeScript, Go) know
field types from class declarations but don't seed them into the type
environment.

**Fix:** Seed class field types from frontend class declarations.  For
fields set at runtime, aggregate across all `StoreField` sites.

### Gap 4: No `Dynamic` type — UNKNOWN is overloaded

`UNKNOWN` means both "inference didn't determine the type" and "this value
is dynamically typed."  There's no way to distinguish an inference failure
from an intentionally dynamic value.

**Fix:** Add `DynamicType` to the `TypeExpr` ADT.  Frontends for dynamic
languages should seed variables/parameters as `Dynamic` when no annotation
exists.

### Gap 5: Method return types require cross-class lookup heuristics

`_infer_call_method` has a multi-step fallback chain:
1. Look up class method types for the receiver's type
2. Walk interface implementations
3. Search *all* class method types for a unique match
4. Fall back to flat `func_return_types`
5. Fall back to `_BUILTIN_METHOD_RETURN_TYPES`

Steps 3-4 are heuristics that may return wrong results when multiple classes
define methods with the same name but different return types.  Step 3 picks
the first match silently — no warning logged.

**Additionally:** No inheritance chain is walked.  If class `Dog extends
Animal` and `Animal` defines `speak() -> String`, calling `dog.speak()`
won't resolve the return type unless `Dog` explicitly declares `speak`.
Only interface implementations are checked (step 2), not parent classes.

**Fix:** Require the receiver type to be resolved before method lookup.
Walk the inheritance chain (parent classes + interfaces).  If receiver type
is `UNKNOWN`, the method return type should also be `UNKNOWN` (or `Dynamic`)
rather than guessing.

### Gap 6: Collection element types are imprecise

- `NewArray` always infers as `scalar("Array")` — never `Array[Int]` or
  `Array[String]`, even when the frontend knows the element type.
- Element types are tracked via a side-channel (`array_element_types` dict),
  not as part of the `TypeExpr` (which supports `ParameterizedType`).
- `LoadRegion` always returns `scalar("Array")` — no element type.

**Fix:** When frontends lower typed arrays (Java `int[]`, Go `[]string`),
emit the element type.  Thread `ParameterizedType("Array", (element_type,))`
through `NewArray` -> `StoreIndex` -> `LoadIndex`.

### Gap 7: Const type inference is string-based and lossy

`_infer_const_type` parses the string representation of a constant to guess
its type.  This loses information:
- `None`/`null` -> `UNKNOWN` (should be `Null` or `Optional[T]`)
- Function references -> `UNKNOWN` (should be `FunctionType`)
- Class references -> `UNKNOWN` (should be `Type[ClassName]`)
- Hex/octal literals (e.g., `0xFF`) — may fail `int()` parsing

**Fix:** Frontends already know the exact type of every constant.  Seed
constant types during lowering rather than re-inferring from strings.

### Gap 8: No type narrowing after branches

After a type-check branch (e.g., Python `isinstance(x, int)` or Java
`instanceof`), the inference pass doesn't narrow the type of `x` in the
true branch.  The variable keeps its pre-branch type.

**Fix:** Track branch conditions and narrow types in dominated blocks.
Requires basic block / dominator tree awareness — a significant addition.

### Gap 9: LOAD_INDIRECT always returns UNKNOWN

```python
def _infer_load_indirect(...):
    ctx.register_types[inst.result_reg] = UNKNOWN
```

Pointer dereferences always produce `UNKNOWN`, even when the pointer type
is known (e.g., `Pointer[Int]` should dereference to `Int`).

**Fix:** If the pointer register's type is `ParameterizedType("Pointer",
(inner,))`, the result type should be `inner`.

### Gap 10: No inference for LOAD_FIELD_INDIRECT

`LoadFieldIndirect` is not in the inference dispatch table at all.  Any
register produced by it gets no type.

**Fix:** Add inference handler, similar to `LoadField` but tracing through
the pointer's base type.

### Gap 11: No coverage metrics

There's no way to measure "what percentage of registers have resolved
types" for a given program.  Without metrics, it's impossible to track
progress or regressions.

**Fix:** Add a pass that counts `UNKNOWN` vs resolved registers/variables
per function, per module.  Report as part of compilation diagnostics.

### Gap 12: SYMBOLIC instructions produce UNKNOWN by default

`_infer_symbolic` (line 502) does **not** assign a type to the result
register.  The only exceptions are:
- Registers pre-seeded by the `TypeEnvironmentBuilder`
- `self`/`this` parameters inside a class scope

All other SYMBOLIC values (function parameters without seeded types,
program inputs, environment variables) get no type.  The `hint` field
(e.g., `"param:x"`) is used only for metadata extraction, not type
inference.

**Impact:** In dynamic languages where frontends don't seed parameter
types, every function parameter starts as UNKNOWN, poisoning all
downstream inference (binop on UNKNOWN -> UNKNOWN, etc.).

**Fix:** For typed languages, frontends must seed all parameter types.
For dynamic languages, SYMBOLIC params should get `Dynamic`, not UNKNOWN.

### Gap 13: Function overloads use last-write-wins in func_return_types

`func_return_types` is `dict[FuncName, TypeExpr]` — keyed by name only.
If two functions (or overloads) share a name, the second definition
overwrites the first.

`class_method_signatures` supports overload lists, but the standalone
function path does not.  This means standalone function overloads
(common in Kotlin, Scala, C++) lose all but the last signature.

**Fix:** Change `func_return_types` to `dict[FuncName, list[TypeExpr]]`
or merge into the unified `method_signatures` system which already
supports lists.

### Gap 14: No generic/polymorphic function support

Type inference has no concept of type variables or generic instantiation.
A function `T identity(T x)` returning `x` would have return type seeded
as whatever the frontend gives (likely the raw string `"T"`), with no
mechanism to instantiate `T = Int` at a specific call site.

`TypeVar` exists in `TypeExpr` but is never resolved during inference.

**Fix:** Add a generic instantiation step: at each call site, unify
parameter types with argument types to resolve type variables, then
substitute into the return type.

### Gap 15: Frontend seeding quality varies dramatically by language

Empirical audit of 4 frontends:

| Frontend | Return types | Param types | Var types | Field types | Array elem types | Coverage |
|---|---|---|---|---|---|---|
| Java | Yes | Yes | Yes | Yes (field_inits) | No (flattened to `Type[]` string) | ~86% |
| Go | Yes | Yes | Yes | No (no classes) | **Yes** (only frontend using `array_of()`) | ~80% |
| C | Yes | Yes (with pointer depth) | Yes | **No** (struct fields not seeded) | No | ~70% |
| Python | No | Only if annotated | No | No | No | ~15% |

**Key observations:**
- Go is the only frontend using `ParameterizedType` for arrays (`array_of()`)
- Java passes generic types as raw strings (e.g., `"List<String>"`)
- Python ignores PEP 484 annotations (`-> int`, `: str`) despite them
  being available in the tree-sitter AST
- C does not seed struct field types in `lower_struct_field()`

**Fix:** Per-frontend improvement targets.  Python has the most
low-hanging fruit (plumb annotation nodes from AST).

### Gap 16: Multi-module linking loses per-module type context

`link_modules()` in `interpreter/project/linker.py` merges IR from
multiple modules into a single instruction list, with registers
renumbered.  However:

- The `TypeEnvironmentBuilder` passed to the linker is a **single shared
  builder**, not a merge of per-module builders.
- Per-module `TypeEnvironmentBuilder` state (seeded by each frontend
  during lowering) is not propagated — `ModuleUnit.type_env_builder`
  exists but the linker doesn't merge them.
- Type inference runs on the **merged IR** after linking, so it sees all
  functions.  But if per-module seeding was lost, the inference pass has
  less to work with.

**Fix:** Merge per-module `TypeEnvironmentBuilder` states during linking
before running inference on the merged program.

### Gap 17: TypeEnvironment only materially affects overload resolution

The VM uses `TypeEnvironment` for exactly one execution-critical decision:
method/constructor **overload resolution** in `handlers/calls.py`.  All
other execution paths (arithmetic, field access, coercion, variable
handling) use runtime `TypedValue` types exclusively.

This means that improving inference completeness has **narrow runtime
impact** unless the VM is also updated to trust static types.  Currently,
even perfectly inferred types are re-derived at runtime.

**Implication:** This isn't a gap to "fix" per se, but it frames the ROI
of the other gaps.  Overload resolution is the one place where better
inference directly improves correctness.  Other benefits are analytical
(better error messages, LLM hints, future optimization/compilation).

---

## 4. Severity Assessment

| Gap | Impact | Statically-typed langs | Dynamically-typed langs |
|---|---|---|---|
| 1. Forward references | Missed return types | Low (frontends seed) | High |
| 2. Variable scoping | Flat scope chain, immutable seeds | Medium | Medium |
| 3. Field type seeding | Missing field types | High | Medium |
| 4. No Dynamic type | Can't distinguish failure from intent | Low | High |
| 5. Method lookup heuristics | Wrong return types, no inheritance walk | Medium | Medium |
| 6. Collection element types | Arrays always untyped | High | Low |
| 7. Const type from strings | Lost type info on None/fn/class refs | Medium | Medium |
| 8. No type narrowing | No instanceof/type-guard benefit | Medium | Medium |
| 9. LOAD_INDIRECT -> UNKNOWN | Pointers always untyped | High (C/C++/Rust) | N/A |
| 10. LOAD_FIELD_INDIRECT missing | No inference at all | High (C/C++/Rust) | N/A |
| 11. No coverage metrics | Can't measure progress | High | High |
| 12. SYMBOLIC params -> UNKNOWN | Poisons all downstream inference | Low (frontends seed) | **Critical** |
| 13. Function overload last-write | Loses all but last overload sig | High (Kotlin/Scala/C++) | Low |
| 14. No generics instantiation | TypeVar never resolved at call sites | High (Java/Kotlin/Scala) | N/A |
| 15. Frontend seeding quality varies | 15%-86% coverage range | Medium (varies) | High |
| 16. Linking loses type context | Per-module seeds not merged | High (multi-module) | High (multi-module) |
| 17. TypeEnvironment underused by VM | Only affects overload resolution | Low (frames ROI) | Low (frames ROI) |

---

## 5. Suggested Phasing

**Phase A — Measure:** (Gap 11)
Add UNKNOWN-coverage metrics.  Before fixing anything, know the baseline.
Report per-function, per-module, per-language register/variable UNKNOWN rates.

**Phase B — Low-hanging fruit:** (Gaps 4, 7, 9, 10, 12)
- Add `DynamicType` to `TypeExpr`
- Fix `_infer_const_type` to handle None/fn/class refs
- Fix `LOAD_INDIRECT` to use pointer element type
- Add `LoadFieldIndirect` to dispatch table
- SYMBOLIC params: seed as `Dynamic` for untyped languages instead of UNKNOWN

**Phase C — Frontend seeding:** (Gaps 3, 6, 15)
- Seed class field types from frontend class declarations
- Thread parameterised array types from frontends
- Per-frontend improvement targets: Python annotations (biggest win),
  C struct fields, Java generic type parsing
- Establish minimum seeding quality bar per language tier

**Phase D — Inference improvements:** (Gaps 1, 2, 5, 13)
- Multi-pass or call-graph-ordered inference for forward references
- Nested scope chain for closures; allow widening seeded types
- Tighten method return type resolution: require receiver type, walk
  inheritance chain (parent classes + interfaces)
- Support overload lists for standalone functions (merge into unified
  `method_signatures` system)

**Phase E — Multi-module & linking:** (Gap 16)
- Merge per-module `TypeEnvironmentBuilder` states during linking
- Ensure register rebasing preserves type mappings

**Phase F — Advanced:** (Gaps 8, 14)
- Type narrowing after branches (requires dominator analysis)
- Generic instantiation: unify type variables at call sites

**Phase G — VM trust (optional):** (Gap 17)
- If inference is sufficiently complete, VM can trust static types for
  typed languages and skip `typed_from_runtime()` re-derivation
- Only worthwhile after Phases A-F achieve near-zero UNKNOWN rates

---

## 6. Open Questions

1. **Should the VM trust inferred types or keep runtime type-checking?**
   If inference is complete and verified, the VM could skip `typed_from_runtime()`
   for typed languages and use the pre-computed type directly.  This would be
   a performance win but requires high confidence in inference correctness.
   (See Gap 17 for current underuse framing.)

2. **How should multi-pass inference interact with multi-module linking?**
   If module A calls module B, the linker merges IR — does inference run
   before or after linking?  Currently it runs per-module, but per-module
   seeds are lost during linking (Gap 16).  Options: (a) infer per-module
   then merge type envs, (b) merge IR then infer once, (c) both.

3. **What's the right granularity for coverage metrics?**
   Per-register? Per-function? Per-module? Per-language? All of the above?
   Need to distinguish "UNKNOWN because dynamic" from "UNKNOWN because
   inference failed" — which requires Gap 4 (Dynamic type) first.

4. **Should `Dynamic` propagate through operations?**
   If `x: Dynamic` and `y: Int`, is `x + y` -> `Dynamic` or `UNKNOWN`?
   Probably `Dynamic` — the operation will succeed at runtime, we just
   can't predict the result type statically.

5. **What is the minimum seeding quality bar per language tier?**
   Typed languages (Java, Go, TypeScript, Rust, C, C++, Kotlin, Swift,
   Scala) should target ~95%+ seeded coverage.  Dynamic languages (Python,
   Ruby, Lua, PHP, JS) might target ~50% with annotations.  Where do
   "gradually typed" languages (TypeScript, Python with PEP 484) fall?

6. **How should generic type parameters be represented during seeding?**
   Java frontends currently pass `"List<String>"` as a raw string.
   Should this be parsed into `ParameterizedType("List", (scalar("String"),))`
   during lowering, or should inference handle the parsing?  (Gap 14)

7. **Should overload resolution move to a pre-execution phase?**
   Currently overloads are resolved at VM dispatch time.  If inference
   can resolve most overloads statically, the VM could skip the runtime
   lookup entirely.  This connects Gap 13 (overload data model) with
   Gap 17 (VM trust).
