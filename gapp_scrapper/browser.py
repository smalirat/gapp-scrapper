from __future__ import annotations

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlparse
from playwright.async_api import BrowserContext, Error as PlaywrightError, Frame, Page, async_playwright
from .login import AutoFiller, CredentialsFor

LOGIN_TIMEOUT_SECONDS = 300
# Headless auto-login: if it makes no progress in this time (2FA, captcha...), a window is opened.
HEADLESS_LOGIN_TIMEOUT_SECONDS = 60
HEADLESS_IDLE_SECONDS = 15

HAS_SCRIPT_RUN_JS = """
() => typeof google !== 'undefined' && google !== null
   && typeof google.script !== 'undefined' && google.script !== null
   && typeof google.script.run !== 'undefined'
"""

class BrowserSession:
    def __init__(self, url: str, profile_dir: Path, show: bool = False, credentials: CredentialsFor | None = None):
        self.url = url
        self.show = show
        # Persistent profile: keeps the session so you don't have to log in every time.
        self.profile_dir = profile_dir
        self.credentials = credentials
        self._playwright = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self) -> Page:
        self._playwright = await async_playwright().start()
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        await self._open(headless=not self.show)
        if await self._app_ready():
            return self.page
        if self._on_script_host():
            # No redirect to a login page: the URL is not an app (or it was taken down).
            raise RuntimeError(f"The URL is not an accessible Apps Script Web App (page: '{await self.page.title()}').")

        # Login required. With saved credentials, try headless first.
        if self.credentials and not self.show:
            print("The app requires signing in. Signing in with the profile's saved credentials...", file=sys.stderr)
            if await self._login(headless=True):
                print("Signed in.", file=sys.stderr)
                return self.page
            print("Could not complete the login headlessly (2FA, captcha or wrong credentials).", file=sys.stderr)

        # Open a window just for the login.
        if not self.show:
            await self.context.close()
            await self._open(headless=False)
        hint = " (saved credentials are filled in automatically)" if self.credentials else ""
        print(f"Complete the login in the browser window{hint}...", file=sys.stderr)
        await self._login(headless=False)
        print("Signed in.", file=sys.stderr)

        # The session is now saved in the profile: continue headless.
        if not self.show:
            await self.context.close()
            await self._open(headless=True)
            if not await self._app_ready():
                raise RuntimeError("The app did not load after signing in.")
        return self.page

    async def _open(self, headless: bool):
        # Persistent profile and flags to avoid Google's bot detection
        options = dict(
            user_data_dir=self.profile_dir,
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 900},
        )
        try:
            # Prefer the installed Google Chrome: Google blocks logins less than on Chromium.
            self.context = await self._playwright.chromium.launch_persistent_context(channel="chrome", **options)
        except PlaywrightError:
            try:
                self.context = await self._playwright.chromium.launch_persistent_context(**options)
            except PlaywrightError as exc:
                raise RuntimeError(
                    "No browser found. Install Google Chrome or run: gapp install-browser"
                ) from exc

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

        # Hide navigator.webdriver from JavaScript
        await self.page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        await self.page.goto(self.url, wait_until="domcontentloaded", timeout=60000)

    def _on_script_host(self) -> bool:
        return urlparse(self.page.url).hostname == "script.google.com"

    async def _app_ready(self) -> bool:
        """The app is loaded once we're back on script.google.com and the HTML contains goog.script.init()."""
        if not self._on_script_host():
            return False
        try:
            return "goog.script.init(" in await self.page.content()
        except Exception:
            # The page may be navigating (login redirects).
            return False

    async def _login(self, headless: bool) -> bool:
        """
        Waits for the app to load, filling in login forms with the profile's credentials.
        Headless, it returns False when it makes no progress (to switch to a window); with a window it waits for the user.
        """
        filler = AutoFiller(self.credentials) if self.credentials else None
        timeout = HEADLESS_LOGIN_TIMEOUT_SECONDS if headless else LOGIN_TIMEOUT_SECONDS
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.page.is_closed():
                raise RuntimeError("The browser was closed before the login was completed.")
            if await self._app_ready():
                return True
            if filler and filler.active:
                result = await filler.step(self.page)
                if result == "stuck":
                    if headless:
                        return False
                    filler.active = False
                    print("The saved credentials weren't enough: complete the login manually.", file=sys.stderr)
                elif headless and time.monotonic() - filler.last_action > HEADLESS_IDLE_SECONDS:
                    return False
            elif headless:
                return False
            await asyncio.sleep(1)
        if headless:
            return False
        raise RuntimeError(f"The login was not completed within {LOGIN_TIMEOUT_SECONDS // 60} minutes.")

    async def find_sandbox(self) -> Frame:
        if not self.page:
            raise RuntimeError("BrowserSession not started")
        for _ in range(150):
            for frame in self.page.frames:
                if frame == self.page.main_frame or "script.googleusercontent.com" not in (frame.url or ""):
                    continue
                # Some Apps Script frames don't have google.script.run: it has to be checked.
                try:
                    if await frame.evaluate(HAS_SCRIPT_RUN_JS):
                        return frame
                except Exception:
                    # The frame may be loading or have been replaced.
                    continue
            await asyncio.sleep(0.2)
        frames = "\n".join(f"  - {f.url}" for f in self.page.frames)
        raise RuntimeError(f"Apps Script sandbox with google.script.run not found.\nCurrent frames:\n{frames}")

    async def close(self):
        if self.context:
            await self.context.close()
        if self._playwright:
            await self._playwright.stop()

@asynccontextmanager
async def browser_session(url: str, profile_dir: Path, show: bool = False, credentials: CredentialsFor | None = None) -> AsyncIterator[BrowserSession]:
    session = BrowserSession(url, profile_dir, show, credentials)
    try:
        await session.start()
        yield session
    finally:
        await session.close()
