import pytest
from gapp_scrapper.discovery import decode_init_payload, decode_js_string

def test_decode_init_payload_hex_escapes():
    # Real format: the JSON comes inside a JS string with quotes escaped as \x22, more arguments
    # follow the payload, and there's another '")' later in the page.
    html = (r'<script>goog.script.init("\x7b\x22functionNames\x22:\x5b\x22apiGetCareers\x22,\x22apiGetSubjects\x22\x5d,'
            r'\x22deploymentId\x22:\x22AKfy\x22,\x22userHtml\x22:\x22\x3cp\x3e\\\x22hello\\\x22\x3c\\\/p\x3e\x22\x7d", "", undefined, true , false  , "false");'
            r'console.log("x")</script>')
    payload = decode_init_payload(html)
    assert payload["functionNames"] == ["apiGetCareers", "apiGetSubjects"]
    assert payload["deploymentId"] == "AKfy"
    assert payload["userHtml"] == '<p>"hello"</p>'

def test_decode_init_payload_preserves_non_ascii():
    html = 'goog.script.init("{\\x22title\\x22:\\x22Análisis Matemático\\x22}")'
    assert decode_init_payload(html) == {"title": "Análisis Matemático"}

def test_decode_js_string_escapes():
    assert decode_js_string(r"a\'b") == "a'b"
    assert decode_js_string(r"\\x22") == "\\x22"  # escaped backslash: not a \x escape
    assert decode_js_string(r"á\n\/") == "á\n/"

def test_decode_init_payload_missing():
    with pytest.raises(RuntimeError, match="goog.script.init"):
        decode_init_payload("<html></html>")
