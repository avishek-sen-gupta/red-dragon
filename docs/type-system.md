# Type System Design Document

RedDragon's type system provides **static type inference** over the universal IR, enabling type-aware operator semantics (e.g. integer division, float promotion) and write-time coercion during VM execution. It is designed for incomplete programs: when type information is missing, the system degrades gracefully to identity (no coercion) rather than failing.

## Architecture Overview

```mermaid
flowchart LR
    subgraph Frontend["Frontend (Lowering)"]
        TS[Tree-sitter Parser]
        CTX[EmitContext]
        TEB[TypeEnvironmentBuilder]
    end

    subgraph Inference["Static Inference"]
        INF[infer_types]
        IC[_InferenceContext]
    end

    subgraph Runtime["VM Execution"]
        VM[Executor]
        CR[TypeConversionRules]
        TR[TypeResolver]
    end

    TS -->|type annotations| CTX
    CTX -->|seed_*_type| TEB
    TEB -->|pre-seeded state| INF
    INF -->|fixpoint walk| IC
    IC -->|.build| TE[TypeEnvironment]
    TE --> VM
    CR --> TR
    TR --> VM
```

The type system operates in three phases:

1. **Frontend extraction** — During IR lowering, frontends extract type annotations from source and seed them into a `TypeEnvironmentBuilder`
2. **Static inference** — `infer_types()` walks the IR to fixpoint, propagating types through registers, variables, and function signatures
3. **Runtime coercion** — During execution, the VM applies write-time coercion when storing values into typed registers

## TypeExpr — Algebraic Data Type for Types

All types in the system are represented as `TypeExpr` values (`interpreter/type_expr.py`), an algebraic data type with the following variants:

| Variant | Example | Description |
|---|---|---|
| `ScalarType("Int")` | `Int`, `String`, `Bool` | Simple non-parameterized type |
| `ParameterizedType("Pointer", (ScalarType("Int"),))` | `Pointer[Int]`, `Map[String, Int]` | Type constructor with arguments |
| `UnionType(frozenset({ScalarType("Int"), ScalarType("String")}))` | `Union[Int, String]` | Union of two or more types |
| `FunctionType(params, return_type)` | `Fn(Int, String) -> Bool` | Callable type with params and return |
| `TypeVar("T", bound=ScalarType("Number"))` | `T: Number` | Bounded generic type variable |
| `UnknownType()` | `""` (falsy) | Sentinel for "type not yet known" |

**String compatibility**: All `TypeExpr` values compare equal to their `str()` representation (`ScalarType("Int") == "Int"` is `True`), enabling gradual migration from string-based type storage.

**Convenience constructors**: `scalar()`, `pointer()`, `array_of()`, `map_of()`, `tuple_of()`, `fn_type()`, `typevar()`, `union_of()`, `optional()`, `unknown()`.

**Parser**: `parse_type("Map[String, Int]")` → `ParameterizedType("Map", (ScalarType("String"), ScalarType("Int")))`. Round-trips through `__str__`.

### Union Types

`UnionType(members: frozenset[TypeExpr])` represents a type that could be any of its members:

- **Construction**: `union_of(*types)` — auto-flattens nested unions, deduplicates, eliminates singletons, filters `UNKNOWN`
- **Optional sugar**: `optional(T)` = `Union[T, Null]`, `is_optional(t)`, `unwrap_optional(t)`
- **Inference**: When a variable is assigned different types on different branches, the engine widens to a union (e.g., `x = 5; x = "hello"` → `Union[Int, String]`)
- **Canonical string**: Members sorted alphabetically: `"Union[Int, String]"` (deterministic hashing)

### Function Types

`FunctionType(params: tuple[TypeExpr, ...], return_type: TypeExpr)` represents callable types:

- **Syntax**: `Fn(Int, String) -> Bool`
- **Inference**: CONST function references get `FunctionType` when param/return types are known; `CALL_UNKNOWN` resolves return types from `FunctionType` targets
- **Subtyping**: Contravariant parameters, covariant return (standard function subtyping)

### Tuple Types

Tuple types use `ParameterizedType("Tuple", (element_types...))` for heterogeneous fixed-size tuples:

