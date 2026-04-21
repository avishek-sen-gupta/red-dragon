# Frontend Feature Coverage Gaps

**Generated**: 2026-04-22
**Method**: Scans `interpreter/frontends/*/features.py` and `interpreter/cobol/features.py` for `XxxFeature` enum members, then cross-references with `@covers(XxxFeature.X)` decorators in `tests/unit/` and `tests/integration/`. Uncovered members = features the frontend handles but no test annotates.
**Regenerate**: `poetry run python scripts/feature_coverage_audit.py --gaps-doc docs/frontend-lowering-gaps.md`

**Totals**: 956 features across 16 languages — 769 covered, 187 uncovered

---

## Summary Table

| Language | Total | Covered | Uncovered | % Covered |
|----------|-------|---------|-----------|-----------|
| c | 48 | 33 | 15 ⚠ | 68% |
| cobol | 112 | 104 | 8 ⚠ | 92% |
| cpp | 84 | 38 | 46 ⚠ | 45% |
| csharp | 94 | 71 | 23 ⚠ | 75% |
| go | 44 | 41 | 3 ⚠ | 93% |
| java | 72 | 72 | 0 | 100% |
| javascript | 40 | 38 | 2 ⚠ | 95% |
| kotlin | 59 | 51 | 8 ⚠ | 86% |
| lua | 25 | 19 | 6 ⚠ | 76% |
| pascal | 47 | 38 | 9 ⚠ | 80% |
| php | 55 | 46 | 9 ⚠ | 83% |
| python | 55 | 46 | 9 ⚠ | 83% |
| ruby | 72 | 67 | 5 ⚠ | 93% |
| rust | 60 | 46 | 14 ⚠ | 76% |
| scala | 53 | 43 | 10 ⚠ | 81% |
| typescript | 36 | 16 | 20 ⚠ | 44% |

---

## Uncovered Features by Language

### c

- `ARRAY_LITERALS` — array declarations with initializer lists
- `BINARY_OPERATORS` — bitwise &, |, ^, <<, >> binary operators
- `BREAK_CONTINUE` — break and continue statements
- `COMMA_OPERATOR` — a, b sequential evaluation comma operator
- `DEFAULT_CASE` — default: case label in switch statements
- `EXTERN_C` — extern "C" linkage specification blocks
- `INCREMENT_DECREMENT` — x++, x--, ++x, --x operators
- `LABELED_STATEMENTS` — label: statement labels for goto targets
- `LOGICAL_OPERATORS` — && and || logical short-circuit operators
- `MACRO_FUNCTION` — function-like macro definitions and expansions
- `POINTER_LOAD` — loading a value through a pointer
- `STRING_CONCATENATION` — adjacent string literal concatenation
- `STRING_LITERAL` — "..." string literals
- `TERNARY_OPERATOR` — cond ? a : b ternary expressions
- `UNARY_OPERATORS` — unary +, -, ~, ! operators

### cobol

- `INSPECT_CONVERTING` — INSPECT x CONVERTING from TO to character conversion
- `READ_AT_END` — AT END clause on READ statements
- `ROUNDED_CLAUSE` — ROUNDED modifier on arithmetic result fields
- `SEARCH_BINARY` — SEARCH ALL table WHEN cond binary table search statements
- `SECTION_FILE` — FILE SECTION file record layout declarations
- `SECTION_LINKAGE` — LINKAGE SECTION parameter and return data declarations
- `SECTION_LOCAL_STORAGE` — LOCAL-STORAGE SECTION per-call local data declarations
- `USAGE_INDEX` — USAGE INDEX table index storage type

### cpp

