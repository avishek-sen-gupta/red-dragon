from pathlib import Path

from interpreter.var_name import VarName

from experiments.java_stdlib.registry import STDLIB_REGISTRY
from experiments.java_stdlib.tests.conftest import (
    locals_of,
    run_class_with_stdlib,
    run_with_stdlib,
)

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


class TestFullClassEndToEnd:
    """Same scenarios as TestEndToEnd but using full Java class + main() structure.

    These tests verify that stdlib dispatch works when called from inside a class
    method body — the realistic call path for real-world Java programs.
    """

    def test_arraylist_in_main_method(self):
        """ArrayList.add/get called from inside a class main() method."""
        vm = run_class_with_stdlib(
            """
            import java.util.ArrayList;
            class Main {
                public static void main() {
                    ArrayList list = new ArrayList();
                    list.add(10);
                    list.add(20);
                    int x = list.get(0);
                    int y = list.get(1);
                    int total = x + y;
                }
            }
            """,
            _ALL,
            max_steps=1000,
        )
        locs = locals_of(vm)
        assert locs[VarName("x")] == 10
        assert locs[VarName("y")] == 20
        assert locs[VarName("total")] == 30

    def test_math_in_main_method(self):
        """Math.sqrt called from inside a class main() method."""
        vm = run_class_with_stdlib(
            """
            class Main {
                public static void main() {
                    double root = Math.sqrt(16.0);
                    double doubled = root + root;
                }
            }
            """,
            _ALL,
        )
        locs = locals_of(vm)
        assert locs[VarName("root")] == 4.0
        assert locs[VarName("doubled")] == 8.0

    def test_hashmap_in_main_method(self):
        """HashMap.put/get called from inside a class main() method."""
        vm = run_class_with_stdlib(
            """
            import java.util.HashMap;
            class Main {
                public static void main() {
                    HashMap map = new HashMap();
                    map.put("score", 42);
                    int result = map.get("score");
                }
            }
            """,
            _ALL,
            max_steps=1000,
        )
        assert locals_of(vm)[VarName("result")] == 42

    def test_system_out_println_in_main_method(self, capsys):
        """System.out.println called from inside a class main() method."""
        run_class_with_stdlib(
            """
            class Main {
                public static void main() {
                    System.out.println("hello from main");
                }
            }
            """,
            _ALL,
        )
        assert "hello from main" in capsys.readouterr().out