- **Construction**: `tuple_of(ScalarType("Int"), ScalarType("String"))` → `Tuple[Int, String]`
- **Per-index tracking**: Inference tracks element types per-index, so `t[0]` on `Tuple[Int, String]` resolves to `Int`
- **Subtyping**: Covariant per-element, same length required

### Type Aliases

Type aliases map alias names to their target types with transitive resolution:

- **Seeding**: Frontends call `seed_type_alias(alias_name, target_type)` (e.g., C `typedef int UserId;` → `UserId = Int`)
- **Resolution**: `_resolve_alias()` expands transitively with cycle protection (depth limit 20)
- **Available aliases**: `TypeEnvironment.type_aliases` provides the full alias map for inspection

### Interface/Trait Typing

Java `implements` (and similar) clauses create class→interface edges in the TypeGraph:

- **TypeNode.kind**: `"class"` (default) or `"interface"`
- **Seeding**: `seed_interface_impl(class_name, interface_name)` during frontend lowering
- **TypeGraph extension**: `extend_with_interfaces(implementations)` adds interface nodes (parented under `Any`) and class→interface edges
- **Result**: `Dog ⊆ Comparable` subtype checks work after extension

### Bounded Type Variables

`TypeVar(name: str, bound: TypeExpr = UNKNOWN)` represents generic type parameters:

- **Construction**: `typevar("T", bound=scalar("Number"))` → `T: Number`
- **Unbounded**: Defaults to `Any` — any concrete type satisfies it
- **Subtyping**: A concrete type satisfies `T: Number` iff it's a subtype of `Number`; a `TypeVar` child is a subtype if its bound is

## Type Hierarchy

The default type hierarchy is a DAG rooted at `ANY` with 12 nodes:

```mermaid
graph TD
    ANY["ANY"]
    NUMBER["NUMBER"]
    INT["INT"]
    FLOAT["FLOAT"]
    STRING["STRING"]
    BOOL["BOOL"]
    OBJECT["OBJECT"]
    ARRAY["ARRAY"]
    POINTER["POINTER"]
    MAP["MAP"]
    TUPLE["TUPLE"]
    REGION["REGION"]

    ANY --> NUMBER
    ANY --> STRING
    ANY --> BOOL
    ANY --> OBJECT
    ANY --> ARRAY
    ANY --> POINTER
    ANY --> MAP
    ANY --> TUPLE
    ANY --> REGION
    NUMBER --> INT
    NUMBER --> FLOAT
```

**`TypeNode`** (`interpreter/type_node.py`) — Each node is a frozen dataclass with a `name`, a tuple of `parents`, and a `kind` (`"class"` or `"interface"`).

**`TypeGraph`** (`interpreter/type_graph.py`) — Immutable DAG built from a tuple of `TypeNode` values. Supports both string-based and TypeExpr-based operations:

### String-Based Operations (Legacy)

| Operation | Algorithm | Complexity |
|---|---|---|
| `contains(t)` | Dict lookup | O(1) |
| `is_subtype(child, parent)` | BFS from child through parent edges | O(V + E) |
| `common_supertype(a, b)` | Intersect BFS ancestor lists; return first common | O(V + E) |
| `extend(nodes)` | Merge and return new graph (immutable) | O(V) |

### TypeExpr-Based Operations

| Operation | Description |
|---|---|
| `is_subtype_expr(child, parent)` | Full TypeExpr subtype check with union, function, variance, TypeVar support |
| `common_supertype_expr(a, b)` | LUB of two TypeExpr values with union merge, pairwise LUB |
| `extend_with_interfaces(impls)` | Add class→interface edges to the graph |
| `with_variance(registry)` | Return new graph with variance annotations |

### Variance Annotations

The `variance_registry` maps constructor names to per-argument variance:

| Variance | Subtype Rule | LUB Rule | Example |
|---|---|---|---|
| `COVARIANT` (default) | child arg ⊆ parent arg | Standard LUB | `List[Int] ⊆ List[Number]` |
| `CONTRAVARIANT` | parent arg ⊆ child arg | Standard LUB | Function params |
| `INVARIANT` | args must be equal | Must be equal (else Any) | `MutableList[Int] ⊄ MutableList[Number]` |

