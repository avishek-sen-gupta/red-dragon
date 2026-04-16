# pyright: standard
"""Semantic feature enumeration for the Go language frontend."""

from __future__ import annotations

from enum import Enum


class GoFeature(Enum):
    """Semantic features of the Go language."""

    # Declarations
    SHORT_VAR_DECL = ":= short variable declaration"
    VAR_DECLARATION = "var name Type = value declarations"
    CONST_DECLARATION = "const name = value declarations"
    STRUCT = "struct type declarations"
    INTERFACE = "interface type declarations"
    TYPE_ALIAS = "type Foo = Bar or type Foo Bar type declarations"

    # Functions
    FUNCTION_DECLARATION = "func f(...) ReturnType function declarations"
    METHOD_DECLARATION = "func (r Receiver) m(...) method declarations"
    MULTIPLE_RETURN = "functions returning multiple values"
    VARIADIC = "variadic ...T parameters"

    # Expressions
    ASSIGNMENT = "= and multi-variable assignment statements"
    ARITHMETIC = "+, -, *, /, % arithmetic expressions"
    INC_DEC = "x++ and x-- increment/decrement statements"
    FUNCTION_CALL = "f(...) function call expressions"
    METHOD_CALL = "obj.m(...) method call expressions"
    FIELD_ACCESS = "struct field access via dot notation"
    INDEXING = "a[i] map and slice index access"
    COMPOSITE_LITERAL = "T{field: val} struct and collection literals"
    TYPE_ASSERTION = "x.(T) type assertion expressions"
    TYPE_CONVERSION = "T(x) explicit type conversion expressions"
    SLICE_EXPRESSION = "a[lo:hi] slice expressions"
    FUNC_LITERAL = "func(...) { } anonymous function literals"
    MAKE = "make(T, ...) built-in for slices, maps, and channels"
    RUNE_LITERAL = "'c' rune (character) literals"
    BLANK_IDENTIFIER = "_ blank identifier to discard values"
    IOTA = "iota enumeration constant in const blocks"
    CHANNEL_TYPE = "chan T, chan<- T, and <-chan T channel types"
    SLICE_TYPE = "[]T slice type expressions"
    GENERIC_TYPE = "generic type parameters (Go 1.18+)"

    # Control flow
    IF_ELSE = "if / else if / else conditional branching"
    FOR_LOOP = "for init; cond; post traditional loops"
    FOR_RANGE = "for k, v := range collection loops"
    SWITCH_STATEMENT = "switch / case / default statements"
    TYPE_SWITCH = "switch x.(type) type assertion switches"
    SELECT_STATEMENT = "select / case channel multiplexing"
    LABELED_STATEMENT = "labeled statements for targeted break/continue/goto"
    GOTO = "goto label unconditional jumps"
    FALLTHROUGH = "fallthrough in switch cases"
    BREAK_CONTINUE = "break and continue statements"
    RETURN = "return statements (single and multiple values)"

    # Concurrency
    DEFER = "defer statement to schedule function call on return"
    GO_STATEMENT = "go f() goroutine launch statements"
    SEND_STATEMENT = "ch <- val channel send statements"
    RECEIVE_STATEMENT = "<-ch channel receive expressions"
