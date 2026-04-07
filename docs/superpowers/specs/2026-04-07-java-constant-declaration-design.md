# Java Constant Declaration Lowering Design

**Date:** 2026-04-07
**Status:** Draft
**Issue:** red-dragon-1ycy
**Related:** red-dragon-ev6r (interface constants, split out)

---

## Problem

The Java frontend does not lower tree-sitter `constant_declaration` nodes.
When Red Dragon encounters class declarations such as:

```java
public static final String GREETING = "hello";
public static final int MAX_SIZE = 100;
public static final String PADDED = "  " + "  ";
```

it currently falls back to unsupported-node handling and produces
`Symbolic(hint='unsupported:constant_declaration')` values instead of
concrete results.

This shows up in the existing integration test
`tests/integration/test_java_constant_declaration.py`, which is currently
`xfail`, and in real Java workloads where class constants feed later runtime
logic.

---

## Scope

This design covers only **class-level** Java `constant_declaration` lowering.

Included:

- `public static final` declarations in class bodies
- declarators with initializer expressions that existing Java expression
  lowering already supports
- emitting concrete `DeclVar` values for those declarations

Excluded:

- interface constant declarations
- new compile-time constant folding rules beyond existing expression lowering
- unrelated Java declaration gaps

The interface case is tracked separately in `red-dragon-ev6r` so this fix can
stay narrow and unblock the current P1 issue.

---

## Existing Structure

The current Java frontend already has the pieces needed for a minimal fix:

- `interpreter/frontends/java/node_types.py` centralizes Java tree-sitter node
  type names
- `interpreter/frontends/java/frontend.py` dispatches statement nodes to
  lowering helpers
- `interpreter/frontends/java/declarations.py` already contains the normal
  declaration helpers, including `lower_local_var_decl()` and field declarator
  extraction logic via `_collect_field_inits()`

The missing piece is that `constant_declaration` is not a recognized Java node
type and is not routed through any declaration lowerer.

---

## Approach Options

### Option 1: Reuse Existing Declaration Lowering Helpers (recommended)

Add `constant_declaration` to the Java node-type table and route it through a
small lowering helper in `declarations.py` that reuses the same declarator /
initializer pattern already used for field and local declarations.

Pros:

- smallest diff
- follows the existing frontend architecture
- keeps expression lowering exactly where it already belongs
- avoids duplicating parsing logic for names and initializer values

Cons:

- requires a small helper split or mild generalization in `declarations.py`

### Option 2: Dedicated Constant-Only Lowerer

Create a fully separate `lower_constant_decl()` implementation with bespoke
logic for traversing `constant_declaration` children.

Pros:

- very explicit semantics

Cons:

- duplicates field-style declarator handling
- introduces a second code path for nearly identical structure

### Option 3: Post-process Unsupported Symbolics

Detect `unsupported:constant_declaration` after lowering and replace it later.

Pros:

- superficially avoids touching frontend dispatch

Cons:

- fixes the symptom instead of the missing lowering support
- fragile and inconsistent with the rest of the frontend

Decision: use **Option 1**.

---

## Design

### Node Type Recognition

Add:

```python
CONSTANT_DECLARATION = "constant_declaration"
```

to `JavaNodeType` so Java lowering code can reference the node without raw
string literals.

### Frontend Dispatch

Register `JavaNodeType.CONSTANT_DECLARATION` in the Java statement dispatch in
`interpreter/frontends/java/frontend.py`.

This keeps constant declarations on the same path as other declaration nodes
and removes the unsupported-node fallback.

### Lowering Strategy

Implement a small lowering helper in `interpreter/frontends/java/declarations.py`
for `constant_declaration` that mirrors the existing declaration pattern:

1. identify each `variable_declarator` child
2. read the declarator name from the `name` field
3. read the initializer from the `value` field
4. lower the initializer through the existing Java expression lowering flow
5. emit `DeclVar(name=VarName(...), value_reg=...)`

This is intentionally simple. We are not adding special constant-folding
semantics. If an initializer expression is already supported by normal Java
expression lowering, constant declarations inherit that behavior automatically.

### Reuse vs. Generalization

The preferred implementation is to share or lightly generalize the existing
field declarator iteration logic rather than creating a separate traversal model.

The code should stay in `declarations.py` and remain local to Java declaration
lowering. No new cross-module abstraction is needed.

---

## Data Flow

After the fix, class constants follow this path:

1. tree-sitter produces `constant_declaration`
2. Java frontend statement dispatch routes it to the Java declarations module
3. declaration lowerer walks each `variable_declarator`
4. initializer expression lowers through existing Java expression dispatch
5. lowerer emits `DeclVar`
6. later reads like `Constants.GREETING` resolve to concrete stored values

The important change is that the frontend now emits real IR for the declaration
site instead of unsupported placeholders.

---

## Error Handling

This change should preserve the current frontend's general failure mode:

- if a declarator has no initializer, emit nothing for that declarator
- if a node is malformed and lacks a `name`, skip it rather than crashing
- if the initializer expression itself is unsupported, let the normal
  expression lowerer produce whatever fallback it already uses

The goal is to make `constant_declaration` behave like other Java declarations,
not to introduce stricter validation rules.

---

## Testing

Primary acceptance coverage already exists:

- `tests/integration/test_java_constant_declaration.py::TestJavaConstantDeclaration::test_static_final_constants_are_concrete`

Planned change to that test:

- remove the `xfail`
- keep the existing assertions that:
  - no symbolics remain for the constants-driven program
  - `g == "hello"`
  - `m == 100`

This is sufficient for the scoped fix because it exercises:

- string constant lowering
- integer constant lowering
- expression-based constant lowering (`"  " + "  "`)
- downstream use of the declared constants at runtime

No new test file is required unless implementation uncovers a missing edge case
that the current integration test does not cover.

---

## Risks

### Declarator Shape Drift

If `constant_declaration` differs subtly from `field_declaration` in child
layout, over-generalizing helper logic could accidentally break one of the two.

Mitigation:

- keep the shared logic narrow and focused on `variable_declarator`
- avoid rewriting unrelated field behavior while implementing the fix

### Scope Creep Into Interfaces

Java interfaces also use `constant_declaration`, but supporting that here would
expand the validation surface and mix two issues.

Mitigation:

- keep interface handling out of this issue
- track it separately in `red-dragon-ev6r`

---

## Acceptance Criteria

`red-dragon-1ycy` is complete when:

- Java `constant_declaration` in class bodies is recognized and lowered
- the frontend emits concrete `DeclVar` values for supported initializer
  expressions
- `tests/integration/test_java_constant_declaration.py::TestJavaConstantDeclaration::test_static_final_constants_are_concrete`
  passes without `xfail`
- no interface-specific behavior is added under this issue
