# pyright: standard
"""One record of an object module's external symbol dictionary."""

from interpreter.project.common_section import CommonSection
from interpreter.project.control_section import ControlSection
from interpreter.project.entry_label import EntryLabel
from interpreter.project.external_dummy_section import ExternalDummySection
from interpreter.project.external_reference import ExternalReference
from interpreter.project.weak_reference import WeakReference

type EsdRecord = (
    ControlSection
    | CommonSection
    | EntryLabel
    | ExternalReference
    | WeakReference
    | ExternalDummySection
)
