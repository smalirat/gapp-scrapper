from __future__ import annotations
from typing import Any
from playwright.async_api import Frame

async def call_function(frame: Frame, function_name: str, args: list[Any]) -> Any:
    script = """
    async ({ functionName, args }) => {
      return await new Promise((resolve, reject) => {
        const runner = google.script.run.withSuccessHandler(resolve).withFailureHandler(error => reject(new Error(error && error.message ? error.message : String(error))));
        if (typeof runner[functionName] !== 'function') { reject(new Error('Function does not exist: ' + functionName)); return; }
        runner[functionName](...args);
      });
    }
    """
    return await frame.evaluate(script, {"functionName": function_name, "args": args})
