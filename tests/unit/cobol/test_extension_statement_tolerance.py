# pyright: standard
"""The lowering tolerates statement types it did not define.

Coprocessor frontends (cicada's ``EXEC CICS``, squall's ``EXEC SQL``, jackal's
own) register their statement types through the extension-strategy seam and swap
them into the ASG before lowering. Those types are NOT red-dragon dataclasses:
they are whatever the extension declared, so red-dragon may only rely on what the
seam actually promises — a statement its ``dispatch_statement`` can route. Every
other attribute, ``span`` included, is optional and may simply be absent.

red-dragon must not import an extension's types to find that out, so the stand-in
here is a local class with no ``span``, standing for any of them.
"""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.asg_types import CobolASG, CobolParagraph
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.lower_procedure import lower_procedure_division
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.ir import Opcode
from tests.covers import NotLanguageFeature, covers


@dataclass
class _ExtensionStatement:
    """An extension's statement type: routed by verb, and carrying no span.

    Deliberately minimal. Giving it a ``span`` would make the test pass for the
    wrong reason — the point is that red-dragon must not require one.
    """

    verb: str


def _lowered(asg: CobolASG):
    """Lower a program whose statements the core does not know how to dispatch."""

    def _extension_dispatch(ctx, stmt, materialised) -> None:
        """Stands in for the extension strategy that would consume the verb."""

    ctx = EmitContext(dispatch_fn=_extension_dispatch)
    materialised = lower_sectioned_data_division(
        ctx, build_sectioned_layout(asg), asg.program_id
    )
    lower_procedure_division(ctx, asg, materialised)
    return ctx.instructions


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_program_ending_in_an_extension_statement_lowers():
    """A program whose last division-level statement is an extension's own type.

    The implicit program exit borrows the last flow element's span, and this one
    has none. Absent is a legitimate answer -- the exit's span is Optional -- so
    it must yield no span rather than raising (red-dragon-7qmn).
    """
    asg = CobolASG(
        program_id="EXTLAST",
        statements=[_ExtensionStatement(verb="SOMEVERB")],
    )

    instructions = _lowered(asg)

    assert Opcode.RETURN in [
        i.opcode for i in instructions
    ], "the program must still be given its implicit exit"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_extension_statement_inside_a_paragraph_lowers():
    """The same, one level down: paragraphs hold extension statements too."""
    asg = CobolASG(
        program_id="EXTPARA",
        paragraphs=[
            CobolParagraph(
                name="MAIN", statements=[_ExtensionStatement(verb="SOMEVERB")]
            )
        ],
    )

    instructions = _lowered(asg)

    assert Opcode.RETURN in [i.opcode for i in instructions]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_spanless_last_statement_does_not_borrow_an_earlier_span():
    """The exit takes the LAST element's span, and reports absence as absence.

    Falling back to some earlier statement's span would put the implicit exit at a
    line it has nothing to do with -- worse than no location at all, because a
    reader would believe it.
    """
    from interpreter.cobol.lower_procedure import _end_of_flow_span

    asg = CobolASG(
        program_id="EXTMIXED",
        statements=[_ExtensionStatement(verb="SOMEVERB")],
    )

    assert _end_of_flow_span(asg) is None
