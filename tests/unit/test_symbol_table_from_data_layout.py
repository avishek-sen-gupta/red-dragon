"""Tests for SymbolTable.from_data_layout — COBOL DataLayout bridge."""

from __future__ import annotations

from interpreter.class_name import ClassName
from interpreter.field_name import FieldName
from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.data_layout import DataLayout, FieldLayout
from interpreter.frontends.symbol_table import SymbolTable


class TestFromDataLayout:
    def test_converts_field_layout_to_field_info(self):
        layout = DataLayout(
            fields={
                "WS-AMOUNT": FieldLayout(
                    name="WS-AMOUNT",
                    type_descriptor=CobolTypeDescriptor(
                        category=CobolDataCategory.ZONED_DECIMAL,
                        total_digits=7,
                    ),
                    offset=0,
                    byte_length=7,
                ),
            },
            total_bytes=7,
        )
        st = SymbolTable.from_data_layout(layout)
        assert ClassName("__WORKING_STORAGE__") in st.classes
        assert (
            FieldName("WS-AMOUNT")
            in st.classes[ClassName("__WORKING_STORAGE__")].fields
        )

    def test_field_type_hint_is_empty_for_cobol_type_descriptor(self):
        """CobolTypeDescriptor has no .pic attribute; type_hint falls back to ''."""
        layout = DataLayout(
            fields={
                "WS-AMOUNT": FieldLayout(
                    name="WS-AMOUNT",
                    type_descriptor=CobolTypeDescriptor(
                        category=CobolDataCategory.ZONED_DECIMAL,
                        total_digits=7,
                    ),
                    offset=0,
                    byte_length=7,
                ),
            },
            total_bytes=7,
        )
        st = SymbolTable.from_data_layout(layout)
        field = st.classes[ClassName("__WORKING_STORAGE__")].fields[
            FieldName("WS-AMOUNT")
        ]
        assert field.type_hint == ""

    def test_field_with_value_has_initializer_true(self):
        layout = DataLayout(
            fields={
                "WS-FLAG": FieldLayout(
                    name="WS-FLAG",
                    type_descriptor=CobolTypeDescriptor(
                        category=CobolDataCategory.ALPHANUMERIC,
                        total_digits=1,
                    ),
                    offset=0,
                    byte_length=1,
                    value="Y",
                ),
            },
            total_bytes=1,
        )
        st = SymbolTable.from_data_layout(layout)
        field = st.classes[ClassName("__WORKING_STORAGE__")].fields[
            FieldName("WS-FLAG")
        ]
        assert field.has_initializer is True

    def test_field_without_value_has_initializer_false(self):
        layout = DataLayout(
            fields={
                "WS-COUNT": FieldLayout(
                    name="WS-COUNT",
                    type_descriptor=CobolTypeDescriptor(
                        category=CobolDataCategory.BINARY,
                        total_digits=4,
                    ),
                    offset=0,
                    byte_length=2,
                ),
            },
            total_bytes=2,
        )
        st = SymbolTable.from_data_layout(layout)
        field = st.classes[ClassName("__WORKING_STORAGE__")].fields[
            FieldName("WS-COUNT")
        ]
        assert field.has_initializer is False

    def test_multiple_fields_all_converted(self):
        layout = DataLayout(
            fields={
                "WS-NAME": FieldLayout(
                    name="WS-NAME",
                    type_descriptor=CobolTypeDescriptor(
                        category=CobolDataCategory.ALPHANUMERIC,
                        total_digits=20,
                    ),
                    offset=0,
                    byte_length=20,
                ),
                "WS-AGE": FieldLayout(
                    name="WS-AGE",
                    type_descriptor=CobolTypeDescriptor(
                        category=CobolDataCategory.BINARY,
                        total_digits=3,
                    ),
                    offset=20,
                    byte_length=2,
                ),
            },
            total_bytes=22,
        )
        st = SymbolTable.from_data_layout(layout)
        ws = st.classes[ClassName("__WORKING_STORAGE__")]
        assert FieldName("WS-NAME") in ws.fields
        assert FieldName("WS-AGE") in ws.fields
        assert len(ws.fields) == 2

    def test_working_storage_class_has_no_methods_or_parents(self):
        layout = DataLayout(
            fields={
                "WS-X": FieldLayout(
                    name="WS-X",
                    type_descriptor=CobolTypeDescriptor(
                        category=CobolDataCategory.ZONED_DECIMAL,
                        total_digits=2,
                    ),
                    offset=0,
                    byte_length=2,
                ),
            },
            total_bytes=2,
        )
        st = SymbolTable.from_data_layout(layout)
        ws = st.classes[ClassName("__WORKING_STORAGE__")]
        assert ws.methods == {}
        assert ws.parents == ()
        assert ws.constants == {}

    def test_empty_layout_produces_empty_fields(self):
        layout = DataLayout(fields={}, total_bytes=0)
        st = SymbolTable.from_data_layout(layout)
        assert ClassName("__WORKING_STORAGE__") in st.classes
        assert st.classes[ClassName("__WORKING_STORAGE__")].fields == {}
