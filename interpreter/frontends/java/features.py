"""Java language features for @covers decorator annotation."""

from __future__ import annotations

from enum import Enum, auto


class JavaFeature(Enum):
    """Java language features covered by tests."""

    # Literals
    INTEGER_LITERALS = auto()
    HEX_INTEGER_LITERAL = auto()
    OCTAL_INTEGER_LITERAL = auto()
    BINARY_INTEGER_LITERAL = auto()
    HEX_FLOAT_LITERAL = auto()
    CHARACTER_LITERAL = auto()
    CLASS_LITERAL = auto()
    TEXT_BLOCK = auto()

    # Variables and fields
    LOCAL_VARIABLE = auto()
    FIELD_ACCESS = auto()
    FIELD_INITIALIZATION = auto()
    CONSTANT_DECLARATION = auto()

    # Operators and expressions
    ASSIGNMENT = auto()
    ARITHMETIC = auto()
    UNARY = auto()
    TERNARY = auto()
    INSTANCEOF = auto()
    CAST = auto()
    PARENTHESIZED_EXPRESSION = auto()

    # Collections
    ARRAY_CREATION = auto()
    ARRAY_ACCESS = auto()
    ARRAY_LENGTH = auto()

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
    SWITCH_STATEMENT = auto()
    SWITCH_EXPRESSION = auto()
    SWITCH_RULE = auto()
    YIELD = auto()
    RETURN = auto()

    # Exception handling
    TRY_CATCH = auto()
    TRY_WITH_RESOURCES = auto()
    THROW = auto()
    FINALLY = auto()

    # Classes and objects
    CLASS = auto()
    CONSTRUCTOR = auto()
    COMPACT_CONSTRUCTOR = auto()
    OBJECT_CREATION = auto()
    METHOD_DECLARATION = auto()
    FIELD_DECLARATION = auto()

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
    SPREAD_PARAMETER = auto()

    # Pattern matching (Java 16+)
    RECORD = auto()
    RECORD_PATTERN = auto()
    TYPE_PATTERN = auto()
    PATTERN_GUARD = auto()

    # Scoping and resolution
    SCOPED_IDENTIFIER = auto()
    NAMESPACE_RESOLUTION = auto()

    # Module system (Java 9+)
    MODULE_DECLARATION = auto()
    IMPORT_DECLARATION = auto()
    PACKAGE_DECLARATION = auto()

    # Statements and assertions
    ASSERT = auto()
    COMMENT_HANDLING = auto()
