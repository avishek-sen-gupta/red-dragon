# pyright: standard
"""Semantic feature enumeration for the C# language frontend.

Each member represents a distinct language-level feature that the C#
frontend can lower to IR. Use these with the @covers decorator in test
methods to document which feature each test exercises.
"""

from __future__ import annotations

from enum import Enum


class CSharpFeature(Enum):
    """Semantic features of the C# language."""

    # Declarations
    VARIABLE_DECLARATION = "local variable declarations with var and explicit types"
    FUNCTION_DECLARATION = "method declarations in class and struct bodies"
    CLASS = "class declarations including nested classes"
    STRUCT = "struct type declarations"
    INTERFACE = "interface declarations with member signatures"
    RECORD = "record class declarations (C# 9+)"
    RECORD_STRUCT = "record struct declarations (C# 10+)"
    ENUM = "enum type declarations"
    DELEGATE = "delegate type declarations"
    LOCAL_FUNCTION = "local function declarations nested inside methods"

    # Fields and Properties
    FIELD = "field declarations in class and struct bodies"
    PROPERTY = "auto-property and full-property declarations"
    PROPERTY_ACCESSOR = "get and set accessor bodies in property declarations"
    EVENT_FIELD = "event field declarations with delegate type"
    EVENT = "full event declarations with add/remove accessors"

    # Expressions
    ARITHMETIC = "+, -, *, /, % arithmetic expressions"
    COMPARISON = "==, !=, <, >, <=, >= comparison expressions"
    PREFIX_UNARY = "prefix unary operators: ++x, --x, !, ~, -, +"
    POSTFIX_UNARY = "postfix unary operators: x++, x--"
    FUNCTION_CALL = "static method and free function call expressions"
    METHOD_CALL = "instance method call expressions"
    MEMBER_ACCESS = "obj.member dot access expressions"
    OBJECT_CREATION = "new T(...) object instantiation"
    IMPLICIT_OBJECT_CREATION = "new() target-typed object creation (C# 9+)"
    LAMBDA = "x => expr and (x) => { } lambda expressions"
    TUPLE = "(a, b) tuple literals and deconstruction"
    STRING_INTERPOLATION = '$"...{expr}..." interpolated strings'
    ARRAY_CREATION = "new T[n] and new T[]{...} array creation"
    IMPLICIT_ARRAY_CREATION = "new[]{...} implicitly typed array creation"
    INITIALIZER = "{ member = value } object and collection initializers"
    CAST = "(T)expr explicit cast expressions"
    TERNARY = "cond ? a : b ternary expressions"
    CONDITIONAL_ACCESS = "obj?.member and obj?[i] null-conditional access"
    TYPEOF = "typeof(T) type object expressions"
    IS_CHECK = "expr is Type type-check expressions"
    IS_PATTERN = "expr is Pattern pattern-check expressions"
    AS_CAST = "expr as Type safe cast expressions"
    SIZEOF = "sizeof(T) unmanaged type size queries"
    DEFAULT = "default and default(T) default value expressions"
    RANGE = "a..b and ^i range and index expressions (C# 8+)"
    AWAIT = "await expr asynchronous expressions"
    ANONYMOUS_OBJECT = "new { prop = val } anonymous object creation"
    WITH_EXPRESSION = "record with { prop = val } non-destructive mutation"
    ELEMENT_ACCESS = "a[i] element access expressions"

    # Control flow
    IF_ELSE = "if / else if / else conditional branching"
    WHILE_LOOP = "while (cond) loops"
    DO_WHILE_LOOP = "do { } while (cond) loops"
    FOR_LOOP = "for (init; cond; update) loops"
    FOREACH_LOOP = "foreach (T x in collection) loops"
    SWITCH_STATEMENT = "switch / case / default statements"
    SWITCH_EXPRESSION = "switch expressions yielding a value (C# 8+)"
    BREAK_CONTINUE = "break and continue statements"
    RETURN = "return and return expr statements"
    THROW = "throw statement to raise exceptions"
    THROW_EXPRESSION = "throw expr used as an expression"
    TRY_CATCH = "try / catch / finally exception handling"
    GOTO = "goto label and goto case unconditional jumps"
    LABELED_STATEMENT = "label: statement labels for goto targets"

    # Statements
    LOCK = "lock (obj) { } mutual exclusion blocks"
    USING = "using (resource) { } deterministic disposal"
    CHECKED = "checked { } overflow-checked arithmetic blocks"
    UNCHECKED = "unchecked { } overflow-unchecked arithmetic blocks"
    FIXED = "fixed (T* p = &x) { } pointer pinning blocks"
    YIELD = "yield return and yield break in iterator methods"
    ASSIGNMENT = "= and compound assignment operators"
    GLOBAL_STATEMENT = "top-level statements outside any type (C# 9+)"

    # Patterns
    DECLARATION_PATTERN = "T x declaration patterns in is and switch"
    CONSTANT_PATTERN = "literal and null constant patterns"
    PARENTHESIZED_PATTERN = "(pattern) parenthesized patterns"
    OR_PATTERN = "P1 or P2 disjunctive patterns (C# 9+)"
    AND_PATTERN = "P1 and P2 conjunctive patterns (C# 9+)"
    NOT_PATTERN = "not P negation patterns (C# 9+)"
    LIST_PATTERN = "[P1, P2] list patterns (C# 11+)"
    RELATIONAL_PATTERN = "< x, > x, <= x relational patterns (C# 9+)"
    RECURSIVE_PATTERN = "{ Prop: P } property / positional patterns"

    # Namespaces and Imports
    NAMESPACE = "namespace declarations"
    FILE_SCOPED_NAMESPACE = "file-scoped namespace declarations (C# 10+)"

    # LINQ
    LINQ_QUERY = "query expression syntax for LINQ"
    LINQ_FROM_CLAUSE = "from x in source LINQ query clause"
    LINQ_SELECT_CLAUSE = "select expr LINQ projection clause"
    LINQ_WHERE_CLAUSE = "where cond LINQ filtering clause"

    # Special features
    OUT_VAR_DECLARATION = "out T x inline out variable declarations"
    REF_PARAM = "ref parameter modifier in method signatures"
    REF_EXPRESSION = "ref expr reference expressions"
    IN_PARAM = "in parameter modifier for read-only references"
    OUT_PARAM = "out parameter modifier for output parameters"
    REF_LOCAL = "ref local variable declarations"
    QUERY_EXPRESSION = "full LINQ query expressions"
    GENERIC_TYPE = "generic type parameters and arguments"
    EMPTY_STATEMENT = "; empty statement"
    VERBATIM_STRING = '@"..." verbatim string literals'
    CONSTRUCTOR = "constructor declarations in class and struct types"
    CONSTRUCTOR_CHAINING = "this(...) and base(...) constructor chaining"
    CHECKED_EXPRESSION = "checked(expr) overflow-checked arithmetic expressions"
