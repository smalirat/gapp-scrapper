from __future__ import annotations
import asyncio
import keyring
from keyring.errors import PasswordDeleteError
from .config import save_config

# Passwords are kept in the system store (Credential Manager on Windows, Keychain on macOS,
# Secret Service on Linux). Only the username goes in config.json.
SERVICE = "gapp-scrapper"
ANY_HOST = "*"
# Where the default credentials are used without asking.
GOOGLE_LOGIN_HOST = "accounts.google.com"

def _key(profile: str, host: str) -> str:
    return f"{profile}|{host}"

def save_credential(cfg: dict, profile: str, host: str, username: str, password: str):
    keyring.set_password(SERVICE, _key(profile, host), password)
    cfg["profiles"][profile]["logins"][host]=username

def delete_credentials(cfg: dict, profile: str):
    for host in cfg["profiles"][profile]["logins"]:
        try: keyring.delete_password(SERVICE, _key(profile, host))
        except PasswordDeleteError: pass
    cfg["profiles"][profile]["logins"]={}

def lookup(cfg: dict, profile: str, host: str) -> tuple[str, str, bool] | None:
    """
    Returns (username, password, needs_confirmation) for a login host.
    A host-specific credential takes precedence over the default one ("*").
    The default one is only used without asking on Google's login or on already confirmed hosts.
    """
    data=cfg["profiles"][profile]
    for key in (host, ANY_HOST):
        if key not in data["logins"]: continue
        password=keyring.get_password(SERVICE, _key(profile, key))
        if password is None: continue
        trusted=key == host or host == GOOGLE_LOGIN_HOST or host in data["trusted_hosts"]
        return data["logins"][key], password, not trusted
    return None

class CredentialProvider:
    """Hands out credentials per host during login. Before using the default credentials on a new
    host it asks in the terminal, so they aren't sent to just any page."""

    def __init__(self, cfg: dict, profile: str):
        self.cfg=cfg
        self.profile=profile
        self._denied: set[str]=set()

    def has_any(self) -> bool:
        return bool(self.cfg["profiles"][self.profile]["logins"])

    async def __call__(self, host: str) -> tuple[str, str] | None:
        if host in self._denied: return None
        found=lookup(self.cfg, self.profile, host)
        if not found: return None
        username, password, confirm=found
        if confirm:
            answer=await asyncio.to_thread(input, f"\nUse username '{username}' from profile '{self.profile}' to sign in at {host}? [y/N] ")
            if answer.strip().lower() not in ("y", "yes"):
                self._denied.add(host); return None
            self.cfg["profiles"][self.profile]["trusted_hosts"].append(host)
            save_config(self.cfg)
        return username, password
