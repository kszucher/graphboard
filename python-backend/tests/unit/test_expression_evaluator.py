from __future__ import annotations

from app.modules.graphs.expressions import evaluate_expression, infer_expression_type


def test_evaluate_literals_and_vars():
    state = {"score": 10, "name": "Antigravity"}
    assert evaluate_expression(42, state) == 42
    assert evaluate_expression("hello", state) == "hello"
    assert evaluate_expression({"var": "score"}, state) == 10
    assert evaluate_expression({"var": "name"}, state) == "Antigravity"
    assert evaluate_expression({"set": 99}, state) == 99


def test_evaluate_atomic_updates():
    state = {"score": 10}
    assert evaluate_expression({"increment": 5}, state, target_var_key="score") == 15
    assert evaluate_expression({"decrement": 3}, state, target_var_key="score") == 7
    assert evaluate_expression({"multiply": 2}, state, target_var_key="score") == 20
    assert evaluate_expression({"divide": 2}, state, target_var_key="score") == 5.0


def test_evaluate_math_ops():
    state = {"a": 10, "b": 3}
    assert evaluate_expression({"op": "add", "left": {"var": "a"}, "right": {"var": "b"}}, state) == 13
    assert evaluate_expression({"op": "subtract", "left": {"var": "a"}, "right": {"var": "b"}}, state) == 7
    assert evaluate_expression({"op": "multiply", "left": {"var": "a"}, "right": {"var": "b"}}, state) == 30
    assert evaluate_expression({"op": "modulo", "left": {"var": "a"}, "right": {"var": "b"}}, state) == 1
    assert evaluate_expression({"op": "round", "val": 3.14159, "ndigits": 2}, state) == 3.14
    assert evaluate_expression({"op": "min", "args": [10, 5, 20]}, state) == 5
    assert evaluate_expression({"op": "max", "args": [10, 5, 20]}, state) == 20


def test_evaluate_string_ops():
    state = {"topic": "Science", "opts": ["A", "B", "C"]}
    assert (
        evaluate_expression({"op": "format", "template": "Topic: {topic}", "vars": ["topic"]}, state)
        == "Topic: Science"
    )
    assert evaluate_expression({"op": "join", "items": {"var": "opts"}, "sep": ", "}, state) == "A, B, C"
    assert evaluate_expression({"op": "split", "text": "apple,banana,cherry", "sep": ","}, state) == [
        "apple",
        "banana",
        "cherry",
    ]


def test_evaluate_collection_ops():
    state = {"items": ["A", "B", "C", "D"]}
    assert evaluate_expression({"op": "length", "items": {"var": "items"}}, state) == 4
    assert evaluate_expression({"op": "append", "items": {"var": "items"}, "item": "E"}, state) == [
        "A",
        "B",
        "C",
        "D",
        "E",
    ]
    assert evaluate_expression({"op": "remove", "items": {"var": "items"}, "item": "B"}, state) == ["A", "C", "D"]
    assert evaluate_expression({"op": "slice", "items": {"var": "items"}, "start": 1, "end": 3}, state) == ["B", "C"]

    sampled = evaluate_expression({"op": "sample", "items": {"var": "items"}, "count": 2}, state)
    assert len(sampled) == 2
    assert all(x in state["items"] for x in sampled)


def test_evaluate_comparisons_and_compound():
    state = {"score": 50, "passed": True}
    assert evaluate_expression({"score": {"gte": 50}}, state) is True
    assert evaluate_expression({"score": {"lt": 50}}, state) is False
    assert evaluate_expression({"score": {"in": [10, 20, 50]}}, state) is True
    assert evaluate_expression({"AND": [{"score": {"gte": 50}}, {"passed": {"equals": True}}]}, state) is True
    assert evaluate_expression({"OR": [{"score": {"lt": 10}}, {"score": {"gte": 50}}]}, state) is True
    assert evaluate_expression({"NOT": {"score": {"lt": 10}}}, state) is True


def test_infer_expression_type():
    var_types = {"score": "number", "name": "string", "active": "boolean", "tags": "array"}

    assert infer_expression_type(10, var_types) == "number"
    assert infer_expression_type("hello", var_types) == "string"
    assert infer_expression_type(True, var_types) == "boolean"
    assert infer_expression_type(["a", "b"], var_types) == "array"
    assert infer_expression_type({"var": "score"}, var_types) == "number"
    assert infer_expression_type({"op": "add", "left": 1, "right": 2}, var_types) == "number"
    assert infer_expression_type({"op": "format", "template": "{name}"}, var_types) == "string"
    assert infer_expression_type({"op": "split", "text": "a,b"}, var_types) == "array"
    assert infer_expression_type({"AND": [{"score": {"gt": 5}}]}, var_types) == "boolean"
