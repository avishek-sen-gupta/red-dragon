"""Which construct an EXIT leaves."""

from enum import StrEnum


class ExitKind(StrEnum):
    """PLAIN is the paragraph-end no-op; the rest leave the named construct."""

    PLAIN = ""
    PARAGRAPH = "paragraph"
    SECTION = "section"
    PERFORM = "perform"
    PERFORM_CYCLE = "perform-cycle"
