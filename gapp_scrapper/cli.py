from __future__ import annotations
import asyncio
import json
import shlex
import shutil
import subprocess
import sys
from typing import Any, Optional
from urllib.parse import urlparse
import typer
from playwright.async_api import Error as PlaywrightError
from .browser import browser_session
from .config import DEFAULT_PROFILE, PROFILE_NAME_RE, load_config, profile_dir, resolve_app, resolve_profile, save_config
from .credentials import ANY_HOST, CredentialProvider, delete_credentials, save_credential
from .discovery import discover
from .models import ScriptApp
from .parser import pretty
from .rpc import call_function

app=typer.Typer(help="CLI explorer for Google Apps Script Web Apps.", no_args_is_help=True)
profile_app=typer.Typer(help="Profiles: browser session and saved credentials.", no_args_is_help=True)
app.add_typer(profile_app, name="profile")

APP_OPT = typer.Option(None, "--app", "-a", help="Saved app or /exec URL. Defaults to the current app.")
SHOW_OPT = typer.Option(False, "--show", help="Show the browser even when no login is needed.")
PROFILE_OPT = typer.Option(None, "--profile", "-p", help="Profile to use (session and credentials). Defaults to the app's.")

def fail(message: str):
    typer.secho(f"Error: {message}", fg="red", err=True); raise typer.Exit(1)

def run(coro):
    try: return asyncio.run(coro)
    except typer.Exit: raise  # subclass of RuntimeError: the error was already reported
    except (RuntimeError, PlaywrightError) as exc: fail(str(exc))

def _resolve_or_exit(cfg: dict, app_: str | None) -> tuple[str | None, str]:
    try: return resolve_app(cfg, app_)
    except RuntimeError as exc: fail(str(exc))

def open_session(cfg: dict, url: str, app_name: str | None, profile: str | None, show: bool):
    """Opens the app with the right profile (saved session + credentials for the login)."""
    try: name=resolve_profile(cfg, app_name, profile)
    except RuntimeError as exc: fail(str(exc))
    provider=CredentialProvider(cfg, name)
    return browser_session(url, profile_dir(name), show, provider if provider.has_any() else None)

def parse_args(raw: list[str]) -> list[Any]:
    """Each argument is parsed as JSON when possible (numbers, lists...); otherwise it's a string."""
    parsed=[]
    for value in raw:
        try: parsed.append(json.loads(value))
        except json.JSONDecodeError: parsed.append(value)
    return parsed

def remember(cfg: dict, name: str | None, info: ScriptApp):
    if name:
        cfg["apps"][name]["functions"]=info.functions; save_config(cfg)

def print_functions(functions: list[str]):
    for f in functions: print(f"  {f}")

@app.command()
def add(name: str = typer.Argument(..., help="Short name for the app."), url: str = typer.Argument(..., help="The app's /exec URL."), profile: Optional[str] = PROFILE_OPT, show: bool = SHOW_OPT):
    """Save an app, discover its functions and make it the current app."""
    cfg=load_config()
    async def _run():
        async with open_session(cfg, url, None, profile, show) as session:
            return await discover(session.page)
    info=run(_run())
    cfg["apps"][name]={"url": url, "functions": info.functions, "profile": profile or DEFAULT_PROFILE}
    cfg["current"]=name
    save_config(cfg)
    print(f"App '{name}' saved and selected. Functions:")
    print_functions(info.functions)

