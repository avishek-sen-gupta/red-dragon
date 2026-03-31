# Frontend Lowering Gap Analysis

**Date**: 2026-03-31 (updated from 2026-03-22)
**Method**: Cross-referenced each frontend's `_build_stmt_dispatch()` / `_build_expr_dispatch()` tables against tree-sitter `node-types.json` grammar definitions. Unhandled named node types (excluding punctuation, structural/internal nodes consumed by parent handlers, and comment/noise types) are classified as gaps.

**Totals: 25 P0 (ALL DONE), ~40+ P1 DONE, ~326 P2 across 15 frontends**

---

## Summary Table

| Language | Dispatched | P0 | P1 Total | P1 Done | P1 Remaining | P2 | Biggest Risk |
|----------|-----------|----|----|---------|-------------|-----|-------------|
| Python | 76 | 0 | 9 | 8 | 1 | ~25 | Complex literal patterns |
| JavaScript | 68 | 0 | 7 | 5 | 2 | ~30 | `decorator`, `using_declaration` |
| TypeScript | ~74 | 0 | 18 | 14 | 4 | ~35 | Inherits JS gaps + `import_alias` |
| Java | 65 | 0 | 11 | 2 | 9 | 14 | Pattern matching (records, types, guards) |
| C# | 97 | 0 | 27 | 7 | 20 | 16+ | Operator overloading, unsafe blocks |
| Kotlin | 76 | 0 | 14 | 10 | 4 | 13+ | Secondary constructors, delegation |
| Scala | 75 | 0 | 18 | 10 | 8 | 30+ | Extension methods, given/using |
| Go | 61 | 0 | 9 | 5 | 4 | 18 | `iota`, type expressions |
| Rust | 86 | 0 | 9 | 9 | 0 | 25 | **All P1 complete** |
| C | 52 | 0 | 4 | 4 | 0 | ~20 | **All P1 complete** |
| C++ | ~64 | 0 | 11 | 2 | 9 | ~25 | Coroutines, operator overloading, structured bindings |
| Ruby | 87 | 0 | 12 | 9 | 3 | 33 | Find patterns, match_pattern |
| PHP | 84 | 0 | 13 | 8 | 5 | 37 | `list_literal`, anonymous classes, attributes |
| Lua | 32 | 0 | 1 | 1 | 0 | 1 | **All P1 complete** |
| Pascal | 46 | 0 | 24 | 0 | 24 | 24 | Units, interfaces, properties, enums |

**Languages with zero P1 gaps remaining: Rust, C, Lua**

---

## All P0 Gaps — ALL DONE

These are core language constructs that would cause SYMBOLIC fallthrough on commonly encountered code.

| # | Language | Node Type | Impact | Status |
|---|----------|-----------|--------|--------|
| 1 | Java | `yield_statement` | Switch expression block arms (`case X -> { yield val; }`) | DONE |
| 2 | C# | `throw_expression` | `x ?? throw new ...` -- idiomatic C# | DONE |
| 3 | C# | `goto_statement` | `goto` / `goto case` / `goto default` | DONE |
| 4 | C# | `labeled_statement` | Labels for goto targets | DONE |
| 5 | C# | `empty_statement` | Bare `;` no-op | DONE |
| 6 | Kotlin | `throw_expression` | `val x = y ?: throw ...` -- throw is an expression | DONE |
| 7 | Kotlin | `when_expression` (stmt) | `when` at statement level may not route through expr dispatch | DONE |
| 8 | Kotlin | `anonymous_function` | `fun(x: Int) { ... }` anonymous function literals | DONE |
| 9 | Scala | `generic_function` | `foo[Int](x)`, `list.asInstanceOf[Bar]` -- ubiquitous | DONE |
| 10 | Scala | `postfix_expression` | `list sorted`, `future await` -- DSL-style calls | DONE |
| 11 | Scala | `stable_identifier` | `pkg.Class` qualified names in patterns/types | DONE |
| 12 | Go | `type_conversion_expression` | `[]byte(s)`, `Foo[int](y)` -- complex type conversions | DONE |
| 13 | Go | `generic_type` | `Foo[int]` -- Go 1.18+ generics | DONE |
| 14 | Rust | `unit_expression` | `()` -- Rust's void, implicit return of many functions | DONE |
| 15 | Rust | `or_pattern` | `A \| B` in match arms -- extremely idiomatic | DONE |
| 16 | Ruby | `scope_resolution` | `Module::Class` -- `::` operator, ubiquitous | DONE |
| 17 | Ruby | `rescue_modifier` | `expr rescue fallback` -- inline error handling | DONE |
| 18 | PHP | `clone_expression` | `clone $obj` -- object cloning | DONE |
| 19 | PHP | `const_declaration` | `const FOO = 1;` -- constant definitions | DONE |
| 20 | PHP | `print_intrinsic` | `print $x` -- distinct from `echo` | DONE |
| 21 | Lua | `method_index_expression` | `obj:method()` -- Lua's primary method call syntax | DONE |
| 22 | Pascal | `foreach` | `for item in collection do` -- iteration | DONE |
| 23 | Pascal | `goto` | Unconditional jump -- required for legacy code | DONE |
| 24 | Pascal | `label` | Label declaration for goto | DONE |
| 25 | Pascal | `declClass` | Class declarations -- core Object Pascal OOP | DONE |

