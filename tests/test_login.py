"""Tests auto-fill against fake login pages served with page.route (requires Playwright's Chromium)."""
import asyncio
from urllib.parse import parse_qs
import pytest
from playwright.async_api import async_playwright
from gapp_scrapper.login import AutoFiller

SSO_FORM = """<form method="post" action="/done">
  <input name="username" type="text"><input name="password" type="password"><button>Sign in</button>
</form>"""
GOOGLE_EMAIL = """<form method="post" action="/pwd">
  <input type="email" name="identifier"><input type="password" name="hiddenPassword" style="display:none">
  <button>Next</button>
</form>"""
GOOGLE_PWD = """<form method="post" action="/done"><input type="password" name="Passwd"></form>"""

async def _run_login(pages: dict[str, str], start: str, creds_by_host: dict) -> list[dict]:
    submitted=[]
    async def handler(route):
        req=route.request
        path=req.url.split("?")[0]
        if req.method == "POST": submitted.append({k: v[0] for k, v in parse_qs(req.post_data or "").items()})
        body=pages.get(path, "<p>ok</p>")
        await route.fulfill(status=200, content_type="text/html", body=f"<html><body>{body}</body></html>")
    async def credentials(host): return creds_by_host.get(host)
    async with async_playwright() as p:
        try: browser=await p.chromium.launch()
        except Exception as exc: pytest.skip(f"Playwright Chromium not available: {exc}")
        page=await browser.new_page()
        await page.route("https://**/*", handler)
        await page.goto(start)
        filler=AutoFiller(credentials)
        for _ in range(10):
            await filler.step(page)
            await page.wait_for_load_state()
            await asyncio.sleep(0.2)
        await browser.close()
    return submitted

def test_sso_form_filled():
    submitted=asyncio.run(_run_login({"https://sso.test/login": SSO_FORM}, "https://sso.test/login", {"sso.test": ("jdoe", "secret")}))
    assert submitted == [{"username": "jdoe", "password": "secret"}]

def test_google_two_steps():
    pages={"https://accounts.test/email": GOOGLE_EMAIL, "https://accounts.test/pwd": GOOGLE_PWD}
    submitted=asyncio.run(_run_login(pages, "https://accounts.test/email", {"accounts.test": ("me@gmail.com", "secret")}))
    assert submitted[0]["identifier"] == "me@gmail.com"
    assert submitted[1] == {"Passwd": "secret"}

def test_no_credentials_does_nothing():
    submitted=asyncio.run(_run_login({"https://sso.test/login": SSO_FORM}, "https://sso.test/login", {}))
    assert submitted == []
