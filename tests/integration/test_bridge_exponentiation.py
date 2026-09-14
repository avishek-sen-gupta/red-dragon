"""Bridge serializes COBOL ** (exponentiation) as a structured binop node.

Previously serializePowers() fell back to getText(), emitting the entire
sub-expression as a raw string literal.  That caused the interpreter to treat
the exponent as UNCOMPUTABLE and produce zero for the whole COMPUTE.
"""

from __future__ import annotations

import json

from cobol_asg.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401


def _fixed(lines: list[str]) -> str:
    return "\n".join("       " + line for line in lines) + "\n"


def _parse(src: list[str], bridge_jar: str) -> dict:
    raw = RealSubprocessRunner().run(["java", "-jar", bridge_jar], _fixed(src))
    return json.loads(raw)


def _find_compute(obj: dict) -> dict:
    """Return the first COMPUTE statement in the flattened statement list."""
    for stmt in obj.get("statements", []):
        if stmt.get("type") == "COMPUTE":
            return stmt
    raise AssertionError("no COMPUTE statement found")


def _find_power_binop(node: object) -> dict | None:
    """Depth-first search for a {"kind":"binop","op":"**"} node."""
    if not isinstance(node, dict):
        return None
    if node.get("kind") == "binop" and node.get("op") == "**":
        return node
    for v in node.values():
        hit = _find_power_binop(v)
        if hit:
            return hit
    return None


@covers(CobolFeature.COMPUTE)
def test_power_operator_serialized_as_binop_not_literal(bridge_jar):
    """COMPUTE WS-R = WS-B ** WS-E emits {"kind":"binop","op":"**",...}, not a string."""
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. POWTEST.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-B PIC 9(3)V9(4) VALUE 1.5.",
            "01 WS-E PIC 9(2)      VALUE 3.",
            "01 WS-R PIC 9(5)V9(4) VALUE ZEROES.",
            "PROCEDURE DIVISION.",
            "    COMPUTE WS-R = WS-B ** WS-E.",
            "    GOBACK.",
        ],
        bridge_jar,
    )
    compute = _find_compute(obj)
    expr = compute.get("expression", {})
    power_node = _find_power_binop(expr)
    assert (
        power_node is not None
    ), f"No ** binop found in expression; got: {json.dumps(expr, indent=2)}"
    assert power_node["kind"] == "binop"
    assert power_node["op"] == "**"
    # Both sides must be structured nodes, not raw strings
    assert isinstance(power_node.get("left"), dict), "left operand must be structured"
    assert isinstance(power_node.get("right"), dict), "right operand must be structured"


@covers(CobolFeature.COMPUTE)
def test_nested_power_in_denominator(bridge_jar):
    """COMPUTE WS-R = WS-A / (1 - (1 / (1 + WS-D) ** (WS-F * WS-N))) serializes ** correctly."""
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. PWRDENOM.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-A PIC 9(7)V9(8) VALUE 0.",
            "01 WS-D PIC 9(2)V9(8) VALUE 0.",
            "01 WS-F PIC 9(2)      VALUE 0.",
            "01 WS-N PIC 9(2)      VALUE 0.",
            "01 WS-R PIC 9(7)V9(8) VALUE 0.",
            "PROCEDURE DIVISION.",
            "    COMPUTE WS-R = WS-A /",
            "        (1 - (1 / (1 + WS-D) ** (WS-F * WS-N))).",
            "    GOBACK.",
        ],
        bridge_jar,
    )
    compute = _find_compute(obj)
    expr = compute.get("expression", {})
    power_node = _find_power_binop(expr)
    assert (
        power_node is not None
    ), f"No ** binop in denominator expression; got: {json.dumps(expr, indent=2)}"
    assert power_node["op"] == "**"
    assert isinstance(power_node["left"], dict)
    assert isinstance(power_node["right"], dict)
