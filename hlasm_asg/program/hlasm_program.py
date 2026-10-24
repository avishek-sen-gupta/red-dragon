# pyright: standard
"""The program the che4z bridge exports: sections, symbols, statements and literals."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.amode_setting import AmodeSetting
from hlasm_asg.program.diagnostic import Diagnostic
from hlasm_asg.program.entry import Entry
from hlasm_asg.program.external_symbol import ExternalSymbol
from hlasm_asg.program.literal_pool import LiteralPool
from hlasm_asg.program.rmode_setting import RmodeSetting
from hlasm_asg.program.section import Section
from hlasm_asg.program.statement import Statement
from hlasm_asg.program.symbol import Symbol


class HlasmProgram(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    format: int
    sections: tuple[Section, ...]
    symbols: tuple[Symbol, ...]
    entry: Entry
    entries: tuple[str, ...]
    externals: tuple[ExternalSymbol, ...]
    statements: tuple[Statement, ...]
    literals: tuple[LiteralPool, ...]
    amodes: tuple[AmodeSetting, ...]
    rmodes: tuple[RmodeSetting, ...]
    diagnostics: tuple[Diagnostic, ...]
