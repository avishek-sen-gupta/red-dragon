"""Rosetta test: linked list traversal across all 15 deterministic frontends.

Every program builds a 3-node singly linked list (values 1, 2, 3) and sums
the values by recursive traversal: ``sum_list(head, 3) => 6``.

Languages use their most natural node representation: classes, structs,
records, or tables.  A ``count`` parameter avoids null-check semantics that
vary across frontends.

14 frontends produce concrete ``answer == 6``.  1 (Pascal) returns
SymbolicValue due to array-index traversal limitations.
"""

import pytest

from interpreter.frontends import SUPPORTED_DETERMINISTIC_LANGUAGES
from interpreter.ir import Opcode

from tests.unit.rosetta.conftest import (
    parse_for_language,
    find_all,
    assert_clean_lowering,
    assert_cross_language_consistency,
    execute_for_language,
    extract_answer,
    STANDARD_EXECUTABLE_LANGUAGES,
)

# ---------------------------------------------------------------------------
# Programs: linked list node traversal in all 15 languages.
# Each builds a 3-node list (1 -> 2 -> 3) and sums values = 6.
# A `count` parameter controls recursion depth to avoid null-check variance.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
class Node:
    def __init__(self, value, next_node):
        self.value = value
        self.next_node = next_node

def sum_list(node, count):
    if count <= 0:
        return 0
    return node.value + sum_list(node.next_node, count - 1)

n3 = Node(3, None)
n2 = Node(2, n3)
n1 = Node(1, n2)
answer = sum_list(n1, 3)
""",
    "javascript": """\
class Node {
    constructor(value, nextNode) {
        this.value = value;
        this.nextNode = nextNode;
    }
}

function sumList(node, count) {
    if (count <= 0) {
        return 0;
    }
    return node.value + sumList(node.nextNode, count - 1);
}

let n3 = new Node(3, null);
let n2 = new Node(2, n3);
let n1 = new Node(1, n2);
let answer = sumList(n1, 3);
""",
    "typescript": """\
class Node {
    value: number;
    nextNode: Node | null;

    constructor(value: number, nextNode: Node | null) {
        this.value = value;
        this.nextNode = nextNode;
    }
}

function sumList(node: Node, count: number): number {
    if (count <= 0) {
        return 0;
    }
    return node.value + sumList(node.nextNode!, count - 1);
}

let n3: Node = new Node(3, null);
let n2: Node = new Node(2, n3);
let n1: Node = new Node(1, n2);
let answer: number = sumList(n1, 3);
""",
    "java": """\
class Node {
    int value;
    Node nextNode;

    Node(int value, Node nextNode) {
        this.value = value;
        this.nextNode = nextNode;
    }
}

class M {
    static int sumList(Node node, int count) {
        if (count <= 0) {
            return 0;
        }
        return node.value + sumList(node.nextNode, count - 1);
    }

    static Node n3 = new Node(3, null);
    static Node n2 = new Node(2, n3);
    static Node n1 = new Node(1, n2);
    static int answer = sumList(n1, 3);
}
""",
    "ruby": """\
class Node
    def initialize(value, next_node)
        @value = value
        @next_node = next_node
    end

    def value
        return @value
    end

    def next_node
        return @next_node
    end
end

def sum_list(node, count)
    if count <= 0
        return 0
    end
    return node.value + sum_list(node.next_node, count - 1)
end

n3 = Node.new(3, nil)
n2 = Node.new(2, n3)
n1 = Node.new(1, n2)
answer = sum_list(n1, 3)
""",
    "go": """\
package main

type Node struct {
    value    int
    nextNode *Node
}

func sumList(node *Node, count int) int {
    if count <= 0 {
        return 0
    }
    return node.value + sumList(node.nextNode, count - 1)
}

func main() {
    n3 := &Node{value: 3, nextNode: nil}
    n2 := &Node{value: 2, nextNode: n3}
    n1 := &Node{value: 1, nextNode: n2}
    answer := sumList(n1, 3)
    _ = answer
}
""",
    "php": """\