- `ADDRESS_OF` — &expr address-of operator
- `ARITHMETIC` — +, -, *, /, % arithmetic expressions
- `ARRAY_ACCESS` — a[i] array element access
- `ARRAY_LITERALS` — array declarations with initializer lists
- `ARROW_OPERATOR` — ptr->field pointer member access
- `ASSIGNMENT` — = and compound assignment operators
- `BREAK_CONTINUE` — break and continue statements
- `CAST` — (T)expr C-style casts inherited from C
- `COMMA_OPERATOR` — a, b sequential evaluation comma operator
- `COMPOUND_LITERAL` — (T){...} C-style compound literal expressions
- `CONST_CAST` — const_cast<T>(expr) const qualifier removal
- `DEFAULT_CASE` — default: case label in switch statements
- `DESIGNATED_INITIALIZER` — .field = val C++20 designated initializers
- `DO_WHILE` — do { } while (cond) loops
- `DYNAMIC_CAST` — dynamic_cast<T>(expr) runtime polymorphic cast
- `ENTRY_LABEL` — synthetic entry point label at function start
- `EXTERN_C` — extern "C" linkage specification blocks
- `FIELD_ACCESS` — obj.field dot access
- `FUNCTION_POINTER` — function pointer declarations and calls
- `GOTO` — goto label unconditional jumps
- `IF_INIT` — C++17: if (init; cond) with initializer
- `INCREMENT_DECREMENT` — x++, x--, ++x, --x operators
- `INHERITANCE` — class B : public A inheritance declarations
- `INITIALIZER_LIST` — {a, b, c} brace-enclosed initializer lists
- `LABELED_STATEMENTS` — label: statement labels for goto targets
- `LOGICAL_OPERATORS` — && and || logical short-circuit operators
- `NULLPTR` — nullptr null pointer constant
- `NUMBER_LITERAL` — integer and floating-point numeric literals
- `POINTER_DEREFERENCE` — *ptr dereference operator
- `POINTER_LOAD` — loading a value through a pointer
- `POINTER_STORE` — storing a value through a pointer
- `POINTER_TYPE` — T* pointer type declarations
- `RAW_STRING_LITERAL` — R"(...)" raw string literals
- `REINTERPRET_CAST` — reinterpret_cast<T>(expr) bit-level reinterpretation
- `SIZEOF` — sizeof(T) and sizeof expr size queries
- `STATIC_METHOD_CALL` — Class::method(...) static method calls
- `STRUCTURED_BINDING` — auto [a, b] = pair; C++17 structured bindings
- `STRUCT_DEFINITION` — struct declarations (equivalent to class with public default)
- `SUBSCRIPT_EXPRESSION` — overloaded operator[] subscript calls
- `SWITCH` — switch / case / default statements
- `TERNARY_OPERATOR` — cond ? a : b ternary expressions
- `THIS_POINTER` — this pointer keyword in member functions
- `THROW_EXPRESSION` — throw expr used as an expression
- `THROW_STATEMENT` — throw expr; exception throwing statements
- `UNARY_OPERATORS` — unary +, -, ~, ! operators
- `USER_DEFINED_LITERAL` — 42_km operator"" user-defined literals

### csharp

