# pyright: standard
"""Semantic feature enumeration for the Pascal language frontend."""

from __future__ import annotations

from enum import Enum, auto


class PascalFeature(Enum):
    """Semantic features of the Pascal language."""

    # Declarations
    VARIABLE_DECLARATION = auto()
    CONST_DECLARATION = auto()
    TYPE_DECLARATION = auto()
    USES_CLAUSE = auto()
    PROCEDURE_DECLARATION = auto()
    FUNCTION_DECLARATION = auto()
    CLASS_DECLARATION = auto()
    ENUM_DECLARATION = auto()
    FIELD_DECLARATION = auto()
    ARRAY_DECLARATION = auto()
    DEFAULT_PARAMETER_VALUES = auto()
    MODULE_NAME = auto()

    # Expressions
    ARITHMETIC = auto()
    DOT_ACCESS = auto()
    SUBSCRIPT_ACCESS = auto()
    UNARY_EXPRESSION = auto()
    PARENTHESIZED_EXPRESSION = auto()
    RANGE_EXPRESSION = auto()
    BITWISE_OPERATORS = auto()
    SET_LITERAL = auto()

    # Statements
    ASSIGNMENT = auto()
    PROCEDURE_CALL = auto()
    FUNCTION_CALL = auto()
    LABEL_DECLARATION = auto()

    # Control flow
    IF_ELSE = auto()
    WHILE_LOOP = auto()
    FOR_LOOP = auto()
    REPEAT_UNTIL = auto()
    CASE_STATEMENT = auto()
    FOREACH = auto()
    GOTO = auto()
    WITH_STATEMENT = auto()

    # OOP
    CLASS_BODY = auto()
    PROPERTY_ACCESSORS = auto()
    FIELD_ACCESSORS = auto()
    INHERITED = auto()
    QUALIFIED_PROCEDURE = auto()
    METHOD_DECLARATION = auto()
    VISIBILITY_MODIFIERS = auto()

    # Exception handling
    TRY_EXCEPT = auto()
    TRY_FINALLY = auto()
    EXCEPTION_HANDLER = auto()
    RAISE = auto()

    # Misc
    FALLBACK = auto()
    VAR_TYPE_TRACKING = auto()
    ASSIGNMENT_INTERCEPTION = auto()
    FUNCTION_RESULT = auto()
