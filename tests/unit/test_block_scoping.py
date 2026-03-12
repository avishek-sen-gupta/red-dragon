"""Unit tests for block-level variable scoping in frontends.

Tests the LLVM-style scope tracking: frontends disambiguate variable names
at emission time, storing original name + scope metadata separately.
"""

from interpreter.constants import Language
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.frontends.context import GrammarConstants, TreeSitterEmitContext
from interpreter.var_scope_info import VarScopeInfo


def _make_ctx() -> TreeSitterEmitContext:
    return TreeSitterEmitContext(
        source=b"",
        language=Language.JAVA,
        observer=NullFrontendObserver(),
        constants=GrammarConstants(),
    )


# ---------------------------------------------------------------------------
# VarScopeInfo dataclass
# ---------------------------------------------------------------------------


class TestVarScopeInfo:
    def test_creation(self):
        info = VarScopeInfo(original_name="x", scope_depth=2)
        assert info.original_name == "x"
        assert info.scope_depth == 2

    def test_frozen(self):
        info = VarScopeInfo(original_name="x", scope_depth=1)
        try:
            info.original_name = "y"
            assert False, "Should have raised"
        except AttributeError:
            pass

    def test_equality(self):
        a = VarScopeInfo(original_name="x", scope_depth=1)
        b = VarScopeInfo(original_name="x", scope_depth=1)
        assert a == b

    def test_inequality_depth(self):
        a = VarScopeInfo(original_name="x", scope_depth=1)
        b = VarScopeInfo(original_name="x", scope_depth=2)
        assert a != b


# ---------------------------------------------------------------------------
# Scope tracker — no shadowing (names pass through unchanged)
# ---------------------------------------------------------------------------


class TestScopeTrackerNoShadowing:
    def test_declare_without_scope_returns_original(self):
        ctx = _make_ctx()
        assert ctx.declare_block_var("x") == "x"

    def test_resolve_without_scope_returns_original(self):
        ctx = _make_ctx()
        assert ctx.resolve_var("x") == "x"

    def test_declare_in_block_no_shadow_returns_original(self):
        ctx = _make_ctx()
        ctx.enter_block_scope()
        assert ctx.declare_block_var("x") == "x"
        ctx.exit_block_scope()

    def test_resolve_finds_outer_var(self):
        ctx = _make_ctx()
        ctx.declare_block_var("x")
        ctx.enter_block_scope()
        assert ctx.resolve_var("x") == "x"
        ctx.exit_block_scope()


# ---------------------------------------------------------------------------
# Scope tracker — shadowing (mangled names)
# ---------------------------------------------------------------------------


class TestScopeTrackerShadowing:
    def test_shadow_in_inner_block_returns_mangled(self):
        ctx = _make_ctx()
        ctx.declare_block_var("x")
        ctx.enter_block_scope()
        mangled = ctx.declare_block_var("x")
        assert mangled != "x"
        assert mangled.startswith("x$")

    def test_resolve_in_inner_block_returns_mangled(self):
        ctx = _make_ctx()
        ctx.declare_block_var("x")
        ctx.enter_block_scope()
        mangled = ctx.declare_block_var("x")
        assert ctx.resolve_var("x") == mangled

    def test_resolve_after_exit_returns_original(self):
        ctx = _make_ctx()
        ctx.declare_block_var("x")
        ctx.enter_block_scope()
        ctx.declare_block_var("x")
        ctx.exit_block_scope()
        assert ctx.resolve_var("x") == "x"

    def test_double_shadow_gets_distinct_names(self):
        ctx = _make_ctx()
        ctx.declare_block_var("x")
        ctx.enter_block_scope()
        m1 = ctx.declare_block_var("x")
        ctx.enter_block_scope()
        m2 = ctx.declare_block_var("x")
        assert m1 != m2
        assert m1 != "x"
        assert m2 != "x"

    def test_non_shadowed_var_unaffected(self):
        """Declaring y in inner scope when only x is in outer should not mangle y."""
        ctx = _make_ctx()
        ctx.declare_block_var("x")
        ctx.enter_block_scope()
        assert ctx.declare_block_var("y") == "y"
        ctx.exit_block_scope()

    def test_metadata_recorded_for_mangled_var(self):
        ctx = _make_ctx()
        ctx.declare_block_var("x")
        ctx.enter_block_scope()
        mangled = ctx.declare_block_var("x")
        metadata = ctx.var_scope_metadata
        assert mangled in metadata
        assert metadata[mangled].original_name == "x"
        assert metadata[mangled].scope_depth == 1

    def test_no_metadata_for_non_shadowed_var(self):
        ctx = _make_ctx()
        ctx.declare_block_var("x")
        assert "x" not in ctx.var_scope_metadata


