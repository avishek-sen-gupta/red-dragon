# pyright: standard
"""Semantic feature enumeration for the Rust language frontend."""

from __future__ import annotations

from enum import Enum, auto


class RustFeature(Enum):
    """Semantic features of the Rust language."""

    # Declarations
    LET_BINDING = auto()
    FUNCTION_DECLARATION = auto()
    STRUCT = auto()
    ENUM = auto()
    TRAIT = auto()
    IMPL_BLOCK = auto()
    CONST_ITEM = auto()
    STATIC_ITEM = auto()
    TYPE_ITEM = auto()
    MOD_ITEM = auto()
    EXTERN_CRATE = auto()
    UNION = auto()
    MACRO_DEFINITION = auto()
    FUNCTION_SIGNATURE = auto()
    FOREIGN_MOD = auto()

    # Expressions
    ARITHMETIC = auto()
    FUNCTION_CALL = auto()
    METHOD_CALL = auto()
    FIELD_ACCESS = auto()
    MACRO_CALL = auto()
    RANGE_EXPRESSION = auto()
    TYPE_CAST = auto()
    SCOPED_IDENTIFIER = auto()
    ASYNC_AWAIT = auto()
    TRY_EXPRESSION = auto()
    UNSAFE_BLOCK = auto()
    UNIT_EXPRESSION = auto()
    NEGATIVE_LITERAL = auto()
    RAW_STRING_LITERAL = auto()
    ARRAY_LITERAL = auto()
    STRUCT_LITERAL = auto()
    TUPLE_LITERAL = auto()
    CLOSURE = auto()
    INDEX_ACCESS = auto()
    REFERENCE = auto()
    DEREFERENCE = auto()
    ASSIGNMENT = auto()
    COMPOUND_ASSIGNMENT = auto()

    # Control flow
    IF_ELSE = auto()
    WHILE_LOOP = auto()
    FOR_LOOP = auto()
    LOOP = auto()
    MATCH_EXPRESSION = auto()
    RETURN = auto()
    BREAK_CONTINUE = auto()

    # Patterns
    DESTRUCTURING = auto()
    TUPLE_STRUCT_PATTERN = auto()
    STRUCT_PATTERN = auto()
    OR_PATTERN = auto()
    MUT_PATTERN = auto()
    RANGE_SLICE = auto()
    LET_CONDITION = auto()
    MATCH_PATTERN_UNWRAP = auto()
    IF_LET = auto()
    IF_LET_CHAIN = auto()
    WHILE_LET = auto()

    # Generics
    GENERIC_FUNCTION = auto()

    # Async
    ASYNC_BLOCK = auto()

    # Test infrastructure
    PRELUDE = auto()
    BOX_OPTION = auto()
