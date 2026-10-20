from __future__ import annotations
import json
import os
import re
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("GAPP_SCRAPPER_HOME") or Path.home() / ".gapp-scrapper")
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_PROFILE = "default"
PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

def load_config() -> dict:
    """
    {"current": name | None,
     "apps": {name: {"url": ..., "functions": [...], "profile": profile}},
     "profiles": {profile: {"logins": {host | "*": username}, "trusted_hosts": [...]}}}
    Passwords are not stored here: they live in the system credential store (see credentials.py).
    """
    try:
        cfg=json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        cfg={}
    cfg.setdefault("current", None)
    cfg.setdefault("apps", {})
    cfg.setdefault("profiles", {}).setdefault(DEFAULT_PROFILE, {})
    for profile in cfg["profiles"].values():
        profile.setdefault("logins", {})
        profile.setdefault("trusted_hosts", [])
    return cfg

def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def resolve_app(cfg: dict, app: str | None) -> tuple[str | None, str]:
    """Returns (name, url). `app` can be a saved name, a URL or None (the current app)."""
    if app and app.startswith(("http://", "https://")): return None, app
    name=app or cfg["current"]
    if not name: raise RuntimeError("No app selected. Save one with: gapp add <name> <url>")
    if name not in cfg["apps"]: raise RuntimeError(f"App '{name}' does not exist. List saved apps with: gapp apps")
    return name, cfg["apps"][name]["url"]

def resolve_profile(cfg: dict, app_name: str | None, profile: str | None) -> str:
    """An explicit profile wins; otherwise the app's; otherwise the default one."""
    name=profile or (cfg["apps"][app_name].get("profile") if app_name else None) or DEFAULT_PROFILE
    if name not in cfg["profiles"]: raise RuntimeError(f"Profile '{name}' does not exist. Create it with: gapp profile add {name}")
    return name

def profile_dir(name: str) -> Path:
    """The profile's Chrome folder (session cookies)."""
    if not PROFILE_NAME_RE.match(name): raise RuntimeError(f"Invalid profile name: '{name}' (use letters, numbers, - or _).")
    # The default profile keeps the folder used before profiles existed.
    return CONFIG_DIR / "browser-profile" if name == DEFAULT_PROFILE else CONFIG_DIR / "profiles" / name
