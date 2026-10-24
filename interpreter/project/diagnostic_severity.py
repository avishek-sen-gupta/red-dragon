# pyright: standard
"""How a unit's diagnostic is reported: the logging level it is logged at."""

import logging
from enum import Enum


class DiagnosticSeverity(Enum):
    WARNING = logging.WARNING
    INFO = logging.INFO
