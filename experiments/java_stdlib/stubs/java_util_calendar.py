"""java.util.Calendar stub — static integer constants only.

Calendar is abstract in Java; this stub exposes the field-selector constants
used by GregorianCalendar.set(field, value):

    Calendar.YEAR          = 1
    Calendar.MONTH         = 2
    Calendar.DAY_OF_MONTH  = 5

Values match the real java.util.Calendar constant definitions.

The stub allocates a heap object for the Calendar class so that
``Calendar.YEAR`` (lowered as LoadVar + LoadField) works at runtime.
"""

from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.instructions import (
    Branch,
    Const,
    DeclVar,
    Label_,
    NewObject,
    StoreField,
)
from interpreter.ir import CodeLabel
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.var_name import VarName

_CLS = "class_Calendar_0"
_END_CLS = "end_class_Calendar_1"

CALENDAR_IR = (
    # ── declare Calendar class ───────────────────────────────────────────
    Label_(label=CodeLabel("entry_Calendar")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    # Allocate a heap object to hold static constants (Calendar.YEAR etc.)
    NewObject(result_reg=Register("%0"), type_hint="Calendar"),
    # Store constants as fields on the heap object
    Const(result_reg=Register("%1"), value=1),
    StoreField(
        obj_reg=Register("%0"), field_name=FieldName("YEAR"), value_reg=Register("%1")
    ),
    Const(result_reg=Register("%2"), value=2),
    StoreField(
        obj_reg=Register("%0"), field_name=FieldName("MONTH"), value_reg=Register("%2")
    ),
    Const(result_reg=Register("%3"), value=5),
    StoreField(
        obj_reg=Register("%0"),
        field_name=FieldName("DAY_OF_MONTH"),
        value_reg=Register("%3"),
    ),
    # Bind the heap object to the variable "Calendar"
    DeclVar(name=VarName("Calendar"), value_reg=Register("%0")),
)

CALENDAR_MODULE = ModuleUnit(
    path=Path("java/util/Calendar.java"),
    language=Language.JAVA,
    ir=CALENDAR_IR,
    exports=ExportTable(
        functions={},
        classes={
            ClassName("Calendar"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
