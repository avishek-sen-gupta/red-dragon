# pyright: standard
"""Unified symbol table for all frontends.

Generalizes COBOL's DataLayout pattern: extract symbols from the AST
before IR lowering begins, so the lowering pass has full knowledge of
all classes, fields, functions, and constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from interpreter.class_name import ClassName
from interpreter.field_name import FieldName, NO_FIELD_NAME
from interpreter.func_name import FuncName


@dataclass(frozen=True)
class FieldInfo:
    """A class/struct/record field."""

    name: FieldName
    type_hint: str
    has_initializer: bool
    children: tuple[FieldInfo, ...] = ()


NULL_FIELD = FieldInfo(name=NO_FIELD_NAME, type_hint="", has_initializer=False)


@dataclass(frozen=True)
class FunctionInfo:
    """A function/method signature."""

    name: FuncName
    params: tuple[str, ...]
    return_type: str


@dataclass(frozen=True)
class ClassInfo:
    """A class/struct/record with its fields, methods, constants, and parents."""

    name: ClassName
    fields: dict[FieldName, FieldInfo]
    methods: dict[FuncName, FunctionInfo]
    constants: dict[str, str]
    parents: tuple[ClassName, ...]
    match_args: tuple[str, ...] = ()


@dataclass
class SymbolTable:
    """Symbol catalog extracted before IR lowering."""

    classes: dict[ClassName, ClassInfo] = field(default_factory=dict)
    functions: dict[FuncName, FunctionInfo] = field(default_factory=dict)
    constants: dict[str, str] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> SymbolTable:
        return cls()

    def resolve_field(self, class_name: ClassName, field_name: FieldName) -> FieldInfo:
        """Find field in class or any ancestor. Returns NULL_FIELD if not found."""
        class_info = self.classes.get(class_name)
        if class_info is None:
            return NULL_FIELD
        if field_name in class_info.fields:
            return class_info.fields[field_name]
        return next(
            (
                result
                for parent in class_info.parents
                for result in [self.resolve_field(parent, field_name)]
                if result.name.is_present()
            ),
            NULL_FIELD,
        )

    @classmethod
    def from_data_layout(cls, layout) -> SymbolTable:
        """Convert COBOL DataLayout to a SymbolTable."""
        fields = {
            FieldName(name): FieldInfo(
                name=FieldName(name),
                type_hint=(
                    fl.type_descriptor.pic if hasattr(fl.type_descriptor, "pic") else ""
                ),
                has_initializer=bool(fl.value),
            )
            for name, fl in layout.fields.items()
        }
        ws_class = ClassInfo(
            name=ClassName("__WORKING_STORAGE__"),
            fields=fields,
            methods={},
            constants={},
            parents=(),
        )
        return cls(classes={ClassName("__WORKING_STORAGE__"): ws_class})
