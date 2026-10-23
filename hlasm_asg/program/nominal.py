# pyright: standard
"""The nominal value of a DC item."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from hlasm_asg.program.addresses_nominal import AddressesNominal
from hlasm_asg.program.omitted_nominal import OmittedNominal
from hlasm_asg.program.string_nominal import StringNominal

Nominal = Annotated[
    StringNominal | AddressesNominal | OmittedNominal, Field(discriminator="kind")
]
