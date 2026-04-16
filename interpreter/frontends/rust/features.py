# pyright: standard
"""Semantic feature enumeration for the Rust language frontend."""

from __future__ import annotations

from enum import Enum


class RustFeature(Enum):
    """Semantic features of the Rust language."""

    # Declarations
    LET_BINDING = "let x = expr and let mut x = expr variable bindings"
    FUNCTION_DECLARATION = "fn f(...) -> T function definitions"
    STRUCT = "struct declarations (named, tuple, and unit structs)"
    ENUM = "enum declarations with variants"
    TRAIT = "trait declarations with method signatures"
    IMPL_BLOCK = "impl Type and impl Trait for Type blocks"
    CONST_ITEM = "const NAME: T = expr constant items"
    STATIC_ITEM = "static NAME: T = expr static variable items"
    TYPE_ITEM = "type Alias = T type alias items"
    MOD_ITEM = "mod name { } module declarations"
    EXTERN_CRATE = "extern crate name external crate declarations"
    UNION = "union declarations (unsafe C-like unions)"
    MACRO_DEFINITION = "macro_rules! macro definitions"
    FUNCTION_SIGNATURE = "function signature items in trait definitions"
    FOREIGN_MOD = 'extern "ABI" { } foreign function interface blocks'

    # Expressions
    ARITHMETIC = "+, -, *, /, % arithmetic expressions"
    FUNCTION_CALL = "f(...) function call expressions"
    METHOD_CALL = "obj.method(...) method call expressions"
    FIELD_ACCESS = "struct.field field access expressions"
    MACRO_CALL = "macro_name!(...) macro invocations"
    RANGE_EXPRESSION = "a..b, a..=b, ..b, a.. range expressions"
    TYPE_CAST = "expr as Type cast expressions"
    SCOPED_IDENTIFIER = "Module::item path expressions"
    ASYNC_AWAIT = "async { } blocks and .await expressions"
    TRY_EXPRESSION = "expr? try (question mark) operator"
    UNSAFE_BLOCK = "unsafe { } blocks"
    UNIT_EXPRESSION = "() unit value expressions"
    NEGATIVE_LITERAL = "negative numeric literals like -42"
    RAW_STRING_LITERAL = 'r"..." and r#"..."# raw string literals'
    ARRAY_LITERAL = "[a, b, c] and [val; N] array expressions"
    STRUCT_LITERAL = "Foo { field: val } struct construction expressions"
    TUPLE_LITERAL = "(a, b, c) tuple expressions"
    CLOSURE = "|x, y| expr and |x| { ... } closure expressions"
    INDEX_ACCESS = "a[i] index access expressions"
    REFERENCE = "&expr and &mut expr reference expressions"
    DEREFERENCE = "*expr dereference expressions"
    ASSIGNMENT = "x = expr assignment expressions"
    COMPOUND_ASSIGNMENT = "x += expr, x -= expr compound assignment operators"

    # Control flow
    IF_ELSE = "if cond { } else { } conditional expressions"
    WHILE_LOOP = "while cond { } loop statements"
    FOR_LOOP = "for x in iter { } loop statements"
    LOOP = "loop { } infinite loop expressions"
    MATCH_EXPRESSION = "match expr { pat => expr } match expressions"
    RETURN = "return expr statements"
    BREAK_CONTINUE = "break and continue (with optional labels and values)"

    # Patterns
    DESTRUCTURING = "let (a, b) = tuple and let Foo { x } = s destructuring"
    TUPLE_STRUCT_PATTERN = "Foo(a, b) tuple struct patterns in match"
    STRUCT_PATTERN = "Foo { field: x } struct patterns in match"
    OR_PATTERN = "Pat1 | Pat2 alternative patterns"
    MUT_PATTERN = "ref mut x pattern bindings"
    RANGE_SLICE = "[first, .., last] slice patterns in match"
    LET_CONDITION = "let Pat = expr in if/while conditions"
    MATCH_PATTERN_UNWRAP = "pattern bindings that unwrap enum variants"
    IF_LET = "if let Pat = expr { } conditional pattern matching"
    IF_LET_CHAIN = "if let A = a && let B = b chained let conditions (Rust 1.64+)"
    WHILE_LET = "while let Pat = expr { } loop with pattern matching"

    # Generics
    GENERIC_FUNCTION = "fn f<T: Trait>(...) generic function definitions"

    # Async
    ASYNC_BLOCK = "async { } async block expressions"

    # Test infrastructure
    PRELUDE = "std::prelude items implicitly in scope (Vec, Option, etc.)"
    BOX_OPTION = "Box<T> heap allocation and Option<T> optional values"
