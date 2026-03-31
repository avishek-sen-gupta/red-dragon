from pathlib import Path

from interpreter.constants import Language
from interpreter.frontends import get_deterministic_frontend
from interpreter.func_name import FuncName
from interpreter.project.compiler import compile_module
from interpreter.project.entry_point import EntryPoint
from interpreter.project.linker import link_modules
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.run import run_linked
from interpreter.types.typed_value import unwrap_locals
from interpreter.var_name import VarName
from interpreter.vm.vm_types import VMState


def run_with_stdlib(
    java_source: str,
    stdlib_modules: dict[Path, ModuleUnit],
    max_steps: int = 500,
) -> VMState:
    """Compile java_source, link with stdlib_modules, execute, return VMState."""
    frontend = get_deterministic_frontend(Language.JAVA)
    user_ir = frontend.lower(java_source.encode())
    user_path = Path("Main.java")
    user_module = ModuleUnit(
        path=user_path,
        language=Language.JAVA,
        ir=tuple(user_ir),
        exports=ExportTable(),
        imports=(),
    )
    all_modules = {**stdlib_modules, user_path: user_module}
    linked = link_modules(
        modules=all_modules,
        import_graph={p: [] for p in all_modules},
        project_root=Path("."),
        topo_order=list(stdlib_modules.keys()) + [user_path],
        language=Language.JAVA,
    )
    return run_linked(
        linked,
        entry_point=EntryPoint.top_level(),
        max_steps=max_steps,
    )


def run_class_with_stdlib(
    java_source: str,
    stdlib_modules: dict[Path, ModuleUnit],
    max_steps: int = 500,
) -> VMState:
    """Compile a full Java class, link with stdlib_modules, execute main(), return VMState.

    Unlike run_with_stdlib (which accepts bare statements and runs from top-level entry),
    this helper accepts a complete Java program with a class and main() method,
    and enters execution at main() — the realistic call path for real-world programs.
    """
    user_path = Path("Main.java")
    user_module = compile_module(user_path, Language.JAVA, source=java_source.encode())
    all_modules = {**stdlib_modules, user_path: user_module}
    linked = link_modules(
        modules=all_modules,
        import_graph={p: [] for p in all_modules},
        project_root=Path("."),
        topo_order=list(stdlib_modules.keys()) + [user_path],
        language=Language.JAVA,
    )
    return run_linked(
        linked,
        entry_point=EntryPoint.function(lambda ref: ref.name == FuncName("main")),
        max_steps=max_steps,
    )


def locals_of(vm: VMState) -> dict:
    return unwrap_locals(vm.call_stack[0].local_vars)
