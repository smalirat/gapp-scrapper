from __future__ import annotations
import time
from typing import Awaitable, Callable
from urllib.parse import urlparse
from playwright.async_api import Error as PlaywrightError, Locator, Page

CredentialsFor = Callable[[str], Awaitable["tuple[str, str] | None"]]

PASSWORD_SELECTOR = "input[type=password]:visible"
# Screens that only ask for the username (e.g. the first step of Google's login).
IDENTIFIER_SELECTOR = "input[type=email]:visible, input[name=identifier]:visible, input[autocomplete=username]:visible"
# Username field next to the password field (e.g. SSO forms).
USER_SELECTOR = IDENTIFIER_SELECTOR + ", input[name=username]:visible, input[type=text]:visible"
# If the page stays in the same place after filling a step, the credentials weren't enough.
STUCK_SECONDS = 8

class AutoFiller:
    """Fills in login forms (Google and generic SSO) with the profile's credentials."""

    def __init__(self, credentials: CredentialsFor):
        self.credentials=credentials
        self.active=True
        self.last_action=time.monotonic()
        self._filled: dict[tuple, float]={}

    async def step(self, page: Page) -> str:
        """Returns 'filled', 'idle' or 'stuck' (this step was already filled and the page didn't move on)."""
        url=urlparse(page.url)
        if url.scheme != "https": return "idle"
        try:
            password=page.locator(PASSWORD_SELECTOR).first
            if await password.count():
                return await self._fill(page, url, "password", password)
            identifier=page.locator(IDENTIFIER_SELECTOR).first
            if await identifier.count():
                return await self._fill(page, url, "identifier", identifier)
        except PlaywrightError:
            # The page may be navigating between login steps.
            pass
        return "idle"

    async def _fill(self, page: Page, url, kind: str, field: Locator) -> str:
        key=(url.hostname, url.path, kind)
        if key in self._filled:
            return "stuck" if time.monotonic() - self._filled[key] > STUCK_SECONDS else "idle"
        creds=await self.credentials(url.hostname)
        if not creds: return "idle"
        username, password=creds
        if kind == "password":
            user=page.locator(USER_SELECTOR).first
            if await user.count() and not await user.input_value():
                await user.fill(username)
            await field.fill(password)
        else:
            await field.fill(username)
        await field.press("Enter")
        self._filled[key]=self.last_action=time.monotonic()
        return "filled"
