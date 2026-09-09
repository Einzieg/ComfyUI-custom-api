import pytest

from custom_api.errors import APIError
from custom_api.templates import endpoint, parameters, render, render_path, select


def test_types_and_escaping_are_preserved():
    context = {"prompt": '中文 "quoted"\nline', "params": {"n": 2, "flag": False}, "messages": [{"role": "user"}]}
    result = render({"n": "{{params.n}}", "flag": "{{params.flag}}", "messages": "{{messages}}", "text": "Hello {{prompt}}"}, context)
    assert result["n"] == 2 and result["flag"] is False
    assert result["messages"] == [{"role": "user"}]
    assert result["text"] == 'Hello 中文 "quoted"\nline'


def test_path_mapping_and_wildcards():
    response = {"data": [{"url": "a"}, {"url": "b"}], "a.b": {"x": 4}}
    assert select(response, "$.data[*].url") == ["a", "b"]
    assert select(response, '$["a.b"].x') == 4
    assert select(response, "$.missing", None) is None
    with pytest.raises(APIError, match="missing_value"):
        select(response, "$.data[5]")


@pytest.mark.parametrize("value", ["{{__import__('os').system('x')}}", "{{params.__class__}}", "{{[].constructor}}"])
def test_templates_do_not_execute_expressions(value):
    with pytest.raises(APIError):
        render(value, {"params": {}})


def test_endpoint_keeps_base_prefix_and_escapes_variables():
    assert endpoint("https://example.com/v1/", "/images") == "https://example.com/v1/images"
    assert render_path("/tasks/{{task_id}}", {"task_id": "a/b?c"}) == "/tasks/a%2Fb%3Fc"
    for path in ("https://evil.example/", "//evil.example"):
        with pytest.raises(APIError):
            endpoint("https://example.com/v1", path)


def test_parameter_overrides_validate_types_and_bounds():
    schema = [{"name": "n", "type": "integer", "default": 2, "min": 1, "max": 4}]
    assert parameters(schema, {}) == {"n": 2}
    for value in (True, "2", 5, 0):
        with pytest.raises(APIError):
            parameters(schema, {"n": value})
    with pytest.raises(APIError):
        parameters([{"name": "x", "type": "number"}], {"x": float("nan")})
