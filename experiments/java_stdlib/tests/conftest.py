from pathlib import Path

from interpreter.constants import Language
from interpreter.frontends import get_deterministic_frontend
from interpreter.func_name import FuncName
from interpreter.instructions import Const, DeclVar
from interpreter.ir import CodeLabel
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
    frontend = get_deterministic_frontend(Language.JAVA)
    user_ir = list(frontend.lower(java_source.encode()))

    # Locate the func_main_* label by scanning for DeclVar("main") and its preceding Const.
    main_label: CodeLabel | None = None
    for i, instr in enumerate(user_ir):
        if isinstance(instr, DeclVar) and instr.name == VarName("main"):
            prev = user_ir[i - 1]
            if isinstance(prev, Const):
                main_label = CodeLabel(prev.value)
                break

    if main_label is None:
        raise ValueError("No main() function found in compiled IR")

    user_path = Path("Main.java")
    user_module = ModuleUnit(
        path=user_path,
        language=Language.JAVA,
        ir=tuple(user_ir),
        exports=ExportTable(functions={FuncName("main"): main_label}),
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
        entry_point=EntryPoint.function(lambda ref: ref.name == FuncName("main")),
        max_steps=max_steps,
    )


def locals_of(vm: VMState) -> dict:
    return unwrap_locals(vm.call_stack[0].local_vars)
