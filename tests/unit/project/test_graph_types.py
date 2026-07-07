"""Unit tests for the shared knowledge-graph node/edge schema."""

from tests.covers import covers, NotLanguageFeature
from interpreter.project.graph_types import EdgeKind, GraphEdge, GraphNode, NodeKind


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_node_kind_has_expected_members():
    assert {k.value for k in NodeKind} == {
        "PROGRAM",
        "COPYBOOK",
        "TRANSACTION",
        "JOB",
        "STEP",
        "DATASET",
        "BMS_MAP",
        "CICS_FILE",
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_edge_kind_has_expected_members():
    assert {k.value for k in EdgeKind} == {
        "CALL",
        "COPY",
        "XCTL",
        "LINK",
        "RETURN_TRANSID",
        "STARTS",
        "SENDS_MAP",
        "RECEIVES_MAP",
        "JCL_STEP_RUNS",
        "READS",
        "WRITES",
        "UPDATES",
        "DELETES",
        "ENDS_BROWSE",
        "DEFINES_DATASET",
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_graph_node_defaults():
    node = GraphNode(id="COSGN00C", kind=NodeKind.PROGRAM)
    assert node.file_path is None
    assert node.attrs == {}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_graph_node_stores_file_path_and_attrs():
    node = GraphNode(
        id="COSGN00C",
        kind=NodeKind.PROGRAM,
        file_path="/src/COSGN00C.cbl",
        attrs={"parm": "X"},
    )
    assert node.file_path == "/src/COSGN00C.cbl"
    assert node.attrs == {"parm": "X"}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_graph_edge_defaults():
    edge = GraphEdge(
        source="MAIN",
        source_kind=NodeKind.PROGRAM,
        target="SUB",
        target_kind=NodeKind.PROGRAM,
        kind=EdgeKind.CALL,
    )
    assert edge.attrs == {}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_graph_edge_stores_kind_source_target():
    edge = GraphEdge(
        source="MAIN",
        source_kind=NodeKind.PROGRAM,
        target="SUB",
        target_kind=NodeKind.PROGRAM,
        kind=EdgeKind.CALL,
    )
    assert edge.source == "MAIN"
    assert edge.source_kind is NodeKind.PROGRAM
    assert edge.target == "SUB"
    assert edge.target_kind is NodeKind.PROGRAM
    assert edge.kind is EdgeKind.CALL
