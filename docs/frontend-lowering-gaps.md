# Frontend Lowering Gap Analysis

**Date**: 2026-03-10
**Method**: Cross-referenced each frontend's `_build_stmt_dispatch()` / `_build_expr_dispatch()` tables against tree-sitter `node-types.json` grammar definitions. Unhandled named node types (excluding punctuation, structural/internal nodes consumed by parent handlers, and comment/noise types) are classified as gaps.

**Totals: 25 P0 (25 DONE, 0 remaining), 187 P1, ~326 P2**

---

## Summary Table

| Language | Dispatched | P0 | P1 | P2 | Biggest Risk |
|----------|-----------|----|----|-----|-------------|
| Python | 76 | 0 | 9 | ~25 | Match statement sub-patterns |
| JavaScript | 63 | 0 | 7 | ~30 | `optional_chain`, anonymous `class`, `decorator` |
| TypeScript | ~74 | 0 | 18 | ~35 | Inherits JS gaps + `decorator`, `type_assertion` |
| Java | 64 | 0 | 11 | 14 | All P0 gaps resolved |
| C# | 84 | 0 | 27 | 16+ | All P0 gaps resolved |
| Kotlin | 58 | 0 | 14 | 13+ | All P0 gaps resolved |
| Scala | 72 | 0 | 18 | 30+ | All P0 gaps resolved |
| Go | 55 | 0 | 9 | 18 | All P0 gaps resolved |
| Rust | ~78 | 0 | 9 | 25 | All P0 gaps resolved |
| C | 42 | 0 | 4 | ~20 | Most complete; gaps are qualifiers/specifiers |
| C++ | ~64 | 0 | 11 | ~25 | Coroutines, structured bindings, `auto` |
| Ruby | 73 | 0 | 12 | 33 | All P0 gaps resolved |
| PHP | 76 | 0 | 13 | 37 | All P0 gaps resolved |
| Lua | 31 | 0 | 1 | 1 | All P0 gaps resolved |
| Pascal | 43 | 0 | 24 | 24 | All P0 gaps resolved |

---

## All P0 Gaps

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
| 13 | Go | `generic_type` (was `type_instantiation_expression`) | `Foo[int]` -- Go 1.18+ generics | DONE |
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

### Python (9 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `class_pattern` | `case Point(x, y):` -- matches class constructor patterns | TODO |
| `complex_pattern` | Compound/complex patterns in match | TODO |
| `union_pattern` | `case int() \| str():` -- OR patterns in match | TODO |
| `keyword_pattern` | `case Point(x=0, y=0):` -- keyword argument patterns | TODO |
| `tuple_pattern` | `case (x, y):` -- tuple destructuring in match | TODO |
| `pattern_list` | Wrapper for multiple patterns in match case | TODO |
| `as_pattern` | `case x as y:` -- pattern binding | TODO |
| `future_import_statement` | `from __future__ import annotations` | TODO |
| `format_expression` | f-string format expression (distinct from `interpolation`) | TODO |

### JavaScript (7 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `class` | Anonymous class expression: `const Foo = class { ... }` | TODO |
| `decorator` | `@logged class Foo {}` -- TC39 decorators | TODO |
| `optional_chain` | `obj?.prop` -- optional chaining operator | TODO |
| `meta_property` | `new.target` or `import.meta` | TODO |
| `computed_property_name` | `{ [expr]: value }` in object literals | TODO |
| `using_declaration` | `using x = getResource()` -- explicit resource management | TODO |
| `rest_pattern` | `const [first, ...rest] = arr` -- rest elements | TODO |

### TypeScript (18 P1, includes 7 inherited from JS)
| Node Type | Description | Status |
|-----------|-------------|--------|
| *(inherits 7 JS P1s above)* | | |
| `type_assertion` | `<Type>expr` -- angle-bracket type assertion | TODO |
| `instantiation_expression` | `fn<string>` -- instantiation without calling | TODO |
| `ambient_declaration` | `declare module 'x' { ... }` | TODO |
| `function_signature` | Overload signatures | TODO |
| `method_signature` | Interface method signatures | TODO |
| `property_signature` | Interface property signatures | TODO |
| `call_signature` | `(x: number): void` in interfaces | TODO |
| `construct_signature` | `new (x: number): Foo` in interfaces | TODO |
| `index_signature` | `[key: string]: number` | TODO |
| `import_alias` | `import Foo = Bar.Baz` | TODO |
| `import_require_clause` | `import x = require('y')` | TODO |

