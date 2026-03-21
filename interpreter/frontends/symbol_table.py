"""Unified symbol table for all frontends.

Generalizes COBOL's DataLayout pattern: extract symbols from the AST
before IR lowering begins, so the lowering pass has full knowledge of
all classes, fields, functions, and constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldInfo:
    """A class/struct/record field."""

    name: str
    type_hint: str
    has_initializer: bool
    children: tuple[FieldInfo, ...] = ()


@dataclass(frozen=True)
class FunctionInfo:
    """A function/method signature."""

    name: str
    params: tuple[str, ...]
    return_type: str


@dataclass(frozen=True)
class ClassInfo:
    """A class/struct/record with its fields, methods, constants, and parents."""

    name: str
    fields: dict[str, FieldInfo]
    methods: dict[str, FunctionInfo]
    constants: dict[str, str]
    parents: tuple[str, ...]
    match_args: tuple[str, ...] = ()


@dataclass
class SymbolTable:
    """Symbol catalog extracted before IR lowering."""

    classes: dict[str, ClassInfo] = field(default_factory=dict)
    functions: dict[str, FunctionInfo] = field(default_factory=dict)
    constants: dict[str, str] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> SymbolTable:
        return cls()

    def resolve_field(self, class_name: str, field_name: str) -> FieldInfo | None:
        """Find field in class or any ancestor via parents chain."""
        class_info = self.classes.get(class_name)
        if class_info is None:
            return None
        if field_name in class_info.fields:
            return class_info.fields[field_name]
        return next(
            (
                result
                for parent in class_info.parents
                for result in [self.resolve_field(parent, field_name)]
                if result is not None
            ),
            None,
        )

    @classmethod
    def from_data_layout(cls, layout) -> SymbolTable:
        """Convert COBOL DataLayout to a SymbolTable."""
        fields = {
            name: FieldInfo(
                name=name,
                type_hint=(
                    fl.type_descriptor.pic if hasattr(fl.type_descriptor, "pic") else ""
                ),
                has_initializer=bool(fl.value),
            )
            for name, fl in layout.fields.items()
        }
        ws_class = ClassInfo(
            name="__WORKING_STORAGE__",
            fields=fields,
            methods={},
            constants={},
            parents=(),
        )
        return cls(classes={"__WORKING_STORAGE__": ws_class})