<?php
class Node {
    public $value;
    public $nextNode;

    function __construct($value, $nextNode) {
        $this->value = $value;
        $this->nextNode = $nextNode;
    }
}

function sum_list($node, $count) {
    if ($count <= 0) {
        return 0;
    }
    return $node->value + sum_list($node->nextNode, $count - 1);
}

$n3 = new Node(3, null);
$n2 = new Node(2, $n3);
$n1 = new Node(1, $n2);
$answer = sum_list($n1, 3);
?>
""",
    "csharp": """\
class Node {
    public int value;
    public Node nextNode;

    public Node(int value, Node nextNode) {
        this.value = value;
        this.nextNode = nextNode;
    }
}

class M {
    static int SumList(Node node, int count) {
        if (count <= 0) {
            return 0;
        }
        return node.value + SumList(node.nextNode, count - 1);
    }

    static Node n3 = new Node(3, null);
    static Node n2 = new Node(2, n3);
    static Node n1 = new Node(1, n2);
    static int answer = SumList(n1, 3);
}
""",
    "c": """\
struct Node {
    int value;
    struct Node* next_node;
};

int sum_list(struct Node* node, int count) {
    if (count <= 0) {
        return 0;
    }
    return node->value + sum_list(node->next_node, count - 1);
}

struct Node n3 = {3, 0};
struct Node n2 = {2, &n3};
struct Node n1 = {1, &n2};
int answer = sum_list(&n1, 3);
""",
    "cpp": """\
class Node {
public:
    int value;
    Node* nextNode;

    Node(int value, Node* nextNode) {
        this->value = value;
        this->nextNode = nextNode;
    }
};

int sumList(Node* node, int count) {
    if (count <= 0) {
        return 0;
    }
    return node->value + sumList(node->nextNode, count - 1);
}

Node* n3 = new Node(3, nullptr);
Node* n2 = new Node(2, n3);
Node* n1 = new Node(1, n2);
int answer = sumList(n1, 3);
""",
    "rust": """\
struct Node {
    value: i32,
    next_node: Option<Box<Node>>,
}

fn sum_list(node: &Node, count: i32) -> i32 {
    if count <= 0 {
        return 0;
    }
    return node.value + sum_list(node.next_node.as_ref().unwrap(), count - 1);
}

let n3 = Node { value: 3, next_node: None };
let n2 = Node { value: 2, next_node: Some(Box::new(n3)) };
let n1 = Node { value: 1, next_node: Some(Box::new(n2)) };
let answer = sum_list(&n1, 3);
""",
    "kotlin": """\
class Node(val value: Int, val nextNode: Node?)

fun sumList(node: Node, count: Int): Int {
    if (count <= 0) {
        return 0
    }
    return node.value + sumList(node.nextNode!!, count - 1)
}

val n3 = Node(3, null)
val n2 = Node(2, n3)
val n1 = Node(1, n2)
val answer = sumList(n1, 3)
""",
    "scala": """\
object M {
    class Node(val value: Int, val nextNode: Node)

    def sumList(node: Node, count: Int): Int = {
        if (count <= 0) {
            return 0
        }
        return node.value + sumList(node.nextNode, count - 1)
    }

    val n3 = new Node(3, null)
    val n2 = new Node(2, n3)
    val n1 = new Node(1, n2)
    val answer = sumList(n1, 3)
}
""",
    "lua": """\
function newNode(value, nextNode)
    local node = {}
    node.value = value
    node.nextNode = nextNode
    return node
end

function sum_list(node, count)
    if count <= 0 then
        return 0
    end
    return node.value + sum_list(node.nextNode, count - 1)
end

n3 = newNode(3, nil)
n2 = newNode(2, n3)
n1 = newNode(1, n2)
answer = sum_list(n1, 3)
""",
    "pascal": """\
program M;

type
    TNode = record
        value: integer;
        nextIdx: integer;
    end;