### Java (11 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `module_declaration` | Java 9 module-info.java declarations | TODO |
| `template_expression` | Java 21 string templates | TODO |
| `hex_floating_point_literal` | `0x1.0p10` hex floats | TODO |
| `record_pattern` | Java 21 record deconstruction patterns | TODO |
| `type_pattern` | Java 16 `x instanceof String s` | TODO |
| `guard` | Java 21 guarded patterns in switch | TODO |
| `wildcard` | Unnamed pattern `_` in switch (Java 21) | TODO |
| `underscore_pattern` | Another representation of unnamed pattern | TODO |
| `compact_constructor_declaration` | Record compact constructors | TODO |
| `constant_declaration` | Interface constant declarations | TODO |
| `string_interpolation` | String interpolation inside templates | TODO |

### C# (27 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `range_expression` | `x..y` range expressions (C# 8) | TODO |
| `with_expression` | `record with { ... }` (C# 9) | TODO |
| `checked_expression` | `checked(expr)` / `unchecked(expr)` | TODO |
| `default_expression` | `default` / `default(T)` | TODO |
| `sizeof_expression` | `sizeof(type)` | TODO |
| `anonymous_object_creation_expression` | `new { X = 1 }` | TODO |
| `anonymous_method_expression` | `delegate { ... }` | TODO |
| `ref_expression` | `ref x` reference expressions | TODO |
| `stackalloc_expression` | `stackalloc int[10]` | TODO |
| `implicit_stackalloc_expression` | `stackalloc[] { 1, 2, 3 }` | TODO |
| `unsafe_statement` | `unsafe { ... }` blocks | TODO |
| `destructor_declaration` | `~ClassName()` finalizers | TODO |
| `indexer_declaration` | `this[int i]` indexer properties | TODO |
| `operator_declaration` | Operator overloading | TODO |
| `conversion_operator_declaration` | Implicit/explicit conversion operators | TODO |
| `file_scoped_namespace_declaration` | `namespace Foo;` (C# 10) | TODO |
| `recursive_pattern` | Recursive/positional pattern matching | TODO |
| `list_pattern` | `[1, 2, ..]` list patterns (C# 11) | TODO |
| `var_pattern` | `var x` pattern | TODO |
| `type_pattern` | Type patterns in switch | TODO |
| `and_pattern` | `pattern1 and pattern2` (C# 9) | TODO |
| `or_pattern` | `pattern1 or pattern2` (C# 9) | TODO |
| `negated_pattern` | `not pattern` (C# 9) | TODO |
| `relational_pattern` | `> 5`, `< 10` patterns (C# 9) | TODO |
| `parenthesized_pattern` | `(pattern)` grouped patterns | TODO |
| `tuple_pattern` | `(x, y)` tuple patterns in switch | TODO |

### Kotlin (14 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `callable_reference` | `::functionName`, `ClassName::method` | TODO |
| `spread_expression` | `*array` spread for varargs | TODO |
| `annotated_lambda` | Lambda with annotations | TODO |
| `secondary_constructor` | `constructor(...)` secondary constructors | TODO |
| `constructor_delegation_call` | `this(...)` or `super(...)` delegation | TODO |
| `constructor_invocation` | Constructor call in supertype list | TODO |
| `explicit_delegation` | `by delegate` delegation pattern | TODO |
| `getter` | Custom property getter | TODO |
| `setter` | Custom property setter | TODO |
| `unsigned_literal` | `42u`, `42UL` unsigned literals | TODO |
| `wildcard_import` | `import foo.*` | TODO |

### Scala (18 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `ascription_expression` | Type ascription `x: Type` | TODO |
| `val_declaration` | Abstract `val` in traits | TODO |
| `var_declaration` | Abstract `var` in traits | TODO |
| `enum_definition` | Scala 3 `enum` definitions | TODO |
| `extension_definition` | Scala 3 `extension` methods | TODO |
| `given_definition` | Scala 3 `given` instances | TODO |
| `given_pattern` | Pattern matching against `given` | TODO |
| `export_declaration` | Scala 3 `export` clauses | TODO |
| `package_object` | `package object foo { ... }` | TODO |
| `quote_expression` | Scala 3 macro quote `'{ ... }` | TODO |
| `splice_expression` | Scala 3 macro splice `${ ... }` | TODO |
| `macro_body` | Macro implementation body | TODO |
| `alternative_pattern` | `case A \| B =>` OR patterns | TODO |
| `capture_pattern` | `case x @ pattern =>` binding | TODO |
| `named_tuple_pattern` | Named tuple destructuring | TODO |
| `repeat_pattern` | `case Seq(xs @ _*) =>` varargs patterns | TODO |
| `named_pattern` | Named patterns in Scala 3 | TODO |

### Go (9 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `fallthrough_statement` | `fallthrough` in switch cases | TODO |
| `rune_literal` | Character literals like `'a'` | TODO |
| `iota` | Auto-incrementing constant generator | TODO |
| `generic_type` | `Map[K, V]` generic type references | TODO |
| `map_type` | `map[K]V` type expressions | TODO |
| `pointer_type` | `*T` type expressions | TODO |
| `array_type` | `[N]T` fixed-size array types | TODO |
| `interface_type` | `interface { ... }` type definitions | TODO |
| `variadic_argument` | `args...` spread operator | TODO |
| `blank_identifier` | `_` blank/discard identifier | TODO |

### Rust (9 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `foreign_mod_item` | `extern "C" { ... }` FFI blocks | TODO |
| `union_item` | `union` type definitions | TODO |
| `macro_definition` | `macro_rules!` definitions | TODO |
| `raw_string_literal` | `r"..."` and `r#"..."#` raw strings | TODO |
| `negative_literal` | Negative number patterns like `-1` | TODO |
| `mut_pattern` | `mut x` mutable binding in patterns | TODO |
| `reference_pattern` | `&x` destructuring references | TODO |
| `slice_pattern` | `[a, b, ..]` slice destructuring | TODO |
| `let_chain` | `let x = ... && let y = ...` chained conditions | TODO |

### C (4 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `linkage_specification` | `extern "C" { ... }` linkage blocks | TODO |
| `sized_type_specifier` | `unsigned int`, `long long` compound types | TODO |
| `storage_class_specifier` | `static`, `extern`, `register`, `auto` | TODO |
| `type_qualifier` | `const`, `volatile`, `restrict` | TODO |

### C++ (11 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `co_await_expression` | C++20 coroutine await | TODO |
| `co_return_statement` | C++20 coroutine return | TODO |
| `co_yield_statement` | C++20 coroutine yield | TODO |
| `fold_expression` | `(args + ...)` template folds (C++17) | TODO |
| `parameter_pack_expansion` | `args...` variadic template expansion | TODO |
| `template_type` | `vector<int>` template type specifier | TODO |
| `template_instantiation` | Explicit `template class Foo<int>` | TODO |
| `decltype` | `decltype(expr)` type deduction | TODO |
| `placeholder_type_specifier` | `auto` / `decltype(auto)` | TODO |
| `operator_name` | `operator+`, `operator<<` overloading names | TODO |
| `destructor_name` | `~ClassName` destructor names | TODO |
| `structured_binding_declarator` | `auto [a, b] = ...` (C++17) | TODO |

### Ruby (12 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `case_match` | Pattern matching `case/in` (Ruby 3.0+) | TODO |
| `hash_splat_argument` | Double-splat `**hash` argument | TODO |
| `splat_argument` | Splat `*array` argument unpacking | TODO |
| `block_argument` | `&block` argument passing | TODO |
| `begin_block` | `BEGIN { ... }` -- pre-main code | TODO |
| `end_block` | `END { ... }` -- post-main code | TODO |
| `hash_pattern` | Hash destructuring in pattern matching | TODO |
| `array_pattern` | Array destructuring in pattern matching | TODO |
| `find_pattern` | `in [*, pattern, *]` find pattern | TODO |
| `match_pattern` | `expr in pattern` single-line match | TODO |
| `test_pattern` | `expr => pattern` test match (Ruby 3.0+) | TODO |
| `in_clause` | `in` clause within `case_match` | TODO |

### PHP (13 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `list_literal` | `list($a, $b) = $arr` destructuring | TODO |
| `include_once_expression` | `include_once 'file.php'` | TODO |
| `require_expression` | `require 'file.php'` | TODO |
| `error_suppression_expression` | `@expr` error suppression | TODO |
| `shell_command_expression` | `` `command` `` shell exec | TODO |
| `sequence_expression` | Comma-separated expressions in `for` | TODO |
| `anonymous_class` | `new class { ... }` | TODO |
| `declare_statement` | `declare(strict_types=1)` | TODO |
| `exit_statement` | `exit(0)` / `die()` | TODO |
| `unset_statement` | `unset($var)` | TODO |
| `attribute_list` | PHP 8 attributes `#[Attribute]` | TODO |
| `attribute_group` | Group of PHP 8 attributes | TODO |
| `attribute` | Single PHP 8 attribute | TODO |

### Lua (1 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `attribute` | Variable attributes `<close>`, `<const>` (Lua 5.4) | TODO |

### Pascal (24 P1)
| Node Type | Description | Status |
|-----------|-------------|--------|
| `unit` | Unit declaration -- Pascal module system | TODO |
| `library` | Library declaration -- DLL/shared lib | TODO |
| `declIntf` | Interface declaration (Object Pascal) | TODO |
| `declProcRef` | Procedure/function reference type | TODO |
| `declField` | Record/class field declaration | TODO |
| `declProp` | Property declaration in classes | TODO |
| `declPropArgs` | Property index parameters | TODO |
| `declSection` | Visibility section (`public`, `private`) | TODO |
| `declHelper` | Class/record helper | TODO |
| `declMetaClass` | `class of TFoo` metaclass type | TODO |
| `declEnum` | Enumerated type declaration | TODO |
| `declEnumValue` | Individual enum value | TODO |
| `declSet` | Set type: `set of Char` | TODO |
| `declString` | String type with length: `string[255]` | TODO |
| `declLabel` / `declLabels` | Label declaration section | TODO |
| `declExport` / `declExports` | DLL export entries | TODO |
| `declVariant` / `declVariantClause` | Variant record parts | TODO |
| `declFile` | `file of T` type declaration | TODO |
| `lambda` | Anonymous function (Delphi 2009+) | TODO |
| `asm` / `asmBody` | Inline assembly block | TODO |
| `exceptionElse` | `else` in `try...except` | TODO |
| `implementation` | `implementation` section of unit | TODO |
| `interface` | `interface` section of unit | TODO |
| `initialization` / `finalization` | Unit init/finit sections | TODO |

---

## Recommended Implementation Order

### Phase 1 -- P0 Quick Wins (high impact, likely simple) -- ALL DONE
1. ~~Lua `method_index_expression`~~ **DONE**
2. ~~Rust `unit_expression`~~ **DONE**
3. ~~Rust `or_pattern`~~ **DONE**
4. ~~Go `type_conversion_expression`~~ **DONE**
5. ~~Go `generic_type`~~ **DONE**
6. ~~Ruby `scope_resolution`~~ **DONE**
7. ~~PHP `const_declaration`, `clone_expression`, `print_intrinsic`~~ **DONE**
8. ~~C# `empty_statement`~~ **DONE**

### Phase 2 -- P0 Medium Effort (10 remaining P0s)
1. Java `yield_statement` -- switch expression support
2. Kotlin `throw_expression`, `anonymous_function`, `when_expression` stmt routing
3. Scala `generic_function`, `postfix_expression`, `stable_identifier`
4. Pascal `foreach`, `goto`/`label`, `declClass`
5. C# `throw_expression`, `goto_statement`, `labeled_statement`
6. Ruby `rescue_modifier`

### Phase 3 -- High-Value P1 Clusters
12. Pattern matching across Python/C#/Scala/Ruby (biggest cross-language gap)
13. JS/TS `optional_chain` + `decorator`
14. C++ coroutines + structured bindings
15. Go generics infrastructure