---

## P1 Gaps by Language

### Python (9 P1 — 8 DONE, 1 remaining)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `class_pattern` | `case Point(x, y):` -- matches class constructor patterns | DONE (ADR-111, `__match_args__` support) |
| `complex_pattern` | Compound/complex patterns in match | TODO (`red-dragon-2qem`) |
| `union_pattern` | `case int() \| str():` -- OR patterns in match | DONE (OrPattern) |
| `keyword_pattern` | `case Point(x=0, y=0):` -- keyword argument patterns | DONE |
| `tuple_pattern` | `case (x, y):` -- tuple destructuring in match | DONE (SequencePattern) |
| `pattern_list` | Wrapper for multiple patterns in match case | DONE |
| `as_pattern` | `case x as y:` -- pattern binding | DONE (AsPattern) |
| `future_import_statement` | `from __future__ import annotations` | DONE |
| `format_expression` | f-string format expression (distinct from `interpolation`) | DONE |

### JavaScript (7 P1 — 5 DONE, 2 remaining)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `class` | Anonymous class expression: `const Foo = class { ... }` | DONE |
| `decorator` | `@logged class Foo {}` -- TC39 decorators | TODO |
| `optional_chain` | `obj?.prop` -- optional chaining operator | DONE (ADR-101) |
| `meta_property` | `new.target` or `import.meta` | DONE |
| `computed_property_name` | `{ [expr]: value }` in object literals | DONE |
| `using_declaration` | `using x = getResource()` -- explicit resource management | TODO |
| `rest_pattern` | `const [first, ...rest] = arr` -- rest elements | TODO |

### TypeScript (18 P1, includes 7 inherited from JS — 14 DONE, 4 remaining)
| Node Type | Description | Status |
|-----------|-------------|--------|
| *(inherits JS P1s above)* | | |
| `type_assertion` | `<Type>expr` -- angle-bracket type assertion | DONE |
| `instantiation_expression` | `fn<string>` -- instantiation without calling | DONE |
| `ambient_declaration` | `declare module 'x' { ... }` | DONE |
| `function_signature` | Overload signatures | DONE |
| `method_signature` | Interface method signatures | TODO (ADR-100) |
| `property_signature` | Interface property signatures | DONE (ADR-101) |
| `call_signature` | `(x: number): void` in interfaces | DONE (ADR-101) |
| `construct_signature` | `new (x: number): Foo` in interfaces | DONE (ADR-101) |
| `index_signature` | `[key: string]: number` | DONE (no-op, ADR-101) |
| `import_alias` | `import Foo = Bar.Baz` | TODO |
| `import_require_clause` | `import x = require('y')` | TODO |

### Java (11 P1 — 2 DONE, 9 remaining)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `module_declaration` | Java 9 module-info.java declarations | TODO |
| `template_expression` | Java 21 string templates | TODO |
| `hex_floating_point_literal` | `0x1.0p10` hex floats | DONE |
| `record_pattern` | Java 21 record deconstruction patterns | TODO (`red-dragon-f3m0`) |
| `type_pattern` | Java 16 `x instanceof String s` | TODO (`red-dragon-f3m0`) |
| `guard` | Java 21 guarded patterns in switch | TODO (`red-dragon-f3m0`) |
| `wildcard` | Unnamed pattern `_` in switch (Java 21) | TODO (`red-dragon-f3m0`) |
| `underscore_pattern` | Another representation of unnamed pattern | TODO (`red-dragon-f3m0`) |
| `compact_constructor_declaration` | Record compact constructors | TODO |
| `constant_declaration` | Interface constant declarations | TODO |
| `string_interpolation` | String interpolation inside templates | TODO |