@app.command()
def use(name: str = typer.Argument(..., help="Name of a saved app."), profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Also change the app's profile.")):
    """Change the current app (and optionally its profile)."""
    cfg=load_config()
    _resolve_or_exit(cfg, name)
    if profile:
        if profile not in cfg["profiles"]: fail(f"Profile '{profile}' does not exist. Create it with: gapp profile add {profile}")
        cfg["apps"][name]["profile"]=profile
    cfg["current"]=name; save_config(cfg)
    print(f"Current app: {name} (profile: {cfg['apps'][name].get('profile', DEFAULT_PROFILE)})")

@app.command()
def apps():
    """List saved apps (* = current)."""
    cfg=load_config()
    if not cfg["apps"]: print("No saved apps. Add one with: gapp add <name> <url>"); return
    for name, data in cfg["apps"].items():
        print(f"{'*' if name == cfg['current'] else ' '} {name}  [{data.get('profile', DEFAULT_PROFILE)}]  {data['url']}")

@app.command()
def remove(name: str = typer.Argument(..., help="Name of a saved app.")):
    """Delete a saved app."""
    cfg=load_config()
    if cfg["apps"].pop(name, None) is None: fail(f"App '{name}' does not exist.")
    if cfg["current"] == name: cfg["current"]=None
    save_config(cfg)
    print(f"App '{name}' deleted.")

@app.command()
def functions(app_: Optional[str] = APP_OPT, refresh: bool = typer.Option(False, "--refresh", "-r", help="Query the app again instead of using the saved list."), profile: Optional[str] = PROFILE_OPT, show: bool = SHOW_OPT):
    """List the app's exposed functions."""
    cfg=load_config()
    name, url=_resolve_or_exit(cfg, app_)
    cached=cfg["apps"][name].get("functions") if name else None
    if cached and not refresh:
        print_functions(cached); return
    async def _run():
        async with open_session(cfg, url, name, profile, show) as session:
            return await discover(session.page)
    info=run(_run())
    remember(cfg, name, info)
    print_functions(info.functions)

@app.command()
def call(function: str = typer.Argument(..., help="Function to run."), args: Optional[list[str]] = typer.Argument(None, help="Arguments (parsed as JSON when possible)."), app_: Optional[str] = APP_OPT, profile: Optional[str] = PROFILE_OPT, show: bool = SHOW_OPT):
    """Run one of the app's functions through google.script.run."""
    cfg=load_config()
    name, url=_resolve_or_exit(cfg, app_)
    async def _run():
        async with open_session(cfg, url, name, profile, show) as session:
            info=await discover(session.page)
            remember(cfg, name, info)
            if function not in info.functions:
                raise RuntimeError(f"Function '{function}' is not exposed. Available: {', '.join(info.functions)}")
            return await call_function(await session.find_sandbox(), function, parse_args(args or []))
    print(pretty(run(_run())))

@app.command()
def shell(app_: Optional[str] = APP_OPT, profile: Optional[str] = PROFILE_OPT, show: bool = SHOW_OPT):
    """Interactive session: keeps the app open to call several functions in a row."""
    cfg=load_config()
    name, url=_resolve_or_exit(cfg, app_)
    async def _run():
        async with open_session(cfg, url, name, profile, show) as session:
            info=await discover(session.page)
            remember(cfg, name, info)
            frame=await session.find_sandbox()
            print(f"Connected to {name or url}.")
            print("Type <function> [args...]. Commands: 'functions', 'exit'.")
            while True:
                try: line=await asyncio.to_thread(input, "gapp> ")
                except EOFError: break
                try: parts=shlex.split(line, posix=True)
                except ValueError as exc: print(f"Error: {exc}"); continue
                if not parts: continue
                command, *rest=parts
                if command in ("exit", "quit"): break
                if command in ("functions", "help", "?"): print_functions(info.functions); continue
                if command not in info.functions: print(f"Error: function '{command}' is not exposed."); continue
                try: print(pretty(await call_function(frame, command, parse_args(rest))))
                except Exception as exc: print(f"Error: {exc}")
    run(_run())

# ---------------------------------------------------------------- profiles

def _require_profile(cfg: dict, name: str):
    if name not in cfg["profiles"]: fail(f"Profile '{name}' does not exist. List profiles with: gapp profile list")

def _prompt_credential(cfg: dict, profile: str, host: str, user: str | None):
    user=user or typer.prompt("Username or email")
    password=typer.prompt("Password", hide_input=True)
    save_credential(cfg, profile, host, user, password)

@profile_app.command("list")
def profile_list():
    """List profiles, their saved credentials and which apps use them."""
    cfg=load_config()
    for name, data in cfg["profiles"].items():
        print(name)
        logins=data["logins"]
        if not logins: print("  credentials: (none, manual login)")
        for host, user in logins.items():
            print(f"  {'default' if host == ANY_HOST else host}: {user}")
        if data["trusted_hosts"]: print(f"  confirmed sites: {', '.join(data['trusted_hosts'])}")
        used=[app_name for app_name, a in cfg["apps"].items() if a.get("profile", DEFAULT_PROFILE) == name]
        if used: print(f"  apps: {', '.join(used)}")

@profile_app.command("add")
def profile_add(name: str = typer.Argument(..., help="Profile name (e.g. work, personal)."), user: Optional[str] = typer.Option(None, "--user", "-u", help="Default username or email."), no_credentials: bool = typer.Option(False, "--no-credentials", help="Don't save credentials: login stays manual.")):
    """Create a profile (separate browser session) and save its default username and password."""
    cfg=load_config()
    if not PROFILE_NAME_RE.match(name): fail("Invalid profile name: use letters, numbers, - or _.")
    if name in cfg["profiles"]: fail(f"Profile '{name}' already exists. To change its credentials: gapp profile creds {name}")
    cfg["profiles"][name]={"logins": {}, "trusted_hosts": []}
    if not no_credentials:
        print("Default credentials (used on Google's login and, if you confirm, on the SSO):")
        _prompt_credential(cfg, name, ANY_HOST, user)
    save_config(cfg)
    print(f"Profile '{name}' created. Use it with: gapp add <app> <url> --profile {name}")

@profile_app.command("creds")
def profile_creds(name: str = typer.Argument(..., help="Profile name."), host: Optional[str] = typer.Option(None, "--host", help="Only for this login site (e.g. sso.example.edu). Without --host: the default ones."), user: Optional[str] = typer.Option(None, "--user", "-u", help="Username or email.")):
    """Save or change a profile's credentials. With --host, different credentials for an SSO."""
    cfg=load_config()
    _require_profile(cfg, name)
    # Accepts both 'sso.example.com' and a full URL.
    target=(urlparse(host).hostname or host) if host and "://" in host else (host or ANY_HOST)
    _prompt_credential(cfg, name, target, user)
    save_config(cfg)
    print(f"Credentials saved for {'all logins' if target == ANY_HOST else target} in profile '{name}'.")

@profile_app.command("logout")
def profile_logout(name: str = typer.Argument(..., help="Profile name.")):
    """Sign out of the profile's browser session (saved credentials are kept)."""
    cfg=load_config()
    _require_profile(cfg, name)
    shutil.rmtree(profile_dir(name), ignore_errors=True)
    print(f"Profile '{name}' signed out. The next login will use the saved credentials.")

@profile_app.command("remove")
def profile_remove(name: str = typer.Argument(..., help="Profile name.")):
    """Delete a profile: its session and its credentials."""
    cfg=load_config()
    _require_profile(cfg, name)
    used=[app_name for app_name, a in cfg["apps"].items() if a.get("profile", DEFAULT_PROFILE) == name]
    if name != DEFAULT_PROFILE and used: fail(f"Used by apps: {', '.join(used)}. Change them with: gapp use <app> --profile <other>")
    delete_credentials(cfg, name)
    shutil.rmtree(profile_dir(name), ignore_errors=True)
    if name == DEFAULT_PROFILE:
        # The default profile always exists: it's emptied instead of deleted.
        cfg["profiles"][name]={"logins": {}, "trusted_hosts": []}
        print("Profile 'default' emptied (session and credentials deleted).")
    else:
        del cfg["profiles"][name]
        print(f"Profile '{name}' deleted.")
    save_config(cfg)

# ---------------------------------------------------------------- other

@app.command("install-browser")
def install_browser():
    """Download Playwright's Chromium (only needed if you don't have Google Chrome)."""
    # Run with the same Python so it matches the installed Playwright version.
    raise typer.Exit(subprocess.call([sys.executable, "-m", "playwright", "install", "chromium"]))

@app.command()
def version():
    """Show the version."""
    from . import __version__; print(__version__)

if __name__ == "__main__": app()
