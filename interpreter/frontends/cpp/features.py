# pyright: standard
"""Semantic feature enumeration for the C++ language frontend.

Each member represents a distinct language-level feature that the C++
frontend can lower to IR.  Use these with the @covers decorator in test
methods to document which feature each test exercises.
"""

from __future__ import annotations

from enum import Enum, auto


class CppFeature(Enum):
    """Semantic features of the C++ language."""

    # Basic declarations
    VARIABLE_DECLARATION = auto()
    DECLARATION_WITHOUT_INITIALIZER = auto()

    # Functions
    FUNCTION_DEFINITION = auto()
    FUNCTION_CALL = auto()
    RETURN_STATEMENT = auto()

    # Control flow
    IF_ELSE = auto()
    IF_INIT = auto()  # C++17: if (init; cond)
    WHILE_LOOP = auto()
    FOR_LOOP = auto()
    DO_WHILE = auto()
    BREAK_CONTINUE = auto()
    SWITCH = auto()
    DEFAULT_CASE = auto()
    LABELED_STATEMENTS = auto()
    GOTO = auto()
    IF_ELSEIF_CHAIN = auto()

    # Classes and objects
    CLASS_DEFINITION = auto()
    CLASS_WITH_METHODS = auto()
    CLASS_WITH_CONSTRUCTOR = auto()
    CLASS_WITH_FIELD_INITIALIZERS = auto()
    FIELD_INITIALIZER_LIST = auto()
    FIELD_INITIALIZER_SINGLE = auto()
    INHERITANCE = auto()
    STRUCT_DEFINITION = auto()

    # Namespaces
    NAMESPACE = auto()

    # Expressions
    NEW_EXPRESSION = auto()
    DELETE_EXPRESSION = auto()
    DELETE_ARRAY = auto()
    LAMBDA_EXPRESSION = auto()
    LAMBDA_CAPTURE = auto()
    BINARY_EXPRESSION = auto()
    UNARY_OPERATORS = auto()
    INCREMENT_DECREMENT = auto()
    TERNARY_OPERATOR = auto()
    COMMA_OPERATOR = auto()
    ARITHMETIC = auto()
    LOGICAL_OPERATORS = auto()

    # Field/pointer access
    FIELD_ACCESS = auto()
    ARROW_OPERATOR = auto()
    ADDRESS_OF = auto()
    POINTER_DEREFERENCE = auto()
    POINTER_LOAD = auto()
    POINTER_STORE = auto()

    # Templates
    TEMPLATE_DECLARATION = auto()
    TEMPLATE_FUNCTION = auto()

    # Type casts
    STATIC_CAST = auto()
    DYNAMIC_CAST = auto()
    REINTERPRET_CAST = auto()
    CONST_CAST = auto()
    CAST = auto()  # C-style casts inherited from C

    # Literals and constants
    EMPTY_PROGRAM = auto()
    UNSUPPORTED_FALLBACK = auto()
    STRING_LITERAL = auto()
    CHAR_LITERAL = auto()
    NUMBER_LITERAL = auto()
    RAW_STRING_LITERAL = auto()
    USER_DEFINED_LITERAL = auto()
    NULLPTR = auto()

    # Method calls
    METHOD_CALL = auto()
    STATIC_METHOD_CALL = auto()

    # Enums
    C_STYLE_ENUM = auto()
    ENUM_CLASS = auto()
    ENUM_CLASS_WITH_VALUES = auto()

    # Exception handling
    TRY_CATCH = auto()
    THROW_STATEMENT = auto()
    THROW_EXPRESSION = auto()

    # Range-based for
    RANGE_FOR = auto()
    STRUCTURED_BINDING = auto()

    # Concepts
    CONCEPT_DEFINITION = auto()

    # Dereferencing and this
    DEREFERENCE_THIS = auto()
    DEREFERENCE_POINTER = auto()
    THIS_POINTER = auto()

    # Array and container operations
    ARRAY_ACCESS = auto()
    SUBSCRIPT_EXPRESSION = auto()

    # Other features
    ASSIGNMENT = auto()
    COMPOUND_LITERAL = auto()
    SIZEOF = auto()
    INITIALIZER_LIST = auto()
    DESIGNATED_INITIALIZER = auto()
    ARRAY_LITERALS = auto()
    FUNCTION_POINTER = auto()
    POINTER_TYPE = auto()

    # Infrastructure
    ENTRY_LABEL = auto()
    EXTERN_C = auto()
