from __future__ import annotations
import json
import re
from playwright.async_api import Page
from .models import ScriptApp

# Captures only the first argument (a JS string literal); more arguments follow it.
INIT_RE = re.compile(r'goog\.script\.init\("(?P<payload>(?:[^"\\]|\\.)*)"', re.DOTALL)
JS_ESCAPE_RE = re.compile(r'\\(x[0-9a-fA-F]{2}|.)', re.DOTALL)

def _js_escape_to_json(match: re.Match) -> str:
    esc=match.group(1)
    if esc.startswith("x") and len(esc) == 3: return "\\u00" + esc[1:]
    if esc == "'": return "'"
    return "\\" + esc

def decode_js_string(encoded: str) -> str:
    """Decodes the contents of a JS string literal ("...") preserving non-ASCII characters."""
    return json.loads('"' + JS_ESCAPE_RE.sub(_js_escape_to_json, encoded) + '"')

def decode_init_payload(page_source: str) -> dict:
    match=INIT_RE.search(page_source)
    if not match: raise RuntimeError("goog.script.init() not found in the /exec HTML.")
    try:
        return json.loads(decode_js_string(match.group("payload")))
    except Exception as exc:
        raise RuntimeError(f"Could not decode goog.script.init(): {exc}") from exc

async def discover(page: Page) -> ScriptApp:
    payload=decode_init_payload(await page.content())
    return ScriptApp(url=page.url, deployment_id=payload.get("deploymentId"), sandbox_host=payload.get("sandboxHost"), functions=payload.get("functionNames") or [])