- `AS_CAST` — expr as Type safe cast expressions
- `CAST` — (T)expr explicit cast expressions
- `CHECKED_EXPRESSION` — checked(expr) overflow-checked arithmetic expressions
- `CONSTRUCTOR` — constructor declarations in class and struct types
- `CONSTRUCTOR_CHAINING` — this(...) and base(...) constructor chaining
- `ELEMENT_ACCESS` — a[i] element access expressions
- `GLOBAL_STATEMENT` — top-level statements outside any type (C# 9+)
- `IMPLICIT_ARRAY_CREATION` — new[]{...} implicitly typed array creation
- `INITIALIZER` — { member = value } object and collection initializers
- `LINQ_FROM_CLAUSE` — from x in source LINQ query clause
- `LINQ_QUERY` — query expression syntax for LINQ
- `LINQ_SELECT_CLAUSE` — select expr LINQ projection clause
- `LINQ_WHERE_CLAUSE` — where cond LINQ filtering clause
- `NAMESPACE` — namespace declarations
- `POSTFIX_UNARY` — postfix unary operators: x++, x--
- `PREFIX_UNARY` — prefix unary operators: ++x, --x, !, ~, -, +
- `PROPERTY_ACCESSOR` — get and set accessor bodies in property declarations
- `RECORD_STRUCT` — record struct declarations (C# 10+)
- `RECURSIVE_PATTERN` — { Prop: P } property / positional patterns
- `REF_EXPRESSION` — ref expr reference expressions
- `STRUCT` — struct type declarations
- `TERNARY` — cond ? a : b ternary expressions
- `UNCHECKED` — unchecked { } overflow-unchecked arithmetic blocks

### go

- `BREAK_CONTINUE` — break and continue statements
- `INDEXING` — a[i] map and slice index access
- `METHOD_DECLARATION` — func (r Receiver) m(...) method declarations

### javascript

- `EXPORT_NAMED` — export { a, b } clause of locally-declared names
- `EXPORT_REEXPORT` — export { a } from './module' re-export from another module

### kotlin

- `ASSIGNMENT` — = and compound assignment operators
- `BREAK_CONTINUE` — break, continue, break@label, continue@label statements
- `DEFAULT_PARAMETERS` — function parameters with default values
- `EXCEPTION_HANDLING` — try / catch / finally exception handling
- `FOR_LOOP_DESTRUCTURING` — for ((a, b) in pairs) destructuring for loops
- `GETTER` — get() { } property getter declarations
- `IMPLICIT_THIS` — implicit this in member access and method calls
- `WHEN_SUBJECT_BINDING` — when (val x = expr) { } subject binding in when

### lua

- `ANONYMOUS_FUNCTION` — function(...) end anonymous function expressions
- `ASSIGNMENT` — x = expr and multi-target assignment statements
- `BREAK` — break loop exit statements
- `DO_BLOCK` — do ... end explicit block scope statements
- `LABEL` — ::label:: label declarations for goto targets
- `TABLE_CONSTRUCTOR` — { k = v, ... } table constructor expressions

### pascal

- `ARRAY_DECLARATION` — array[range] of T array type declarations
- `DEFAULT_PARAMETER_VALUES` — function parameters with default values
- `FIELD_ACCESSORS` — getter/setter field accessor method declarations
- `FIELD_DECLARATION` — field declarations inside class and record types
- `LABEL_DECLARATION` — label n; label declarations for goto targets
- `METHOD_DECLARATION` — method declarations within class body
- `MODULE_NAME` — program Name and unit Name module name declarations
- `SET_LITERAL` — [a, b, c] set literal expressions
- `VISIBILITY_MODIFIERS` — public, private, protected, published visibility sections

### php

- `CLONE` — clone $obj object cloning expressions
- `CONST_DECLARATION` — const NAME = value constant declarations
- `ERROR_SUPPRESSION` — @expr error-suppression operator
- `NAMESPACE_USE` — use Foo\Bar namespace import declarations
- `OBJECT_CREATION` — new ClassName(...) object instantiation
- `SEQUENCE_EXPRESSION` — a, b comma-separated sequential evaluation
- `TERNARY` — cond ? a : b and cond ?: b ternary and Elvis expressions
- `TRY_CATCH_FINALLY` — try / catch / finally exception handling
- `TYPE_CAST` — (int), (string) etc. type cast expressions

### python

- `ATTRIBUTE_ACCESS` — obj.attr attribute access expressions
- `AUGMENTED_ASSIGNMENT` — +=, -=, *=, /= and other augmented assignments
- `CONDITIONAL_EXPRESSION` — a if cond else b ternary expressions
- `DEFAULT_PARAMETERS` — function parameters with default values
- `PARENTHESIZED_EXPRESSION` — expressions wrapped in parentheses
- `RAISE_STATEMENT` — raise ExcType(...) exception raising
- `SUBSCRIPT_ACCESS` — obj[key] subscript / index access
- `TUPLE_UNPACKING` — a, b = value and (a, b) = value destructuring
- `TYPE_HINTS` — function and variable type annotations

### ruby

- `BREAK_STATEMENT` — break and break value loop exit statements
- `ENSURE_CLAUSE` — ensure ... end cleanup clauses
- `NEXT_STATEMENT` — next and next value loop continue statements
- `RAISE` — raise and raise ExcType.new(...) exception raising
- `RESCUE_CLAUSE` — rescue ExcType => e ... rescue clauses in begin/def

### rust

- `ARRAY_LITERAL` — [a, b, c] and [val; N] array expressions
- `ASSIGNMENT` — x = expr assignment expressions
- `BREAK_CONTINUE` — break and continue (with optional labels and values)
- `CLOSURE` — |x, y| expr and |x| { ... } closure expressions
- `COMPOUND_ASSIGNMENT` — x += expr, x -= expr compound assignment operators
- `DEREFERENCE` — *expr dereference expressions
- `IF_LET` — if let Pat = expr { } conditional pattern matching
- `IF_LET_CHAIN` — if let A = a && let B = b chained let conditions (Rust 1.64+)
- `INDEX_ACCESS` — a[i] index access expressions
- `LOOP` — loop { } infinite loop expressions
- `REFERENCE` — &expr and &mut expr reference expressions
- `STRUCT_LITERAL` — Foo { field: val } struct construction expressions
- `TUPLE_LITERAL` — (a, b, c) tuple expressions
- `WHILE_LET` — while let Pat = expr { } loop with pattern matching

### scala

- `AUXILIARY_CONSTRUCTOR` — def this(...) auxiliary constructor declarations
- `BREAK` — break loop exit (via scala.util.control.Breaks)
- `CONSTRUCTOR_DELEGATION` — this(...) constructor delegation calls
- `CONTINUE` — continue loop skip (via scala.util.control.Breaks)
- `DEFAULT_PARAMETERS` — function parameters with default argument values
- `ENUM` — enum Foo { case A, B } enumeration declarations (Scala 3)
- `GUARD` — case pat if cond => guard conditions in match cases
- `INFIX_PATTERN` — P1 op P2 infix extractor patterns
- `LAMBDA_EXPRESSION` — (x: T) => expr and { case pat => expr } lambda expressions
- `TRY_CATCH` — try { } catch { case e => } finally { } exception handling

### typescript

- `ABSTRACT_CLASS` — abstract class declarations
- `ABSTRACT_METHOD` — abstract method declarations in abstract classes
- `ARITHMETIC` — +, -, *, /, % arithmetic expressions
- `CLASS_STATIC_BLOCK` — static { } initializer blocks in classes
- `EXPORT` — export declarations
- `GENERIC_TYPES` — generic type parameters <T> on functions and classes
- `IMPORT` — import declarations
- `IMPORT_ALIAS` — import { X as Y } alias bindings
- `INHERITANCE` — extends clause in class declarations
- `INSTANCEOF` — instanceof type-check expressions
- `INTERFACE_IMPLEMENTATION` — implements clause in class declarations
- `NAMESPACE` — namespace and module declarations
- `PRIVATE_MODIFIER` — private visibility modifier on class members
- `PROTECTED_MODIFIER` — protected visibility modifier on class members
- `PUBLIC_FIELD` — public class field declarations
- `PUBLIC_MODIFIER` — public visibility modifier on class members
- `READONLY_MODIFIER` — readonly modifier on properties and parameters
- `REQUIRE_IMPORT` — require("module") CommonJS-style imports
- `SATISFIES_EXPRESSION` — expr satisfies Type constraint (TypeScript 4.9+)
- `STATIC_MODIFIER` — static modifier on class members

