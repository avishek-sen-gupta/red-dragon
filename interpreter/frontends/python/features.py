# pyright: standard
"""Semantic feature enumeration for the Python language frontend.

Each member represents a distinct language-level feature that the Python
frontend can lower to IR. Use these with the @covers decorator in test
methods to document which feature each test exercises.
"""

from __future__ import annotations

from enum import Enum, auto


class PythonFeature(Enum):
    """Semantic features of the Python language."""

    # Declarations
    VARIABLE_DECLARATION = auto()
    FUNCTION_DECLARATION = auto()
    CLASS = auto()
    TYPE_ALIAS = auto()

    # Expressions
    ARITHMETIC = auto()
    COMPARISON = auto()
    FUNCTION_CALL = auto()
    METHOD_CALL = auto()
    LAMBDA = auto()
    NAMED_EXPRESSION = auto()
    SLICE_EXPRESSION = auto()
    TUPLE_EXPRESSION = auto()
    F_STRING = auto()
    SPREAD = auto()
    ELLIPSIS = auto()

    # Control flow
    IF_ELSE = auto()
    WHILE_LOOP = auto()
    FOR_LOOP = auto()
    BREAK_CONTINUE = auto()
    TRY_EXCEPT = auto()
    WITH_STATEMENT = auto()
    MATCH_STATEMENT = auto()
    ASSERT_STATEMENT = auto()
    DELETE_STATEMENT = auto()
    GLOBAL_NONLOCAL = auto()

    # Functions and async
    YIELD = auto()
    ASYNC_AWAIT = auto()
    GENERATOR_EXPRESSION = auto()
    DECORATOR = auto()

    # Comprehensions
    LIST_COMPREHENSION = auto()
    DICT_COMPREHENSION = auto()
    SET_COMPREHENSION = auto()
    SET_LITERAL = auto()

    # Imports
    IMPORT = auto()

    # Infrastructure
    SOURCE_LOCATION = auto()