### C# (27 P1 — 7 DONE, 20 remaining)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `range_expression` | `x..y` range expressions (C# 8) | DONE |
| `with_expression` | `record with { ... }` (C# 9) | TODO |
| `checked_expression` | `checked(expr)` / `unchecked(expr)` | DONE |
| `default_expression` | `default` / `default(T)` | DONE |
| `sizeof_expression` | `sizeof(type)` | DONE |
| `anonymous_object_creation_expression` | `new { X = 1 }` | TODO |
| `anonymous_method_expression` | `delegate { ... }` | TODO |
| `ref_expression` | `ref x` reference expressions | TODO |
| `stackalloc_expression` | `stackalloc int[10]` | TODO |
| `implicit_stackalloc_expression` | `stackalloc[] { 1, 2, 3 }` | TODO |
| `unsafe_statement` | `unsafe { ... }` blocks | TODO |
| `destructor_declaration` | `~ClassName()` finalizers | TODO |
| `indexer_declaration` | `this[int i]` indexer properties | TODO |
| `operator_declaration` | Operator overloading | TODO (`red-dragon-cha`) |
| `conversion_operator_declaration` | Implicit/explicit conversion operators | TODO |
| `file_scoped_namespace_declaration` | `namespace Foo;` (C# 10) | DONE |
| `recursive_pattern` | Recursive/positional pattern matching | DONE (Pattern ADT) |
| `list_pattern` | `[1, 2, ..]` list patterns (C# 11) | TODO |
| `var_pattern` | `var x` pattern | TODO |
| `type_pattern` | Type patterns in switch | TODO |
| `and_pattern` | `pattern1 and pattern2` (C# 9) | TODO |
| `or_pattern` | `pattern1 or pattern2` (C# 9) | TODO |
| `negated_pattern` | `not pattern` (C# 9) | TODO |
| `relational_pattern` | `> 5`, `< 10` patterns (C# 9) | TODO |
| `parenthesized_pattern` | `(pattern)` grouped patterns | TODO |
| `tuple_pattern` | `(x, y)` tuple patterns in switch | TODO |

### Kotlin (14 P1 — 10 DONE, 4 remaining)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `callable_reference` | `::functionName`, `ClassName::method` | DONE |
| `spread_expression` | `*array` spread for varargs | DONE (ADR-109) |
| `annotated_lambda` | Lambda with annotations | TODO |
| `secondary_constructor` | `constructor(...)` secondary constructors | TODO |
| `constructor_delegation_call` | `this(...)` or `super(...)` delegation | TODO |
| `constructor_invocation` | Constructor call in supertype list | TODO |
| `explicit_delegation` | `by delegate` delegation pattern | TODO (`red-dragon-nm6`) |
| `getter` | Custom property getter | DONE |
| `setter` | Custom property setter | DONE |
| `unsigned_literal` | `42u`, `42UL` unsigned literals | DONE |
| `wildcard_import` | `import foo.*` | DONE |
| `when_expression` pattern matching | `is Type`, literals, captures in `when` | DONE (ADR-119) |
| `type_test` | `is Type` checks in `when` | DONE (ADR-119) |

### Scala (18 P1 — 10 DONE, 8 remaining)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `ascription_expression` | Type ascription `x: Type` | DONE |
| `val_declaration` | Abstract `val` in traits | DONE |
| `var_declaration` | Abstract `var` in traits | TODO |
| `enum_definition` | Scala 3 `enum` definitions | DONE (ADR, `red-dragon-416`) |
| `extension_definition` | Scala 3 `extension` methods | TODO (`red-dragon-rnm`) |
| `given_definition` | Scala 3 `given` instances | TODO (`red-dragon-fre`) |
| `given_pattern` | Pattern matching against `given` | TODO |
| `export_declaration` | Scala 3 `export` clauses | DONE |
| `package_object` | `package object foo { ... }` | TODO |
| `quote_expression` | Scala 3 macro quote `'{ ... }` | TODO |
| `splice_expression` | Scala 3 macro splice `${ ... }` | TODO |
| `macro_body` | Macro implementation body | TODO |
| `alternative_pattern` | `case A \| B =>` OR patterns | DONE (ADR-118) |
| `capture_pattern` | `case x @ pattern =>` binding | TODO (`red-dragon-4s1a`) |
| `case_class_pattern` | `case Circle(r) =>` destructuring | DONE (ADR-118) |
| `typed_pattern` | `case i: Int =>` type check + bind | DONE (ADR-118) |
| `tuple_pattern` | `case (a, b) =>` tuple matching | DONE (ADR-118) |

### Go (9 P1 — 5 DONE, 4 remaining)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `fallthrough_statement` | `fallthrough` in switch cases | DONE |
| `rune_literal` | Character literals like `'a'` | DONE |
| `iota` | Auto-incrementing constant generator | TODO |
| `generic_type` | `Map[K, V]` generic type references | TODO |
| `map_type` | `map[K]V` type expressions | TODO |
| `pointer_type` | `*T` type expressions | TODO |
| `array_type` | `[N]T` fixed-size array types | TODO |
| `interface_type` | `interface { ... }` type definitions | TODO |
| `variadic_argument` | `args...` spread operator | DONE |
| `blank_identifier` | `_` blank/discard identifier | DONE |

### Rust (9 P1 — ALL DONE)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `foreign_mod_item` | `extern "C" { ... }` FFI blocks | DONE |
| `union_item` | `union` type definitions | DONE |
| `macro_definition` | `macro_rules!` definitions | DONE |
| `macro_invocation` (vec!) | `vec![e1, e2, ...]` array macro | DONE (ADR-131) |
| `raw_string_literal` | `r"..."` and `r#"..."#` raw strings | DONE |
| `negative_literal` | Negative number patterns like `-1` | DONE |
| `mut_pattern` | `mut x` mutable binding in patterns | DONE |
| `reference_pattern` | `&x` destructuring references | DONE (ADR-117, DerefPattern) |
| `slice_pattern` | `[a, b, ..]` slice destructuring | DONE (SequencePattern + StarPattern) |
| `let_chain` | `let x = ... && let y = ...` chained conditions | DONE |

### C (4 P1 — ALL DONE)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `linkage_specification` | `extern "C" { ... }` linkage blocks | DONE |
| `sized_type_specifier` | `unsigned int`, `long long` compound types | DONE |
| `storage_class_specifier` | `static`, `extern`, `register`, `auto` | DONE |
| `type_qualifier` | `const`, `volatile`, `restrict` | DONE |

### C++ (11 P1 — 2 DONE, 9 remaining)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `co_await_expression` | C++20 coroutine await | TODO |
| `co_return_statement` | C++20 coroutine return | TODO |
| `co_yield_statement` | C++20 coroutine yield | TODO |
| `fold_expression` | `(args + ...)` template folds (C++17) | TODO (`red-dragon-jrj`) |
| `parameter_pack_expansion` | `args...` variadic template expansion | TODO |
| `template_type` | `vector<int>` template type specifier | DONE |
| `template_instantiation` | Explicit `template class Foo<int>` | TODO |
| `decltype` | `decltype(expr)` type deduction | DONE |
| `placeholder_type_specifier` | `auto` / `decltype(auto)` | TODO |
| `operator_name` | `operator+`, `operator<<` overloading names | TODO (`red-dragon-3tw`) |
| `destructor_name` | `~ClassName` destructor names | TODO |
| `structured_binding_declarator` | `auto [a, b] = ...` (C++17) | TODO |

### Ruby (12 P1 — 9 DONE, 3 remaining)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `case_match` | Pattern matching `case/in` (Ruby 3.0+) | DONE (ADR-121) |
| `hash_splat_argument` | Double-splat `**hash` argument | DONE |
| `splat_argument` | Splat `*array` argument unpacking | DONE |
| `block_argument` | `&block` argument passing | DONE |
| `begin_block` | `BEGIN { ... }` -- pre-main code | DONE |
| `end_block` | `END { ... }` -- post-main code | DONE |
| `hash_pattern` | Hash destructuring in pattern matching | DONE (ADR-121, MappingPattern) |
| `array_pattern` | Array destructuring in pattern matching | DONE (ADR-121, SequencePattern) |
| `find_pattern` | `in [*, pattern, *]` find pattern | TODO (`red-dragon-swlt`) |
| `match_pattern` | `expr in pattern` single-line match | TODO |
| `test_pattern` | `expr => pattern` test match (Ruby 3.0+) | TODO |
| `in_clause` | `in` clause within `case_match` | DONE (ADR-121) |

### PHP (13 P1 — 8 DONE, 5 remaining)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `list_literal` | `list($a, $b) = $arr` destructuring | TODO |
| `include_once_expression` | `include_once 'file.php'` | DONE |
| `require_expression` | `require 'file.php'` | DONE |
| `error_suppression_expression` | `@expr` error suppression | DONE |
| `shell_command_expression` | `` `command` `` shell exec | TODO |
| `sequence_expression` | Comma-separated expressions in `for` | DONE |
| `anonymous_class` | `new class { ... }` | TODO |
| `declare_statement` | `declare(strict_types=1)` | DONE |
| `exit_statement` | `exit(0)` / `die()` | DONE |
| `unset_statement` | `unset($var)` | DONE |
| `attribute_list` | PHP 8 attributes `#[Attribute]` | TODO |
| `attribute_group` | Group of PHP 8 attributes | TODO |
| `attribute` | Single PHP 8 attribute | TODO |

### Lua (1 P1 — ALL DONE)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `attribute` | Variable attributes `<close>`, `<const>` (Lua 5.4) | DONE |

### Pascal (24 P1 — 0 DONE, 24 remaining)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `unit` | Unit declaration -- Pascal module system | TODO |
| `library` | Library declaration -- DLL/shared lib | TODO |
| `declIntf` | Interface declaration (Object Pascal) | TODO (`red-dragon-u8e`) |
| `declProcRef` | Procedure/function reference type | TODO |
| `declField` | Record/class field declaration | TODO |
| `declProp` | Property declaration in classes | TODO |
| `declPropArgs` | Property index parameters | TODO |
| `declSection` | Visibility section (`public`, `private`) | TODO |
| `declHelper` | Class/record helper | TODO |
| `declMetaClass` | `class of TFoo` metaclass type | TODO |
| `declEnum` | Enumerated type declaration | TODO |
| `declEnumValue` | Individual enum value | TODO |
| `declSet` | Set type: `set of Char` | TODO (`red-dragon-dqo`) |
| `declString` | String type with length: `string[255]` | TODO |
| `declLabel` / `declLabels` | Label declaration section | TODO |
| `declExport` / `declExports` | DLL export entries | TODO |
| `declVariant` / `declVariantClause` | Variant record parts | TODO |
| `declFile` | `file of T` type declaration | TODO |
| `lambda` | Anonymous function (Delphi 2009+) | TODO (`red-dragon-b3x`) |
| `asm` / `asmBody` | Inline assembly block | TODO |
| `exceptionElse` | `else` in `try...except` | TODO |
| `implementation` | `implementation` section of unit | TODO |
| `interface` | `interface` section of unit | TODO |
| `initialization` / `finalization` | Unit init/finit sections | TODO |

---

## Pattern Matching Status

6 of 15 languages now use the common Pattern ADT (`interpreter/frontends/common/patterns.py`). The unified match expression lowering framework (ADR-120, `common/match_expr.py`) eliminates per-language IR emission duplication.

| Language | Pattern ADT | Patterns Supported | ADR |
|----------|------------|-------------------|-----|
| Python | Yes | All 10 types | ADR-111 |
| C# | Yes | Declaration, constant, recursive, discard | — |
| Rust | Yes | Literal, wildcard, capture, or, tuple, struct, scoped id, slice, deref, guard | ADR-117 |
| Scala | Yes | Literal, wildcard, capture, alternative, tuple, case class, typed, stable id, guard | ADR-118 |
| Kotlin | Yes | Literal, wildcard, capture, is-type | ADR-119 |
| Ruby | Yes | Literal, wildcard, capture, alternative, array, splat, as, hash | ADR-121 |
| Java | No | — | TODO (`red-dragon-f3m0`) |
| Go | No | — | TODO (`red-dragon-c1fh`) |
| Others | No | N/A (no native pattern matching) | — |

---

## Architecture (updated 2026-03-22)

### Executor Refactoring
- **HandlerContext** dataclass replaces `**kwargs` in all 31 handlers (ADR, `red-dragon-w358`)
- **Handler family modules** extracted from executor.py (1,855→224 lines, `red-dragon-g85o`)
- **ExecutionStrategies** reduces `execute_cfg` from 13→5 params (`red-dragon-92ho`)

### Shared Infrastructure
- **Unified match framework** (`common/match_expr.py`, ADR-120): `MatchArmSpec` + `lower_match_as_expr`
- **Pattern utilities** (`common/pattern_utils.py`): shared `parse_number`, `resolve_positional_via_match_args`
- **DerefPattern** in Pattern ADT: Rust `&x` reference pattern support
- **match_args resolution**: Option/Box prelude registered in symbol table

---

## Recommended Next Steps

### Highest Impact
1. **C++/C# operator overloading** (`red-dragon-3tw`, `red-dragon-cha`) — blocks real programs using `+`, `<<` on custom types
2. **Java pattern matching** (`red-dragon-f3m0`) — record/type/guard patterns

### Quick Wins
3. **Scala extension methods** (`red-dragon-rnm`) — Scala 3 core feature
4. **Kotlin secondary constructors** — common in Kotlin code

### Systematic
5. **Pascal P1 cluster** (24 items) — if Pascal coverage matters
6. **C# extended patterns** (and/or/not/relational/list) — C# 9-11 features
