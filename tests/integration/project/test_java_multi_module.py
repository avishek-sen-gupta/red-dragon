"""End-to-end integration test for multi-module Java project linking.

4 modules, 7 Java files across Maven-convention source roots:
  math-lib  — Adder, Multiplier
  models    — Result, Pair
  utils     — Formatter
  app       — Calculator (imports math-lib + models), Main (imports app + models.*)

Exercises: cross-module constructor dispatch, wildcard + specific imports,
method dispatch, and linked IR completeness.
"""

from pathlib import Path

import pytest

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.project.compiler import compile_directory
from interpreter.project.types import LinkedProgram
from interpreter.run import execute_cfg, ExecutionStrategies
from interpreter.run_types import VMConfig
from interpreter.types.typed_value import TypedValue
from interpreter.var_name import VarName

# ── Java source files ───────────────────────────────────────────

_ADDER_JAVA = """\
package com.math;

public class Adder {
    int base;

    Adder(int b) {
        this.base = b;
    }

    int add(int x) {
        return this.base + x;
    }
}
"""

_MULTIPLIER_JAVA = """\
package com.math;

public class Multiplier {
    int factor;

    Multiplier(int f) {
        this.factor = f;
    }

    int multiply(int x) {
        return this.factor * x;
    }
}
"""

_RESULT_JAVA = """\
package com.models;

public class Result {
    String label;
    int value;

    Result(String l, int v) {
        this.label = l;
        this.value = v;
    }

    String getLabel() {
        return this.label;
    }

    int getValue() {
        return this.value;
    }
}
"""

_PAIR_JAVA = """\
package com.models;

public class Pair {
    int first;
    int second;

    Pair(int f, int s) {
        this.first = f;
        this.second = s;
    }

    int getFirst() {
        return this.first;
    }

    int getSecond() {
        return this.second;
    }
}
"""

_FORMATTER_JAVA = """\
package com.utils;

public class Formatter {
    String prefix;

    Formatter(String p) {
        this.prefix = p;
    }
}
"""

_CALCULATOR_JAVA = """\
package com.app;

import com.math.Adder;
import com.math.Multiplier;
import com.models.Result;

public class Calculator {
    Result compute(int a, int b) {
        Adder adder = new Adder(a);
        int sum = adder.add(b);
        Multiplier mul = new Multiplier(a);
        int product = mul.multiply(b);
        return new Result("result", sum + product);
    }
}
"""

_MAIN_JAVA = """\
import com.app.Calculator;
import com.models.*;

Calculator c = new Calculator();
Result r = c.compute(10, 3);
int val = r.getValue();
String label = r.getLabel();
"""


# ── Fixture ─────────────────────────────────────────────────────


@pytest.fixture
def java_project(tmp_path: Path) -> Path:
    """Write 4-module Maven-style Java project under tmp_path and return root."""
    files = {
        "math-lib/src/main/java/com/math/Adder.java": _ADDER_JAVA,
        "math-lib/src/main/java/com/math/Multiplier.java": _MULTIPLIER_JAVA,
        "models/src/main/java/com/models/Result.java": _RESULT_JAVA,
        "models/src/main/java/com/models/Pair.java": _PAIR_JAVA,
        "utils/src/main/java/com/utils/Formatter.java": _FORMATTER_JAVA,
        "app/src/main/java/com/app/Calculator.java": _CALCULATOR_JAVA,
        "app/src/main/java/com/app/Main.java": _MAIN_JAVA,
    }
    for rel_path, content in files.items():
        full = tmp_path / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
    return tmp_path


# ── Tests ───────────────────────────────────────────────────────


class TestJavaMultiModuleLinking:
    """Full end-to-end multi-module Java project tests."""

    def test_linked_ir_contains_all_modules(self, java_project: Path):
        """After compile_directory(), merged IR should contain classes from all modules."""
        linked = compile_directory(java_project, Language.JAVA)

        assert isinstance(linked, LinkedProgram)

        # Collect all labels that appear in the merged IR
        ir_labels = []
        for inst in linked.merged_ir:
            if hasattr(inst, "label") and inst.label is not None:
                ir_labels.append(str(inst.label))

        ir_text = " ".join(ir_labels)

        # Classes from math-lib
        assert any(
            "Adder" in label for label in ir_labels
        ), f"Adder not found in IR labels: {ir_labels[:20]}"
        assert any(
            "Multiplier" in label for label in ir_labels
        ), f"Multiplier not found in IR labels: {ir_labels[:20]}"

        # Class from models (imported specifically by Calculator)
        assert any(
            "Result" in label for label in ir_labels
        ), f"Result not found in IR labels: {ir_labels[:20]}"

        # Class from app
        assert any(
            "Calculator" in label for label in ir_labels
        ), f"Calculator not found in IR labels: {ir_labels[:20]}"

    def test_cross_module_constructor_and_method_dispatch(self, java_project: Path):
        """Execute the linked program and verify cross-module dispatch."""
        linked = compile_directory(java_project, Language.JAVA)

        strategies = ExecutionStrategies(
            func_symbol_table=linked.func_symbol_table,
            class_symbol_table=linked.class_symbol_table,
        )
        config = VMConfig(max_steps=500)
        vm, stats = execute_cfg(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            config,
            strategies,
        )

        frame = vm.call_stack[0]
        local_vars = {
            k: v.value if isinstance(v, TypedValue) else v
            for k, v in frame.local_vars.items()
        }

        # Calculator instance created
        assert (
            VarName("c") in local_vars
        ), f"Variable 'c' (Calculator instance) not in scope: {list(local_vars.keys())}"

        # Result instance from cross-module dispatch chain:
        # Calculator.compute(10, 3) → Adder(10).add(3)=13, Multiplier(10).multiply(3)=30
        # → Result("result", 13+30)
        assert (
            VarName("r") in local_vars
        ), f"Variable 'r' (Result instance) not in scope: {list(local_vars.keys())}"

        # Concrete value: Adder(10).add(3) + Multiplier(10).multiply(3) = 13 + 30 = 43
        assert local_vars[VarName("val")] == 43

        # Concrete value: the label passed to the Result constructor
        assert local_vars[VarName("label")] == "result"
