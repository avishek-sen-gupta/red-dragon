from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Branch,
    CallCtorFunction,
    Const,
    DeclVar,
    Label_,
    NewObject,
    Return_,
    StoreField,
)
from interpreter.ir import CodeLabel
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.types.type_expr import scalar
from interpreter.var_name import VarName

_OUT = FieldName("out")

# Label names for the System class-declaration block (kept for ExportTable).
_CLS = "class_System_0"
_END_CLS = "end_class_System_1"

# Labels for the singleton-setup block that runs at module-init time.
_SETUP = "setup_System_2"
_SETUP_END = "end_setup_System_3"

SYSTEM_IR = (
    # ── record System class label (not actually executed at runtime) ──────────
    Label_(label=CodeLabel("entry_System")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    # ── build System singleton: allocate PrintStream, init it, store as .out ──
    # Allocate a PrintStream heap object and call its __init__.
    CallCtorFunction(
        result_reg=Register("%0"),
        func_name=FuncName("PrintStream"),
        type_hint=scalar("PrintStream"),
        args=(),
    ),
    # Allocate the System singleton heap object.
    NewObject(result_reg=Register("%1"), type_hint=scalar("System")),
    # Store the PrintStream instance as System.out.
    StoreField(obj_reg=Register("%1"), field_name=_OUT, value_reg=Register("%0")),
    # Expose the System singleton as the variable "System" in scope.
    DeclVar(name=VarName("System"), value_reg=Register("%1")),
)

SYSTEM_MODULE = ModuleUnit(
    path=Path("java/lang/System.java"),
    language=Language.JAVA,
    ir=SYSTEM_IR,
    exports=ExportTable(
        functions={},
        classes={
            ClassName("System"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
