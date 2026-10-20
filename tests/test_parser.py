from gapp_scrapper.parser import parse_nested_json, pretty

def test_parse_nested_json_strings():
    raw = '["A", "{\\"b\\": \\"[1, 2]\\"}"]'
    assert parse_nested_json(raw) == ["A", {"b": [1, 2]}]

def test_parse_nested_json_leaves_invalid_and_plain():
    assert parse_nested_json("[not json") == "[not json"
    assert parse_nested_json("[broken]") == "[broken]"
    assert parse_nested_json(42) == 42

def test_pretty():
    assert pretty("hello") == "hello"
    assert pretty('{"á": 1}') == '{\n  "á": 1\n}'