# ---------------------------------------------------------------------------
# Scope tracker — nested scopes
# ---------------------------------------------------------------------------


class TestScopeTrackerNested:
    def test_three_level_nesting(self):
        ctx = _make_ctx()
        ctx.declare_block_var("x")  # level 0
        ctx.enter_block_scope()  # level 1
        m1 = ctx.declare_block_var("x")
        ctx.enter_block_scope()  # level 2
        m2 = ctx.declare_block_var("x")
        assert ctx.resolve_var("x") == m2
        ctx.exit_block_scope()
        assert ctx.resolve_var("x") == m1
        ctx.exit_block_scope()
        assert ctx.resolve_var("x") == "x"

    def test_sibling_scopes_can_reuse_names(self):
        """Two sibling blocks both shadow x — each gets a distinct mangled name."""
        ctx = _make_ctx()
        ctx.declare_block_var("x")
        ctx.enter_block_scope()
        m1 = ctx.declare_block_var("x")
        ctx.exit_block_scope()
        ctx.enter_block_scope()
        m2 = ctx.declare_block_var("x")
        ctx.exit_block_scope()
        assert m1 != m2
        assert m1 != "x"
        assert m2 != "x"

    def test_scope_reset_clears_all_block_scopes(self):
        """reset_block_scopes() clears all block scopes (used at function boundaries)."""
        ctx = _make_ctx()
        ctx.declare_block_var("x")
        ctx.enter_block_scope()
        ctx.declare_block_var("x")
        ctx.reset_block_scopes()
        # After reset, x is no longer tracked — fresh state
        assert ctx.resolve_var("x") == "x"


# ---------------------------------------------------------------------------
# flat_var_types union merge
# ---------------------------------------------------------------------------


class TestFlatVarTypesUnionMerge:
    def test_same_name_different_scopes_produces_union(self):
        """x: Int in func_f and x: String in func_g → flat x: Union[Int, String]."""
        from interpreter.type_inference import _InferenceContext
        from interpreter.type_expr import scalar, union_of

        ctx = _InferenceContext()
        ctx.scoped_var_types = {
            "func_f_0": {"x": scalar("Int")},
            "func_g_1": {"x": scalar("String")},
        }
        flat = ctx.flat_var_types()
        assert flat["x"] == union_of(scalar("Int"), scalar("String"))

    def test_same_type_same_name_no_union(self):
        """x: Int in both scopes → flat x: Int (no union)."""
        from interpreter.type_inference import _InferenceContext
        from interpreter.type_expr import scalar

        ctx = _InferenceContext()
        ctx.scoped_var_types = {
            "func_f_0": {"x": scalar("Int")},
            "func_g_1": {"x": scalar("Int")},
        }
        flat = ctx.flat_var_types()
        assert flat["x"] == scalar("Int")

    def test_disjoint_names_both_present(self):
        """x in func_f, y in func_g → flat has both."""
        from interpreter.type_inference import _InferenceContext
        from interpreter.type_expr import scalar

        ctx = _InferenceContext()
        ctx.scoped_var_types = {
            "func_f_0": {"x": scalar("Int")},
            "func_g_1": {"y": scalar("String")},
        }
        flat = ctx.flat_var_types()
        assert flat["x"] == scalar("Int")
        assert flat["y"] == scalar("String")


# ---------------------------------------------------------------------------
# TypeEnvironment exposes scoped_var_types
# ---------------------------------------------------------------------------


class TestTypeEnvironmentScopedVarTypes:
    def test_scoped_var_types_exposed(self):
        """TypeEnvironment should expose per-function scoped variable types."""
        from types import MappingProxyType

        from interpreter.type_environment import TypeEnvironment
        from interpreter.type_expr import scalar

        scoped = MappingProxyType(
            {
                "func_f_0": MappingProxyType({"x": scalar("Int")}),
                "func_g_1": MappingProxyType({"x": scalar("String")}),
            }
        )
        env = TypeEnvironment(
            register_types=MappingProxyType({}),
            var_types=MappingProxyType({}),
            scoped_var_types=scoped,
        )
        assert env.scoped_var_types["func_f_0"]["x"] == "Int"
        assert env.scoped_var_types["func_g_1"]["x"] == "String"

    def test_var_scope_metadata_exposed(self):
        """TypeEnvironment should expose mangled→original name metadata."""
        from types import MappingProxyType

        from interpreter.type_environment import TypeEnvironment

        metadata = MappingProxyType(
            {"x$1": VarScopeInfo(original_name="x", scope_depth=1)}
        )
        env = TypeEnvironment(
            register_types=MappingProxyType({}),
            var_types=MappingProxyType({}),
            var_scope_metadata=metadata,
        )
        assert env.var_scope_metadata["x$1"].original_name == "x"
