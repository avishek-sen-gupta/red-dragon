from pathlib import Path

from interpreter.var_name import VarName

from experiments.java_stdlib.registry import STDLIB_REGISTRY
from experiments.java_stdlib.tests.conftest import locals_of, run_with_stdlib

_ALL = STDLIB_REGISTRY


class TestEndToEnd:
    def test_arraylist_produces_concrete_not_symbolic(self):
        """Core success criterion: stdlib call returns concrete value, not SYMBOLIC."""
        vm = run_with_stdlib(
            """
            ArrayList list = new ArrayList();
            list.add(10);
            list.add(20);
            int x = list.get(0);
            int y = list.get(1);
            int total = x + y;
            """,
            _ALL,
            max_steps=1000,
        )
        locs = locals_of(vm)
        assert locs[VarName("x")] == 10
        assert locs[VarName("y")] == 20
        assert locs[VarName("total")] == 30

    def test_math_result_flows_into_arithmetic(self):
        """Math.sqrt result is concrete and usable in subsequent operations."""
        vm = run_with_stdlib(
            "double root = Math.sqrt(16.0); double doubled = root + root;",
            _ALL,
        )
        locs = locals_of(vm)
        assert locs[VarName("root")] == 4.0
        assert locs[VarName("doubled")] == 8.0

    def test_hashmap_roundtrip(self):
        """HashMap put/get roundtrip produces concrete value."""
        vm = run_with_stdlib(
            """
            HashMap map = new HashMap();
            map.put("score", 42);
            int result = map.get("score");
            """,
            _ALL,
            max_steps=1000,
        )
        assert locals_of(vm)[VarName("result")] == 42

    def test_system_out_println(self, capsys):
        """System.out.println produces output, not SYMBOLIC."""
        run_with_stdlib('System.out.println("experiment works");', _ALL)
        assert "experiment works" in capsys.readouterr().out
