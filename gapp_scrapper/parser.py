from __future__ import annotations
import json
from typing import Any

def parse_nested_json(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text and ((text.startswith("[") and text.endswith("]")) or (text.startswith("{") and text.endswith("}"))):
            try: return parse_nested_json(json.loads(text))
            except json.JSONDecodeError: return value
        return value
    if isinstance(value, list): return [parse_nested_json(x) for x in value]
    if isinstance(value, dict): return {k: parse_nested_json(v) for k, v in value.items()}
    return value

def pretty(value: Any) -> str:
    value = parse_nested_json(value)
    return json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else str(value)
