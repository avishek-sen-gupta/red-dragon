"""Integration tests: field initializers + method chaining across languages.

Verifies that field initializers populate heap object fields correctly,
so that method chaining (return this) works end-to-end.

counter.increment().increment().get_value() => answer = 2
"""

from __future__ import annotations

import pytest

from tests.unit.rosetta.conftest import execute_for_language, extract_answer

PROGRAMS: dict[str, str] = {
    "java": """\
class Counter {
    int count = 0;
    Counter increment() {
        this.count = this.count + 1;
        return this;
    }
    int get_value() {
        return this.count;
    }
}

class M {
    static Counter counter = new Counter();
    static Counter result = counter.increment().increment();
    static int answer = result.get_value();
}
""",
    "csharp": """\
class Counter {
    int count = 0;
    Counter increment() {
        this.count = this.count + 1;
        return this;
    }
    int get_value() {
        return this.count;
    }
}

Counter counter = new Counter();
Counter result = counter.increment().increment();
int answer = result.get_value();
""",
    "kotlin": """\
class Counter {
    var count: Int = 0
    fun increment(): Counter {
        this.count = this.count + 1
        return this
    }
    fun get_value(): Int {
        return this.count
    }
}

val counter = Counter()
val result = counter.increment().increment()
val answer = result.get_value()
""",
    "php": """\
<?php
class Counter {
    public $count = 0;
    function increment() {
        $this->count = $this->count + 1;
        return $this;
    }
    function get_value() {
        return $this->count;
    }
}

$counter = new Counter();
$result = $counter->increment()->increment();
$answer = $result->get_value();
?>
""",
    "scala": """\
class Counter {
    var count: Int = 0
    def increment(): Counter = {
        this.count = this.count + 1
        return this
    }
    def get_value(): Int = {
        return this.count
    }
}

val counter = new Counter()
val result = counter.increment().increment()
val answer = result.get_value()
""",
    "cpp": """\
class Counter {
public:
    int count = 0;
    Counter increment() {
        this->count = this->count + 1;
        return *this;
    }
    int get_value() {
        return this->count;
    }
};

Counter counter;
Counter result = counter.increment().increment();
int answer = result.get_value();
""",
}

EXPECTED_ANSWER = 2


class TestFieldInitMethodChaining:
    @pytest.fixture(
        params=sorted(PROGRAMS.keys()),
        ids=lambda lang: lang,
        scope="class",
    )
    def execution_result(self, request):
        lang = request.param
        vm, stats = execute_for_language(lang, PROGRAMS[lang])
        return lang, vm, stats

    def test_correct_answer(self, execution_result):
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

    def test_count_field_is_concrete(self, execution_result):
        """The count field on the heap object should be a concrete integer, not symbolic."""
        lang, vm, _stats = execution_result
        heap_objects = [obj for obj in vm.heap.values() if obj.type_hint == "Counter"]
        assert len(heap_objects) >= 1, f"[{lang}] expected Counter heap object"
        counter_obj = heap_objects[0]
        assert "count" in counter_obj.fields, (
            f"[{lang}] expected 'count' field on Counter heap object, "
            f"got fields: {list(counter_obj.fields.keys())}"
        )
        count_val = counter_obj.fields["count"]
        assert isinstance(
            count_val, int
        ), f"[{lang}] expected count to be int, got {type(count_val).__name__}: {count_val}"
        assert (
            count_val == EXPECTED_ANSWER
        ), f"[{lang}] expected count={EXPECTED_ANSWER}, got {count_val}"
