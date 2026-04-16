# pyright: standard
"""Semantic feature enumeration for the C# language frontend.

Each member represents a distinct language-level feature that the C#
frontend can lower to IR. Use these with the @covers decorator in test
methods to document which feature each test exercises.
"""

from __future__ import annotations

from enum import Enum, auto


class CSharpFeature(Enum):
    """Semantic features of the C# language."""

    # Declarations
    VARIABLE_DECLARATION = auto()
    FUNCTION_DECLARATION = auto()
    CLASS = auto()
    STRUCT = auto()
    INTERFACE = auto()
    RECORD = auto()
    RECORD_STRUCT = auto()
    ENUM = auto()
    DELEGATE = auto()
    LOCAL_FUNCTION = auto()

    # Fields and Properties
    FIELD = auto()
    PROPERTY = auto()
    PROPERTY_ACCESSOR = auto()
    EVENT_FIELD = auto()
    EVENT = auto()

    # Expressions
    ARITHMETIC = auto()
    COMPARISON = auto()
    PREFIX_UNARY = auto()
    POSTFIX_UNARY = auto()
    FUNCTION_CALL = auto()
    METHOD_CALL = auto()
    MEMBER_ACCESS = auto()
    OBJECT_CREATION = auto()
    IMPLICIT_OBJECT_CREATION = auto()
    LAMBDA = auto()
    TUPLE = auto()
    STRING_INTERPOLATION = auto()
    ARRAY_CREATION = auto()
    IMPLICIT_ARRAY_CREATION = auto()
    INITIALIZER = auto()
    CAST = auto()
    TERNARY = auto()
    CONDITIONAL_ACCESS = auto()
    TYPEOF = auto()
    IS_CHECK = auto()
    IS_PATTERN = auto()
    AS_CAST = auto()
    SIZEOF = auto()
    DEFAULT = auto()
    RANGE = auto()
    AWAIT = auto()
    ANONYMOUS_OBJECT = auto()
    WITH_EXPRESSION = auto()
    ELEMENT_ACCESS = auto()

    # Control flow
    IF_ELSE = auto()
    WHILE_LOOP = auto()
    DO_WHILE_LOOP = auto()
    FOR_LOOP = auto()
    FOREACH_LOOP = auto()
    SWITCH_STATEMENT = auto()
    SWITCH_EXPRESSION = auto()
    BREAK_CONTINUE = auto()
    RETURN = auto()
    THROW = auto()
    THROW_EXPRESSION = auto()
    TRY_CATCH = auto()
    GOTO = auto()
    LABELED_STATEMENT = auto()

    # Statements
    LOCK = auto()
    USING = auto()
    CHECKED = auto()
    UNCHECKED = auto()
    FIXED = auto()
    YIELD = auto()
    ASSIGNMENT = auto()
    GLOBAL_STATEMENT = auto()

    # Patterns
    DECLARATION_PATTERN = auto()
    CONSTANT_PATTERN = auto()
    PARENTHESIZED_PATTERN = auto()
    OR_PATTERN = auto()
    AND_PATTERN = auto()
    NOT_PATTERN = auto()
    LIST_PATTERN = auto()
    RELATIONAL_PATTERN = auto()
    RECURSIVE_PATTERN = auto()

    # Namespaces and Imports
    NAMESPACE = auto()
    FILE_SCOPED_NAMESPACE = auto()

    # LINQ
    LINQ_QUERY = auto()
    LINQ_FROM_CLAUSE = auto()
    LINQ_SELECT_CLAUSE = auto()
    LINQ_WHERE_CLAUSE = auto()

    # Special features
    OUT_VAR_DECLARATION = auto()
    REF_PARAM = auto()
    REF_EXPRESSION = auto()
    IN_PARAM = auto()
    OUT_PARAM = auto()
    REF_LOCAL = auto()
    QUERY_EXPRESSION = auto()
    GENERIC_TYPE = auto()
    EMPTY_STATEMENT = auto()
    VERBATIM_STRING = auto()
    CONSTRUCTOR = auto()
    CONSTRUCTOR_CHAINING = auto()
    CHECKED_EXPRESSION = auto()
