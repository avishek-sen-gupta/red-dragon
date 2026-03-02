"""Tests for COBOL arithmetic expression tokenizer and parser."""

from interpreter.cobol.cobol_expression import (
    BinOpNode,
    FieldRefNode,
    LiteralNode,
    parse_expression,
    tokenize_expression,
)


class TestTokenizer:
    def test_simple_addition(self):
        assert tokenize_expression("WS-A + WS-B") == ["WS-A", "+", "WS-B"]

    def test_mixed_operators(self):
        assert tokenize_expression("WS-A + WS-B * 2") == [
            "WS-A",
            "+",
            "WS-B",
            "*",
            "2",
        ]

    def test_parenthesized_expression(self):
        assert tokenize_expression("(WS-A + WS-B) * 3") == [
            "(",
            "WS-A",
            "+",
            "WS-B",
            ")",
            "*",
            "3",
        ]

    def test_division(self):
        assert tokenize_expression("WS-A / WS-B") == ["WS-A", "/", "WS-B"]

    def test_literal_only(self):
        assert tokenize_expression("100") == ["100"]

    def test_subtraction(self):
        assert tokenize_expression("100 - WS-A") == ["100", "-", "WS-A"]

    def test_decimal_literal(self):
        assert tokenize_expression("WS-A * 1.5") == ["WS-A", "*", "1.5"]

    def test_nested_parens(self):
        assert tokenize_expression("((WS-A + 1) * (WS-B - 2))") == [
            "(",
            "(",
            "WS-A",
            "+",
            "1",
            ")",
            "*",
            "(",
            "WS-B",
            "-",
            "2",
            ")",
            ")",
        ]


class TestParserAtoms:
    def test_literal_integer(self):
        tree = parse_expression("42")
        assert isinstance(tree, LiteralNode)
        assert tree.value == "42"

    def test_literal_decimal(self):
        tree = parse_expression("3.14")
        assert isinstance(tree, LiteralNode)
        assert tree.value == "3.14"

    def test_field_reference(self):
        tree = parse_expression("WS-AMOUNT")
        assert isinstance(tree, FieldRefNode)
        assert tree.name == "WS-AMOUNT"


class TestParserPrecedence:
    def test_addition(self):
        tree = parse_expression("WS-A + WS-B")
        assert isinstance(tree, BinOpNode)
        assert tree.op == "+"
        assert isinstance(tree.left, FieldRefNode)
        assert isinstance(tree.right, FieldRefNode)
        assert tree.left.name == "WS-A"
        assert tree.right.name == "WS-B"

    def test_multiplication_before_addition(self):
        # WS-A + WS-B * 2  →  WS-A + (WS-B * 2)
        tree = parse_expression("WS-A + WS-B * 2")
        assert isinstance(tree, BinOpNode)
        assert tree.op == "+"
        assert isinstance(tree.left, FieldRefNode)
        assert tree.left.name == "WS-A"
        assert isinstance(tree.right, BinOpNode)
        assert tree.right.op == "*"

    def test_parentheses_override_precedence(self):
        # (WS-A + WS-B) * 3  →  (WS-A + WS-B) * 3
        tree = parse_expression("(WS-A + WS-B) * 3")
        assert isinstance(tree, BinOpNode)
        assert tree.op == "*"
        assert isinstance(tree.left, BinOpNode)
        assert tree.left.op == "+"
        assert isinstance(tree.right, LiteralNode)
        assert tree.right.value == "3"

    def test_left_associativity(self):
        # WS-A - WS-B - WS-C  →  (WS-A - WS-B) - WS-C
        tree = parse_expression("WS-A - WS-B - WS-C")
        assert isinstance(tree, BinOpNode)
        assert tree.op == "-"
        assert isinstance(tree.left, BinOpNode)
        assert tree.left.op == "-"
        assert isinstance(tree.right, FieldRefNode)
        assert tree.right.name == "WS-C"

    def test_division_same_precedence_as_multiplication(self):
        # WS-A * WS-B / WS-C  →  (WS-A * WS-B) / WS-C
        tree = parse_expression("WS-A * WS-B / WS-C")
        assert isinstance(tree, BinOpNode)
        assert tree.op == "/"
        assert isinstance(tree.left, BinOpNode)
        assert tree.left.op == "*"

    def test_complex_expression(self):
        # (WS-A + WS-B) * 100 / WS-C - 5
        tree = parse_expression("(WS-A + WS-B) * 100 / WS-C - 5")
        # Should be: (((WS-A + WS-B) * 100 / WS-C) - 5)
        assert isinstance(tree, BinOpNode)
        assert tree.op == "-"
        assert isinstance(tree.right, LiteralNode)
        assert tree.right.value == "5"

    def test_subtraction_with_literal(self):
        tree = parse_expression("100 - WS-A")
        assert isinstance(tree, BinOpNode)
        assert tree.op == "-"
        assert isinstance(tree.left, LiteralNode)
        assert isinstance(tree.right, FieldRefNode)
