# pyright: standard
"""Semantic feature enumeration for the Scala language frontend.

Each member represents a distinct language-level feature that the Scala
frontend can lower to IR. Use these with the @covers decorator in test
methods to document which feature each test exercises.
"""

from __future__ import annotations

from enum import Enum


class ScalaFeature(Enum):
    """Semantic features of the Scala language."""

    # Declarations
    VAL_DECLARATION = "val x: T = expr immutable value declarations"
    VAR_DECLARATION = "var x: T = expr mutable variable declarations"
    VAR_ASSIGNMENT = "x = expr mutable variable assignment statements"
    LAZY_VAL = "lazy val x = expr lazily evaluated value declarations"
    FUNCTION_DECLARATION = "def f(...): T = expr function declarations"
    CLASS = "class declarations with primary constructors"
    OBJECT = "object Foo singleton object declarations"
    TRAIT = "trait declarations for interface and mixin types"
    CASE_CLASS = (
        "case class declarations with auto-generated equals and pattern matching"
    )
    TYPE_ALIAS = "type Foo = Bar type alias declarations"
    ENUM = "enum Foo { case A, B } enumeration declarations (Scala 3)"
    AUXILIARY_CONSTRUCTOR = "def this(...) auxiliary constructor declarations"
    DEFAULT_PARAMETERS = "function parameters with default argument values"

    # Expressions
    BINARY_OPERATION = "binary operator expressions"
    INFIX_EXPRESSION = "a method b infix method call expressions"
    BLOCK_EXPRESSION = "{ stmt; ...; expr } block expressions yielding a value"
    FIELD_ACCESS = "obj.field dot member access expressions"
    METHOD_CALL = "obj.method(...) instance method call expressions"
    FUNCTION_CALL = "f(...) function call expressions"
    STRING_LITERAL = "string literal values"
    CHARACTER_LITERAL = "'c' character literal values (lowered to integer ordinal)"
    BOOLEAN_LITERAL = "true and false boolean literal values"
    NULL_LITERAL = "null null value literal"
    STRING_INTERPOLATION = 's"...${expr}..." and f"..." string interpolation'
    GENERIC_FUNCTION = "f[T](...) explicitly typed generic function calls"
    POSTFIX_EXPRESSION = "expr method postfix method call expressions (deprecated)"
    NEW_EXPRESSION = "new T(...) object instantiation expressions"
    IMPLICIT_RETURN = "last expression in a block or method as the return value"
    LAMBDA_EXPRESSION = "(x: T) => expr and { case pat => expr } lambda expressions"

    # Control flow
    IF_EXPRESSION = "if (cond) expr else expr if expressions yielding a value"
    IF_ELSEIF_ELSE = "if / else if / else chained conditional branching"
    WHILE_LOOP = "while (cond) { } loop statements"
    DO_WHILE_LOOP = "do { } while (cond) loop statements"
    FOR_COMPREHENSION = (
        "for (x <- xs; if cond) yield expr for-comprehension expressions"
    )
    MATCH_EXPRESSION = "expr match { case pat => body } pattern match expressions"
    THROW_EXPRESSION = "throw new Exc(...) used as an expression"
    TRY_CATCH = "try { } catch { case e => } finally { } exception handling"
    BREAK = "break loop exit (via scala.util.control.Breaks)"
    CONTINUE = "continue loop skip (via scala.util.control.Breaks)"

    # Patterns and destructuring
    LITERAL_PATTERN = "literal value patterns in match expressions"
    WILDCARD_PATTERN = "_ wildcard patterns in match expressions"
    CAPTURE_PATTERN = "name capture patterns in match expressions"
    ALTERNATIVE_PATTERN = "P1 | P2 alternative patterns in match expressions"
    TUPLE_PATTERN = "(P1, P2) tuple deconstruction patterns"
    CASE_CLASS_PATTERN = "CaseClass(P1, P2) case class deconstruction patterns"
    TYPED_PATTERN = "x: T typed binding patterns"
    VALUE_PATTERN = "`stable` stable identifier patterns"
    TUPLE_DESTRUCTURING = "val (a, b) = tuple tuple value destructuring"
    INFIX_PATTERN = "P1 op P2 infix extractor patterns"

    # Generics and advanced features
    STABLE_TYPE_IDENTIFIER = "a.b.c stable identifier path types"
    PRIMARY_CONSTRUCTOR = (
        "class Foo(val x: T) primary constructor parameter declarations"
    )
    CONSTRUCTOR_DELEGATION = "this(...) constructor delegation calls"
    GUARD = "case pat if cond => guard conditions in match cases"

    # Infrastructure
    SOURCE_LOCATION = "source file and line number attached to IR instructions"
