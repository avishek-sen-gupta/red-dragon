"""A LinkedProgram to and from its .linked.json file; the CFG and registry are rebuilt on read."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path

from interpreter.cfg import build_cfg
from interpreter.constants import Language
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.ir import CodeLabel
from interpreter.project.ir_codec import IrCodec, Wire
from interpreter.project.types import LinkedProgram
from interpreter.project.unit_format_error import UnitFormatError
from interpreter.registry import build_registry
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder

_FORMAT = 9
_DERIVED = frozenset({"merged_cfg", "merged_registry"})


class LinkedCodec:
    def __init__(self, ir: IrCodec) -> None:
        self._ir = ir

    def write(self, linked: LinkedProgram, path: Path) -> None:
        fields = {
            f.name: self._ir.encode(getattr(linked, f.name))
            for f in dataclasses.fields(LinkedProgram)
            if f.name not in _DERIVED
        }
        path.write_text(
            json.dumps({"format": _FORMAT, "linked": fields}), encoding="utf-8"
        )

    def read(self, path: Path) -> LinkedProgram:
        try:
            return self._linked(json.loads(path.read_text(encoding="utf-8")))
        except (UnitFormatError, json.JSONDecodeError, KeyError) as exc:
            raise UnitFormatError(f"{path}: {exc}") from exc

    def _linked(self, wire: Wire) -> LinkedProgram:
        match wire:
            case {"format": 9, "linked": dict(body)}:
                return self._program(body)
            case _:
                raise UnitFormatError(f"not a linked-program file of format {_FORMAT}")

    def _program(self, body: Mapping[str, Wire]) -> LinkedProgram:
        ir = self._ir
        merged_ir = ir.decode_as(body["merged_ir"], list)
        funcs = ir.decode_as(body["func_symbol_table"], dict)
        classes = ir.decode_as(body["class_symbol_table"], dict)
        cfg = build_cfg(merged_ir)
        return LinkedProgram(
            modules=ir.decode_as(body["modules"], dict),
            merged_ir=merged_ir,
            merged_cfg=cfg,
            merged_registry=build_registry(
                merged_ir, cfg, func_symbol_table=funcs, class_symbol_table=classes
            ),
            language=ir.decode_as(body["language"], Language),
            import_graph=ir.decode_as(body["import_graph"], dict),
            type_env_builder=ir.decode_as(
                body["type_env_builder"], TypeEnvironmentBuilder
            ),
            symbol_table=ir.decode_as(body["symbol_table"], SymbolTable),
            unresolved_imports=ir.decode_as(body["unresolved_imports"], list),
            func_symbol_table=funcs,
            class_symbol_table=classes,
            entry_func_label=ir.decode_as(body["entry_func_label"], CodeLabel),
            programs=ir.decode_as(body["programs"], dict),
        )
