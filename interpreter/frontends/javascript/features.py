# pyright: standard
"""Semantic feature enumeration for the JavaScript language frontend."""

from __future__ import annotations

from enum import Enum, auto


class JavaScriptFeature(Enum):
    """Semantic features of the JavaScript language."""

    # Declarations
    VARIABLE_DECLARATION = auto()

    # Expressions
    ARITHMETIC = auto()
    TERNARY = auto()
    TEMPLATE_LITERAL = auto()
    FUNCTION_CALL = auto()
    METHOD_CALL = auto()
    OBJECT_LITERAL = auto()
    ARRAY_LITERAL = auto()

    # Control flow
    IF_ELSE = auto()
    WHILE_LOOP = auto()
    FOR_LOOP = auto()
    FOR_IN_LOOP = auto()
    FOR_OF_LOOP = auto()
    BREAK_CONTINUE = auto()
    SWITCH_STATEMENT = auto()
    TRY_CATCH = auto()
    THROW = auto()

    # Functions
    FUNCTION_DECLARATION = auto()
    ARROW_FUNCTION = auto()
    LAMBDA = auto()
    ASYNC_AWAIT = auto()
    GENERATOR = auto()

    # Classes
    CLASS = auto()
    OBJECT_CREATION = auto()
    SUPER = auto()

    # Misc
    IMPORT = auto()
    EXPORT = auto()
    SPREAD = auto()
    DESTRUCTURING = auto()
    OPTIONAL_CHAIN = auto()
    DO_WHILE_LOOP = auto()
    LABELED_STATEMENT = auto()
    REGEX_LITERAL = auto()