Unlisted constructors default to all-covariant (backwards-compatible).

### Subtype Check Algorithm

```mermaid
flowchart TD
    Start["is_subtype(child, parent)"]
    EQ{child == parent?}
    EXISTS{Both in graph?}
    BFS["BFS from child<br/>through parent edges"]
    FOUND{Reached parent?}
    TRUE["return True"]
    FALSE["return False"]

    Start --> EQ
    EQ -->|yes| TRUE
    EQ -->|no| EXISTS
    EXISTS -->|no| FALSE
    EXISTS -->|yes| BFS
    BFS --> FOUND
    FOUND -->|yes| TRUE
    FOUND -->|no| FALSE
```

### Least Upper Bound (common_supertype)

```mermaid
flowchart TD
    Start["common_supertype(a, b)"]
    EQ{a == b?}
    EXISTS{Both in graph?}
    ANC_A["ancestors_a = BFS ancestors of a"]
    ANC_B["ancestors_b = BFS ancestors of b"]
    INTERSECT["common = ancestors_a ∩ ancestors_b<br/>(preserving BFS order of a)"]
    RESULT{common non-empty?}
    RET["return common[0]"]
    ANY["return ANY"]

    Start --> EQ
    EQ -->|yes| RET
    EQ -->|no| EXISTS
    EXISTS -->|no| ANY
    EXISTS -->|yes| ANC_A
    ANC_A --> ANC_B
    ANC_B --> INTERSECT
    INTERSECT --> RESULT
    RESULT -->|yes| RET
    RESULT -->|no| ANY
```

The BFS order ensures the **closest** common ancestor is returned, not just any common ancestor. For example, `common_supertype(INT, FLOAT)` returns `NUMBER` (not `ANY`).

The graph can be extended with user-defined class types at runtime via `extend()`, which merges new `TypeNode` entries (e.g. `TypeNode("Dog", ("Animal",))`) into a new immutable graph.

## Phase 1: Frontend Type Extraction

During IR lowering, the `TreeSitterEmitContext` provides seeding methods that populate the `TypeEnvironmentBuilder`:

| Method | Seeds | Example |
|---|---|---|
| `seed_register_type(reg, type)` | `register_types["%3"] = ScalarType("Int")` | Typed parameter `int x` → `%3 = Int` |
| `seed_var_type(var, type)` | `var_types["x"] = ScalarType("Int")` | Typed declaration `int x = 5` |
| `seed_param_type(name, type)` | `func_param_types["func_add_0"].append(("x", "Int"))` | Function param `(int x)` |
| `seed_func_return_type(label, type)` | `func_return_types["func_add_0"] = ScalarType("Int")` | Return annotation `-> int` |
| `seed_type_alias(alias, target)` | `type_aliases["UserId"] = ScalarType("Int")` | `typedef int UserId;` |
| `seed_interface_impl(class, iface)` | `interface_implementations["Dog"].append("Comparable")` | `class Dog implements Comparable` |

Type annotations are extracted via `extract_type_from_field()` and normalized through `normalize_type_hint()`, which maps language-specific type names to canonical names (e.g. `int` → `Int`, `double` → `Float`, `str`/`String`/`string` → `String`).

