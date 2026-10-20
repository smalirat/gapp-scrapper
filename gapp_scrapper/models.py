from __future__ import annotations
from dataclasses import dataclass

@dataclass
class ScriptApp:
    url: str
    deployment_id: str | None
    sandbox_host: str | None
    functions: list[str]
