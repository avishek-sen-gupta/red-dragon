# pyright: standard
"""Enforcement tests for the Java benign-types registry.

For every entry in JAVA_BENIGN_TYPES, asserts that:
  1. Each referenced test module is importable.
  2. Each referenced test class exists inside that module.

This makes the link between known_benign_types and test coverage a hard
build-time constraint: deleting a test class or misspelling a module path
will fail these tests immediately.
"""

from __future__ import annotations

import importlib

import pytest

from interpreter.frontends.java.benign_types import JAVA_BENIGN_TYPES, BenignType


def _all_refs() -> list[tuple[BenignType, str, str]]:
    """Flatten registry into (benign_type, module_path, class_name) triples."""
    return [(bt, mod, cls) for bt in JAVA_BENIGN_TYPES for mod, cls in bt.test_refs]


@pytest.mark.parametrize(
    "benign_type,module_path,class_name",
    [
        pytest.param(bt, mod, cls, id=f"{bt.node_type}→{cls}")
        for bt, mod, cls in _all_refs()
    ],
)
def test_benign_type_test_class_exists(
    benign_type: BenignType, module_path: str, class_name: str
) -> None:
    """Each test_ref in the registry must resolve to a real test class."""
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"benign node '{benign_type.node_type}': "
            f"test module '{module_path}' not found — {exc}"
        )

    assert hasattr(module, class_name), (
        f"benign node '{benign_type.node_type}': "
        f"test class '{class_name}' not found in '{module_path}'"
    )