var
    nodes: array[0..2] of TNode;
    answer: integer;

function sumList(idx: integer; count: integer): integer;
begin
    if count <= 0 then
        sumList := 0
    else
        sumList := nodes[idx].value + sumList(nodes[idx].nextIdx, count - 1);
end;

begin
    nodes[0].value := 1;
    nodes[0].nextIdx := 1;
    nodes[1].value := 2;
    nodes[1].nextIdx := 2;
    nodes[2].value := 3;
    nodes[2].nextIdx := 0;
    answer := sumList(0, 3);
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.CALL_FUNCTION,
    Opcode.BRANCH_IF,
}

MIN_INSTRUCTIONS = 8


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestLinkedListLowering:
    @pytest.fixture(params=sorted(PROGRAMS.keys()), ids=lambda lang: lang)
    def language_ir(self, request):
        lang = request.param
        ir = parse_for_language(lang, PROGRAMS[lang])
        return lang, ir

    def test_clean_lowering(self, language_ir):
        lang, ir = language_ir
        assert_clean_lowering(
            ir,
            min_instructions=MIN_INSTRUCTIONS,
            required_opcodes=REQUIRED_OPCODES,
            language=lang,
        )

    def test_call_function_present(self, language_ir):
        """Verify CALL_FUNCTION instructions exist for the recursive calls."""
        lang, ir = language_ir
        calls = find_all(ir, Opcode.CALL_FUNCTION)
        assert (
            len(calls) >= 2
        ), f"[{lang}] expected at least 2 CALL_FUNCTION (constructor + recursion), got {len(calls)}"

    def test_field_access_present(self, language_ir):
        """Verify LOAD_FIELD instructions exist for node.value / node.next_node."""
        lang, ir = language_ir
        fields = find_all(ir, Opcode.LOAD_FIELD)
        assert (
            len(fields) >= 1
        ), f"[{lang}] expected at least 1 LOAD_FIELD for node field access, got {len(fields)}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestLinkedListCrossLanguage:
    @pytest.fixture(scope="class")
    def all_results(self):
        return {lang: parse_for_language(lang, PROGRAMS[lang]) for lang in PROGRAMS}

    def test_all_languages_covered(self):
        assert set(PROGRAMS.keys()) == set(SUPPORTED_DETERMINISTIC_LANGUAGES)

    def test_cross_language_consistency(self, all_results):
        assert_cross_language_consistency(
            all_results, required_opcodes=REQUIRED_OPCODES
        )


# ---------------------------------------------------------------------------
# VM execution tests
# ---------------------------------------------------------------------------

# Languages where field access on heap objects resolves to concrete values.
CONCRETE_LANGUAGES: frozenset[str] = frozenset(
    {
        "python",
        "javascript",
        "typescript",
        "java",
        "ruby",
        "csharp",
        "php",
        "go",
        "lua",
        "c",
        "cpp",
        "kotlin",
        "scala",
        "rust",
        "pascal",
    }
)

EXPECTED_ANSWER = 6  # 1 + 2 + 3


class TestLinkedListConcreteExecution:
    """Languages that produce concrete answer = 6."""

    @pytest.fixture(
        params=sorted(CONCRETE_LANGUAGES), ids=lambda lang: lang, scope="class"
    )
    def execution_result(self, request):
        lang = request.param
        vm, stats = execute_for_language(lang, PROGRAMS[lang])
        return lang, vm, stats

    def test_correct_result(self, execution_result):
        lang, vm, _stats = execution_result
        answer = extract_answer(vm, lang)
        assert (
            answer == EXPECTED_ANSWER
        ), f"[{lang}] expected answer={EXPECTED_ANSWER}, got {answer}"

    def test_zero_llm_calls(self, execution_result):
        lang, _vm, stats = execution_result
        assert (
            stats.llm_calls == 0
        ), f"[{lang}] expected 0 LLM calls, got {stats.llm_calls}"
