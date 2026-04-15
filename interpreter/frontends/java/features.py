"""Java language features for @covers decorator annotation."""

from __future__ import annotations

from enum import Enum, auto


class JavaFeature(Enum):
    """Java language features covered by tests."""

    # Literals
    INTEGER_LITERALS = auto()
    HEX_FLOAT_LITERAL = auto()
    CLASS_LITERAL = auto()
    TEXT_BLOCK = auto()

    # Variables and fields
    LOCAL_VARIABLE = auto()
    FIELD_ACCESS = auto()

    # Operators and expressions
    ASSIGNMENT = auto()
    ARITHMETIC = auto()
    TERNARY = auto()
    INSTANCEOF = auto()
    CAST = auto()

    # Collections
    ARRAY_CREATION = auto()
    ARRAY_ACCESS = auto()

    # Method and function calls
    METHOD_CALL = auto()
    FUNCTION_CALL = auto()
    METHOD_REFERENCE = auto()

    # Control flow
    IF_ELSE = auto()
    WHILE_LOOP = auto()
    DO_WHILE_LOOP = auto()
    FOR_LOOP = auto()
    ENHANCED_FOR_LOOP = auto()
    BREAK_CONTINUE = auto()
    LABELED_STATEMENT = auto()
    SWITCH_EXPRESSION = auto()
    YIELD = auto()

    # Exception handling
    TRY_CATCH = auto()
    THROW = auto()

    # Classes and objects
    CLASS = auto()
    CONSTRUCTOR = auto()
    OBJECT_CREATION = auto()
    METHOD_DECLARATION = auto()

    # Advanced features
    LAMBDA = auto()
    GENERIC_TYPES = auto()
    INTERFACE = auto()
    ENUM = auto()
    ANNOTATION_TYPE = auto()
    ANNOTATIONS = auto()
    MODIFIERS = auto()
    STATIC_INITIALIZER = auto()
    SYNCHRONIZED = auto()
    SUPER = auto()
    EXPLICIT_CONSTRUCTOR_INVOCATION = auto()
    FORMAL_PARAMETERS = auto()
    INFERRED_PARAMETERS = auto()

    # Pattern matching (Java 16+)
    RECORD = auto()
    RECORD_PATTERN = auto()
    TYPE_PATTERN = auto()

    # Comments
    COMMENT_HANDLING = auto()

    # Scoping
    SCOPED_IDENTIFIER = auto()
    ASSERT = auto()
