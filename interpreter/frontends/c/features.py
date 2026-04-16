# pyright: standard
"""Semantic feature enumeration for the C language frontend.

Each member represents a distinct language-level feature that the C
frontend can lower to IR. Use these with the @covers decorator in test
methods to document which feature each test exercises.
"""

from __future__ import annotations

from enum import Enum


class CFeature(Enum):
    """Semantic features of the C language."""

    # Declarations
    VARIABLE_DECLARATION = "local and global variable declarations"
    FUNCTION_DECLARATION = "function definitions and forward declarations"
    STRUCT = "struct type declarations"
    UNION = "union type declarations"
    ENUM = "enum type declarations"
    TYPEDEF = "typedef type alias declarations"

    # Expressions
    ARITHMETIC = "+, -, *, /, % arithmetic expressions"
    UNARY_OPERATORS = "unary +, -, ~, ! operators"
    BINARY_OPERATORS = "bitwise &, |, ^, <<, >> binary operators"
    LOGICAL_OPERATORS = "&& and || logical short-circuit operators"
    FUNCTION_CALL = "f(...) function call expressions"
    CAST = "(T)expr explicit type cast expressions"
    ADDRESS_OF = "&expr address-of operator"
    POINTER_DEREFERENCE = "*ptr dereference operator"
    POINTER_LOAD = "loading a value through a pointer"
    POINTER_STORE = "storing a value through a pointer"
    SIZEOF = "sizeof(T) and sizeof expr size queries"
    COMPOUND_LITERAL = "(T){...} compound literal expressions"
    ARRAY_ACCESS = "a[i] array element access"
    CHAR_LITERAL = "'c' character literals"
    STRING_LITERAL = '"..." string literals'
    STRING_CONCATENATION = "adjacent string literal concatenation"
    TERNARY_OPERATOR = "cond ? a : b ternary expressions"
    COMMA_OPERATOR = "a, b sequential evaluation comma operator"
    INCREMENT_DECREMENT = "x++, x--, ++x, --x operators"

    # Field access
    FIELD_ACCESS = "struct.field dot access"
    ARROW_OPERATOR = "ptr->field pointer member access"

    # Control flow
    IF_ELSE = "if / else if / else conditional branching"
    WHILE_LOOP = "while (cond) loops"
    FOR_LOOP = "for (init; cond; update) loops"
    DO_WHILE = "do { } while (cond) loops"
    SWITCH = "switch / case / default statements"
    DEFAULT_CASE = "default: case label in switch statements"
    LABELED_STATEMENTS = "label: statement labels for goto targets"
    GOTO = "goto label unconditional jumps"
    BREAK_CONTINUE = "break and continue statements"
    RETURN = "return and return expr statements"

    # Initialization
    INITIALIZER_LIST = "{a, b, c} brace-enclosed initializer lists"
    ARRAY_LITERALS = "array declarations with initializer lists"
    DESIGNATED_INITIALIZER = ".field = val and [i] = val designated initializers"

    # Assignment
    ASSIGNMENT = "= and compound assignment operators (+=, -=, etc.)"

    # Pointers and types
    FUNCTION_POINTER = "function pointer declarations and calls"
    POINTER_TYPE = "T* pointer type declarations"

    # Preprocessor and linkage
    PREPROCESSOR = "#define, #include, #ifdef and other preprocessor directives"
    MACRO = "object-like macro expansions"
    MACRO_FUNCTION = "function-like macro definitions and expansions"
    EXTERN_C = 'extern "C" linkage specification blocks'

    # Infrastructure
    ENTRY_LABEL = "synthetic entry point label at function start"
