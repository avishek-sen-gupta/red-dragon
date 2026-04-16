# pyright: standard
"""Semantic feature enumeration for the Python language frontend.

Each member represents a distinct language-level feature that the Python
frontend can lower to IR. Use these with the @covers decorator in test
methods to document which feature each test exercises.
"""

from __future__ import annotations

from enum import Enum


class PythonFeature(Enum):
    """Semantic features of the Python language."""

    # Declarations
    VARIABLE_DECLARATION = "simple name = value assignments at statement level"
    FUNCTION_DECLARATION = "def f(...): function definitions"
    CLASS = "class C: class body definitions"
    TYPE_ALIAS = "type X = Y type alias statements (Python 3.12+)"

    # Expressions
    ARITHMETIC = "+, -, *, /, //, %, ** arithmetic expressions"
    COMPARISON = "==, !=, <, >, <=, >= and chained comparisons"
    FUNCTION_CALL = "f(...) function call expressions"
    METHOD_CALL = "obj.method(...) method call expressions"
    LAMBDA = "lambda x: expr anonymous function expressions"
    NAMED_EXPRESSION = "walrus operator x := expr (Python 3.8+)"
    SLICE_EXPRESSION = "a[start:stop:step] slice expressions"
    TUPLE_EXPRESSION = "(a, b, c) tuple literals"
    F_STRING = 'f"..." formatted string literals'
    SPREAD = "*args unpacking and **kwargs dictionary unpacking"
    ELLIPSIS = "... ellipsis literal"
    ATTRIBUTE_ACCESS = "obj.attr attribute access expressions"
    SUBSCRIPT_ACCESS = "obj[key] subscript / index access"
    CONDITIONAL_EXPRESSION = "a if cond else b ternary expressions"
    PARENTHESIZED_EXPRESSION = "expressions wrapped in parentheses"

    # Control flow
    IF_ELSE = "if / elif / else conditional branching"
    WHILE_LOOP = "while cond: loop statements"
    FOR_LOOP = "for x in iterable: loop statements"
    BREAK_CONTINUE = "break and continue statements"
    TRY_EXCEPT = "try / except / else exception handling"
    WITH_STATEMENT = "with expr as x: context manager blocks"
    MATCH_STATEMENT = "match subject: structural pattern matching (Python 3.10+)"
    ASSERT_STATEMENT = "assert expr and assert expr, msg"
    DELETE_STATEMENT = "del name and del obj.attr"
    GLOBAL_NONLOCAL = "global and nonlocal variable scope declarations"
    RAISE_STATEMENT = "raise ExcType(...) exception raising"

    # Functions and async
    YIELD = "yield expr and yield from expr in generator functions"
    ASYNC_AWAIT = "async def, await expr, async for, async with"
    GENERATOR_EXPRESSION = "(x for x in iterable) generator expressions"
    DECORATOR = "@decorator syntax on function and class definitions"
    DEFAULT_PARAMETERS = "function parameters with default values"
    TYPE_HINTS = "function and variable type annotations"

    # Comprehensions
    LIST_COMPREHENSION = "[x for x in iterable if cond] list comprehensions"
    DICT_COMPREHENSION = "{k: v for k, v in items} dict comprehensions"
    SET_COMPREHENSION = "{x for x in iterable} set comprehensions"
    SET_LITERAL = "{a, b, c} set literals"

    # Assignments
    AUGMENTED_ASSIGNMENT = "+=, -=, *=, /= and other augmented assignments"
    TUPLE_UNPACKING = "a, b = value and (a, b) = value destructuring"

    # Imports
    IMPORT = "import module and import a.b.c statements"
    IMPORT_FROM = "from module import name statements"

    # Pattern Matching (match/case)
    PATTERN_MATCHING = "match statement with case clauses"
    CAPTURE_PATTERN = "case x: name capture in match cases"
    LITERAL_PATTERN = 'case 42 or case "str": literal matching'
    VALUE_PATTERN = "case Enum.MEMBER: dotted value patterns"
    SEQUENCE_PATTERN = "case [a, b]: sequence destructuring patterns"
    MAPPING_PATTERN = 'case {"key": v}: mapping destructuring patterns'
    CLASS_PATTERN = "case Cls(x=a): class attribute destructuring"
    OR_PATTERN = "case P | Q: alternative patterns"
    AS_PATTERN = "case P as x: pattern with alias binding"
    STAR_PATTERN = "case [a, *rest]: star wildcard in sequence patterns"

    # Infrastructure
    SOURCE_LOCATION = "source file and line number attached to IR instructions"
