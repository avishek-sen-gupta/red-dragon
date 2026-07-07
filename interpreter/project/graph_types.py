"""Shared node/edge schema for the COBOL/CICS/JCL knowledge graph.

Every source in the codebase (a COBOL program, a copybook, a CICS
transaction, a JCL job/step, a dataset, a BMS map) is a GraphNode; every
relationship between them (CALL, COPY, XCTL, JCL step sequencing, dataset
access, ...) is a GraphEdge. Node identity is (kind, id) — id is a logical
name (program-id, transaction-id, "JOBNAME.STEPNAME", ...), never a file
path, and is uppercased by every extractor at extraction time.

Consumers: interpreter.project.cobol_connections (this repo), cics.flow_map
(cicada), a new jackal JCL extractor, and red-dragon-forge's knowledge_graph
package, which merges all three into one graph. This module has no
knowledge of any of them — it is pure vocabulary, the same role
interpreter.project.coprocessor_compile plays for CoprocessorSpec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeKind(Enum):
    PROGRAM = "PROGRAM"
    COPYBOOK = "COPYBOOK"
    TRANSACTION = "TRANSACTION"
    JOB = "JOB"
    STEP = "STEP"
    DATASET = "DATASET"
    BMS_MAP = "BMS_MAP"


class EdgeKind(Enum):
    CALL = "CALL"
    COPY = "COPY"
    XCTL = "XCTL"
    LINK = "LINK"
    RETURN_TRANSID = "RETURN_TRANSID"
    STARTS = "STARTS"
    SENDS_MAP = "SENDS_MAP"
    RECEIVES_MAP = "RECEIVES_MAP"
    JCL_STEP_RUNS = "JCL_STEP_RUNS"
    READS = "READS"
    WRITES = "WRITES"
    UPDATES = "UPDATES"


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: NodeKind
    file_path: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    source: str
    source_kind: NodeKind
    target: str
    target_kind: NodeKind
    kind: EdgeKind
    attrs: dict[str, Any] = field(default_factory=dict)
