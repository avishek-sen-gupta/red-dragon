"""Ruby language features for @covers decorator annotation."""

from __future__ import annotations

from enum import Enum


class RubyFeature(Enum):
    """Ruby language features covered by tests."""

    # Literals and basic expressions
    INTEGER_LITERAL = "integer literal values"
    STRING_LITERAL = "single and double quoted string literals"
    SYMBOL = ':name and :"name" symbol literals'
    REGEX = "/pattern/flags regular expression literals"
    ARRAY_LITERAL = "[a, b, c] array literal expressions"
    HASH_LITERAL = "{ key => value } and { key: value } hash literals"
    RANGE = "a..b and a...b range literals"
    LAMBDA = "lambda { |x| } and ->(x) { } lambda literals"
    STRING_ARRAY = "%w[...] word and %i[...] symbol array literals"
    HEREDOC = "<<~HEREDOC ... HEREDOC heredoc string literals"
    HEREDOC_INTERPOLATION = "#{expr} interpolation inside heredoc strings"

    # Variables
    VARIABLE_ASSIGNMENT = "x = expr local variable assignment"
    INSTANCE_VARIABLE = "@x instance variable access and assignment"
    GLOBAL_VARIABLE = "$x global variable access and assignment"
    CLASS_VARIABLE = "@@x class variable access and assignment"
    AUGMENTED_ASSIGNMENT = "+=, -=, *=, etc. augmented assignment operators"

    # Control flow
    IF_ELSIF_ELSE = "if / elsif / else conditional branching"
    UNLESS = "unless cond negated conditional statements"
    WHILE_LOOP = "while cond do ... end loop statements"
    UNTIL_LOOP = "until cond do ... end loop statements"
    IF_MODIFIER = "expr if cond trailing if modifier"
    UNLESS_MODIFIER = "expr unless cond trailing unless modifier"
    WHILE_MODIFIER = "expr while cond trailing while modifier"
    UNTIL_MODIFIER = "expr until cond trailing until modifier"
    CONDITIONAL_TERNARY = "cond ? a : b ternary expressions"
    CASE_WHEN = "case expr when pattern ... end case/when branching"
    BREAK_STATEMENT = "break and break value loop exit statements"
    NEXT_STATEMENT = "next and next value loop continue statements"

    # Methods and functions
    METHOD_DEFINITION = "def method_name(...) ... end method definitions"
    METHOD_CALL = "obj.method(...) and method(...) method call expressions"
    METHOD_CHAINING = "obj.method1.method2 chained method call expressions"
    RETURN_STATEMENT = "return and return expr explicit return statements"
    IMPLICIT_RETURN = "last-expression-as-return implicit return values"
    YIELD = "yield and yield value block invocation inside methods"
    SUPER = "super and super(...) parent method invocation"

    # Classes and modules
    CLASS_DEFINITION = "class Foo ... end class definitions"
    CLASS_CONSTRUCTOR = "def initialize(...) constructor definitions"
    MODULE_DEFINITION = "module Foo ... end module definitions"
    SINGLETON_CLASS = "class << self ... end singleton class bodies"
    SINGLETON_METHOD = "def obj.method singleton method definitions"

    # Expressions
    ARITHMETIC = "+, -, *, /, %, ** arithmetic expressions"
    UNARY_OPERATOR = "unary -, !, ~, + operator expressions"
    SELF_KEYWORD = "self current object reference"
    SCOPE_RESOLUTION = "Module::Constant scope resolution operator"

    # Block and closure
    BLOCK_DO_END = "method do |x| ... end block expressions"
    BLOCK_CURLY = "method { |x| ... } block expressions"
    BLOCK_WITH_PARAMS = "block parameter lists in do/end and { } blocks"

    # Exception handling
    RESCUE_MODIFIER = "expr rescue fallback inline rescue modifier"
    RESCUE_CLAUSE = "rescue ExcType => e ... rescue clauses in begin/def"
    ENSURE_CLAUSE = "ensure ... end cleanup clauses"
    RAISE = "raise and raise ExcType.new(...) exception raising"
    RETRY = "retry retry the enclosing begin block from rescue"

    # String interpolation
    STRING_INTERPOLATION = '"...#{expr}..." double-quoted string interpolation'

    # Patterns (Ruby 3+)
    PATTERN_MATCHING = "case/in and expr in pattern pattern matching (Ruby 3+)"
    LITERAL_PATTERN = "literal value pattern matching clauses"
    WILDCARD_PATTERN = "_ wildcard pattern matching clauses"
    CAPTURE_PATTERN = "variable capture in pattern matching"
    OR_PATTERN = "pat1 | pat2 disjunctive pattern matching"
    ARRAY_PATTERN = "[P1, P2] array deconstruction patterns"
    HASH_PATTERN = "{ key: value } hash deconstruction patterns"
    CLASS_PATTERN = "ClassName[pat] and ClassName[key: pat] class patterns"
    AS_PATTERN = "pattern => variable as-binding patterns"

    # For loops
    FOR_IN_LOOP = "for x in collection ... end for-in loop statements"

    # Advanced features
    RANGE_SLICE = "collection[a..b] range-based slicing expressions"
    HASH_WITH_SYMBOL_KEYS = "{ key: value } hash with symbol-key shorthand"
    DELIMITED_SYMBOL = "%s[...] delimited symbol literals"
    BEGIN_END_BLOCK = "begin ... rescue ... ensure ... end structured blocks"
    SPLAT_ARGUMENT = "*args splat argument unpacking in calls"
    HASH_SPLAT_ARGUMENT = "**kwargs double-splat hash unpacking in calls"
    BLOCK_ARGUMENT = "&block block-to-proc argument passing"

    # Execution tests
    CLASS_EXECUTION = "end-to-end class instantiation and method execution"
    LOGICAL_OPERATOR = "&& and || and and and or logical operators"