Languages with explicit type annotations (Java, C#, C++, Kotlin, TypeScript, Scala) produce richer seeds. Dynamically-typed languages (Python, Ruby, JavaScript, PHP) produce fewer seeds — the inference pass fills in the gaps.

### TypeEnvironmentBuilder

`TypeEnvironmentBuilder` (`interpreter/type_environment_builder.py`) is a mutable dataclass that accumulates type information during lowering:

```
register_types:            dict[str, TypeExpr]                    # "%0" → ScalarType("Int")
var_types:                 dict[str, TypeExpr]                    # "x"  → ScalarType("Int")
func_return_types:         dict[str, TypeExpr]                    # "func_add_0" → ScalarType("Int")
func_param_types:          dict[str, list[tuple[str, str]]]       # "func_add_0" → [("a", "Int"), ("b", "Int")]
type_aliases:              dict[str, TypeExpr]                    # "UserId" → ScalarType("Int")
interface_implementations: dict[str, list[str]]                   # "Dog" → ["Comparable", "Serializable"]
```

Its `.build()` method freezes the accumulated state into an immutable `TypeEnvironment`.

## Phase 2: Static Type Inference

`infer_types()` (`interpreter/type_inference.py`) walks the IR instruction list to fixpoint, adding inferred types on top of the pre-seeded state.

### Fixpoint Algorithm

```mermaid
flowchart TD
    INIT["Initialize _InferenceContext<br/>from TypeEnvironmentBuilder seeds"]
    WALK["Walk all instructions,<br/>dispatching each to handler"]
    SIZE["current_size = |register_types| + |func_return_types|"]
    CMP{current_size > prev_size?}
    BUILD["Freeze into TypeEnvironment<br/>via builder.build()"]
    RET["Return TypeEnvironment"]

    INIT --> WALK
    WALK --> SIZE
    SIZE --> CMP
    CMP -->|yes: new types discovered| WALK
    CMP -->|no: fixpoint reached| BUILD
    BUILD --> RET
```

The fixpoint loop resolves forward references: if function `A` calls function `B` (defined later in the IR), the first pass may not know `B`'s return type. On the second pass, `B`'s return type is available and propagates into `A`'s call site.

Convergence is guaranteed because each pass can only **add** entries to `register_types` and `func_return_types` (never remove or modify), and both maps are bounded by the finite set of registers and function labels in the IR.

### Per-Opcode Inference Rules

The inference walk dispatches each instruction to a handler via the `_DISPATCH` table (19 opcodes handled):

| Opcode | Inference Rule |
|---|---|
| `LABEL` | Track current function label and class scope |
| `SYMBOLIC` | Infer `self`/`this` parameter type from class scope; collect param types |
| `CONST` | Infer literal type: `42` → Int, `3.14` → Float, `"hello"` → String, `True`/`False` → Bool; extract function/class ref mappings |
| `LOAD_VAR` | Copy variable type to result register; track register→variable source |
| `STORE_VAR` | Copy source register type to variable (skip if already seeded) |
| `BINOP` | Delegate to `TypeResolver.resolve_binop()` for result type |
| `UNOP` | Fixed types for `not`/`!` → Bool, `#`/`~` → Int; otherwise propagate operand type |
| `NEW_OBJECT` | Result type = class name from operand |
| `NEW_ARRAY` | Result type = Array |
| `CALL_FUNCTION` | Look up function return type from `func_return_types`, then `_BUILTIN_RETURN_TYPES` |
| `CALL_METHOD` | Look up class method return type, then `func_return_types`, then `_BUILTIN_METHOD_RETURN_TYPES` |
| `CALL_UNKNOWN` | Resolve target register to source variable name, then look up return type |
| `STORE_FIELD` | Record field type for class→field mapping |
| `LOAD_FIELD` | Look up field type from class→field mapping |
| `STORE_INDEX` | Record element type for array register |
| `LOAD_INDEX` | Look up element type from array register |
| `ALLOC_REGION` | Result type = "Region" |
| `LOAD_REGION` | Result type = Array |
| `RETURN` | Record return type for current function label |

### Builtin Type Knowledge

The inference engine has built-in knowledge of common function and method return types across languages:

**Builtin functions** (12 entries): `len` → Int, `int` → Int, `float` → Float, `str` → String, `bool` → Bool, `range` → Array, `abs`/`max`/`min` → Number, `arrayOf`/`intArrayOf`/`Array` → Array

**Builtin methods** (60+ entries), organized by return type:
- **→ String**: `upper`, `lower`, `strip`, `replace`, `format`, `join`, `capitalize`, `title`, `trim`, `toLowerCase`, `toUpperCase`, `substring`, `charAt`, `toString`, `concat`, `downcase`, `upcase`, `gsub`, `sub`, `encode`, `decode`, ...
- **→ Int**: `find`, `index`, `rfind`, `count`, `indexOf`, `lastIndexOf`, `size`, `length`
- **→ Bool**: `startswith`, `endswith`, `isdigit`, `isalpha`, `startsWith`, `endsWith`, `includes`, `contains`, `isEmpty`, `has`
- **→ Array**: `split`, `splitlines`, `keys`, `values`, `items`, `entries`, `toArray`, `toList`

### TypeEnvironment (Output)

The inference pass produces a frozen `TypeEnvironment` (`interpreter/type_environment.py`):

```
register_types:            MappingProxyType[str, TypeExpr]                # "%0" → ScalarType("Int")
var_types:                 MappingProxyType[str, TypeExpr]                # "x"  → ScalarType("Int")
func_signatures:           MappingProxyType[str, FunctionSignature]       # "add" → FunctionSignature(...)
type_aliases:              MappingProxyType[str, TypeExpr]                # "UserId" → ScalarType("Int")
interface_implementations: MappingProxyType[str, tuple[str, ...]]         # "Dog" → ("Comparable",)
scoped_var_types:          MappingProxyType[str, MappingProxyType[str, TypeExpr]]  # per-function scoped types
var_scope_metadata:        MappingProxyType[str, VarScopeInfo]            # "x$1" → VarScopeInfo("x", 1)
```

`FunctionSignature` is a frozen dataclass with `params: tuple[tuple[str, str], ...]` and `return_type: str`. Only user-facing function names (not internal labels like `func_add_0`) appear in `func_signatures`.

`scoped_var_types` preserves per-function variable types without flattening — useful for scope-aware analysis. `var_scope_metadata` maps mangled variable names back to their original names and scope depths.

All fields use `MappingProxyType` for true immutability — the environment cannot be modified after construction.

### Block-Scope Tracking (LLVM-style)

For block-scoped languages (Java, C, C++, C#, Rust, Go, Kotlin, Scala, TypeScript `let`/`const`), `TreeSitterEmitContext` provides LLVM-style scope tracking that disambiguates variable names at IR emission time:

| Method | Purpose |
|---|---|
| `enter_block_scope()` | Push a new block scope onto the stack |
| `exit_block_scope()` | Pop the innermost scope |
| `declare_block_var(name) → str` | Declare a variable; returns mangled name if shadowing |
| `resolve_var(name) → str` | Resolve name through scope stack (innermost first) |
| `reset_block_scopes()` | Clear all scopes (used at function boundaries) |
| `var_scope_metadata` | `dict[str, VarScopeInfo]` — mangled→original metadata |

When `declare_block_var("x")` detects that `x` already exists in an outer scope, it generates a mangled name (`x$1`, `x$2`, ...) and records `VarScopeInfo(original_name="x", scope_depth=N)`. The IR then uses the mangled name, so the inference engine sees distinct variables. Function-scoped languages (Python, JavaScript `var`, Ruby, Lua, PHP, Pascal) bypass this entirely.

The `flat_var_types()` method on `_InferenceContext` merges per-scope variable types using `union_of()` when the same name appears in multiple scopes with different types, rather than last-writer-wins overwriting.

## Phase 3: Runtime Type Coercion

During VM execution, type coercion is applied at **write time** — every register store passes through `_coerce_value()`.

### Coercion Flow

```mermaid
flowchart TD
    WRITE["apply_update: store val into reg"]
    IS_REG{reg starts with '%'?}
    HAS_TYPE{"type_env.register_types<br/>has reg?"}
    RT["runtime_type = type(val)"]
    MATCH{runtime_type == target_type?}
    COERCE["coercer = rules.coerce_assignment(<br/>runtime_type, target_type)"]
    APPLY["val = coercer(val)"]
    STORE["Store val in register"]
    PASS["Store val unchanged"]

    WRITE --> IS_REG
    IS_REG -->|no| PASS
    IS_REG -->|yes| HAS_TYPE
    HAS_TYPE -->|no| PASS
    HAS_TYPE -->|yes| RT
    RT --> MATCH
    MATCH -->|yes| PASS
    MATCH -->|no| COERCE
    COERCE --> APPLY
    APPLY --> STORE
```

### TypeConversionRules

`TypeConversionRules` (`interpreter/conversion_rules.py`) is an ABC with two methods:

```python
def resolve(operator, left_type, right_type) -> ConversionResult
def coerce_assignment(value_type, target_type) -> Callable[[Any], Any]
```

`DefaultTypeConversionRules` (`interpreter/default_conversion_rules.py`) implements the standard coercion table:

#### Binary Operator Coercion

| Operator | Left | Right | Result Type | Coercion | Override |
|---|---|---|---|---|---|
| `+`, `-`, `*` | Int | Int | Int | — | — |
| `+`, `-`, `*` | Int | Float | Float | left → float() | — |
| `+`, `-`, `*` | Float | Int | Float | right → float() | — |
| `+`, `-`, `*` | Float | Float | Float | — | — |
| `+`, `-`, `*` | Bool | Int | Int | left → int() | — |
| `+`, `-`, `*` | Int | Bool | Int | right → int() | — |
| `/` | Int | Int | Int | — | `//` (floor division) |
| `/` | Int | Float | Float | left → float() | — |
| `/` | Float | Int | Float | right → float() | — |
| `/` | Float | Float | Float | — | — |
| `%` | Int | Int | Int | — | — |
| `==`, `!=`, `<`, `>`, `<=`, `>=` | any | any | Bool | — | — |

The `operator_override` mechanism is key: when both operands are `Int`, `/` is silently rewritten to `//` (Python floor division), preserving integer semantics across all source languages.

#### Assignment Coercion

| Value Type | Target Type | Coercer | Semantics |
|---|---|---|---|
| Float | Int | `math.trunc()` | Truncate toward zero (C/Java semantics) |
| Int | Float | `float()` | Widening promotion |
| Bool | Int | `int()` | `True` → 1, `False` → 0 |
| same | same | identity | No-op |
| other | other | identity | No coercion when types unknown |

### ConversionResult

`ConversionResult` (`interpreter/conversion_result.py`) is the output of binary operator resolution:

```python
@dataclass(frozen=True)
class ConversionResult:
    result_type: str = ""          # Canonical type of the result
    left_coercer: Callable = _identity   # Applied to left operand before eval
    right_coercer: Callable = _identity  # Applied to right operand before eval
    operator_override: str = ""    # Replaces original operator (e.g. "/" → "//")
```

### TypeResolver

`TypeResolver` (`interpreter/type_resolver.py`) composes `TypeConversionRules` with graceful degradation for missing type information:

```mermaid
flowchart TD
    BINOP["resolve_binop(op, left_hint, right_hint)"]
    BOTH_EMPTY{Both hints empty?}
    ONE_MISSING{One hint missing?}
    DELEGATE["Delegate to ConversionRules.resolve(<br/>op, effective_left, effective_right)"]
    IDENTITY["Return IDENTITY_CONVERSION"]

    BINOP --> BOTH_EMPTY
    BOTH_EMPTY -->|yes| IDENTITY
    BOTH_EMPTY -->|no| ONE_MISSING
    ONE_MISSING -->|yes| DELEGATE
    ONE_MISSING -->|no| DELEGATE

    NOTE["When one hint is missing,<br/>assume the other's type<br/>(symmetric fill)"]
    ONE_MISSING -.- NOTE
```

For assignments: if either hint is empty, return identity (no coercion). Both must be known to trigger coercion.

## End-to-End Example

Consider this Java source:

```java
int a = 10;
double b = 3.0;
double c = a + b;
int d = 7 / 2;
```

### Phase 1: Frontend Seeds

The Java frontend extracts type annotations and seeds:
- `var_types["a"] = "Int"`, `var_types["b"] = "Float"`, `var_types["c"] = "Float"`, `var_types["d"] = "Int"`

### Phase 2: Inference Walk

The IR for `c = a + b`:
```
CONST %0 10              → register_types["%0"] = "Int"
STORE_VAR a %0            → var_types["a"] already seeded as "Int"
CONST %1 3.0              → register_types["%1"] = "Float"
STORE_VAR b %1            → var_types["b"] already seeded as "Float"
LOAD_VAR %2 a             → register_types["%2"] = "Int" (from var_types)
LOAD_VAR %3 b             → register_types["%3"] = "Float" (from var_types)
BINOP %4 + %2 %3          → TypeResolver: Int + Float → Float (left coerced to float)
                             register_types["%4"] = "Float"
STORE_VAR c %4            → var_types["c"] already seeded as "Float"
```

The IR for `d = 7 / 2`:
```
CONST %5 7                → register_types["%5"] = "Int"
CONST %6 2                → register_types["%6"] = "Int"
BINOP %7 / %5 %6          → TypeResolver: Int / Int → Int (operator_override = "//")
                             register_types["%7"] = "Int"
STORE_VAR d %7            → var_types["d"] already seeded as "Int"
```

### Phase 3: Runtime Coercion

When `%4` (the `a + b` result) is stored:
1. The `+` BINOP handler sees `ConversionResult(result_type="Float", left_coercer=float)`
2. Left operand `10` is coerced to `10.0` before addition: `10.0 + 3.0 = 13.0`

When `%7` (the `7 / 2` result) is stored:
1. The `/` BINOP handler sees `ConversionResult(result_type="Int", operator_override="//")`
2. The operator is rewritten: `7 // 2 = 3` (floor division, not `3.5`)

When `c = 13.0` is stored into `%4` (target type Float): runtime type matches, no coercion needed.
When `d = 3` is stored into `%7` (target type Int): runtime type matches, no coercion needed.

## Extensibility

The type system is designed for extension via dependency injection:

- **Custom type hierarchies**: Provide additional `TypeNode` entries via `TypeGraph.extend()` to add user-defined class types with inheritance relationships
- **Interface hierarchies**: Use `TypeGraph.extend_with_interfaces()` to add class→interface subtype edges
- **Variance annotations**: Use `TypeGraph.with_variance()` to annotate parameterized type constructors with per-argument variance
- **Custom coercion rules**: Implement `TypeConversionRules` to define domain-specific operator semantics (e.g. COBOL decimal arithmetic)
- **Frontend seeding**: Any frontend can populate the `TypeEnvironmentBuilder` with type information via `seed_register_type()`, `seed_var_type()`, `seed_type_alias()`, `seed_interface_impl()`, etc.
- **Type aliases**: Frontends can register type aliases that are transitively resolved during inference

## File Reference

| File | Role |
|---|---|
| `interpreter/type_expr.py` | `TypeExpr` ADT — `ScalarType`, `ParameterizedType`, `UnionType`, `FunctionType`, `TypeVar`, `UnknownType` |
| `interpreter/type_node.py` | `TypeNode` — frozen dataclass for DAG nodes (with `kind` for class/interface) |
| `interpreter/type_graph.py` | `TypeGraph` — immutable DAG with string and TypeExpr subtype/LUB queries, variance, interface extension |
| `interpreter/constants.py` | `TypeName` enum, `Variance` enum (`COVARIANT`, `CONTRAVARIANT`, `INVARIANT`) |
| `interpreter/type_environment_builder.py` | `TypeEnvironmentBuilder` — mutable accumulator for frontend seeds (types, aliases, interfaces) |
| `interpreter/type_environment.py` | `TypeEnvironment` — frozen inference result |
| `interpreter/function_signature.py` | `FunctionSignature` — frozen param/return type record |
| `interpreter/type_inference.py` | `infer_types()` — fixpoint inference engine with tuple/alias/union support |
| `interpreter/type_resolver.py` | `TypeResolver` — composes rules with missing-hint logic |
| `interpreter/conversion_rules.py` | `TypeConversionRules` — ABC for coercion rules |
| `interpreter/conversion_result.py` | `ConversionResult` — coercion descriptor |
| `interpreter/default_conversion_rules.py` | `DefaultTypeConversionRules` — standard coercion table |
| `interpreter/var_scope_info.py` | `VarScopeInfo` — frozen metadata for mangled block-scoped variable names |
| `interpreter/frontends/context.py` | `TreeSitterEmitContext.seed_*_type()` — frontend seeding API; block-scope tracking |
| `interpreter/vm.py` | `_coerce_value()`, `apply_update()` — runtime coercion |
