# gapp-scrapper

CLI explorer for Google Apps Script Web Apps: it discovers the server functions exposed to `google.script.run` and lets you call them directly.

## Installation

Requires Python 3.10+. The recommended way is [pipx](https://pipx.pypa.io), which installs it isolated and puts the command on your PATH:

```sh
pipx install "git+https://github.com/<user>/<repo>"
gapp --help
```

Or from a local clone: `pipx install <project-folder>`.

pip works too: `pip install <project-folder>`.

It uses your installed Google Chrome. If you don't have it, download Playwright's Chromium with `gapp install-browser`.

For development: `pip install -e .` (code changes apply without reinstalling).

## Usage

Save the app once under a short name. It becomes the current app:

```sh
gapp add demo "https://script.google.com/macros/s/.../exec"
```

Then call its functions directly:

```sh
gapp functions                       # list functions (saved list; --refresh to query again)
gapp call getUrl
gapp call apiGetLevels Systems
gapp call apiGetSubjects "Systems Engineering" "Level 1"
gapp call add 2 3                    # arguments are parsed as JSON when possible: these arrive as numbers
```

`call` prints only the result (messages and errors go to stderr), so it can be redirected:
`gapp call apiGetCareers > careers.json`.

To call several functions in a row without restarting the browser each time:

```sh
gapp shell
gapp> getUrl
gapp> apiGetLevels Systems
gapp> functions
gapp> exit
```

Managing apps:

```sh
gapp apps            # list saved apps (* = current)
gapp use work        # change the current app
gapp remove demo     # delete one
gapp call getUrl --app work                                   # use another app without changing the current one
gapp call getUrl --app "https://script.google.com/.../exec"   # or a URL directly
```

## Login and profiles

Everything runs headless. A **profile** is a saved browser session plus, optionally, the credentials to sign in.
Each app uses a profile (`default` unless told otherwise). As long as the profile's session is still valid,
nothing opens.

If the app requires signing in:

1. With saved credentials, it signs in **headlessly**, filling in Google's and the SSO's forms.
2. If that's not possible (2FA, captcha, wrong credentials) or there are no credentials, Chrome opens with the
   data already filled in; you finish the login and the window closes on its own once the app loads.

```sh
gapp profile add work                              # asks for the default username and password
gapp profile creds work --host sso.example.edu     # optional: different credentials only for that SSO
gapp add subjects "https://script.google.com/a/macros/example.edu/s/.../exec" --profile work

gapp profile list              # profiles, credentials (without passwords) and the apps using them
gapp use subjects --profile x  # change an app's profile
gapp profile logout work       # sign out of the browser session (keeps the credentials)
gapp profile remove work       # delete session and credentials
```

**Default and per-site credentials.** A profile's default credentials work for any login, so you don't have to
enter them twice when the SSO uses the same data as Google. If the SSO uses different data, add it with `--host`;
it takes precedence on that site.

**Security.** Passwords are kept in the system store (Windows Credential Manager, macOS Keychain), never in plain
text. Default credentials are only filled in automatically on `accounts.google.com`; on any other login site
you're asked once in the terminal before they're used, so a third-party URL can't capture them with a fake page.

With `--show` the browser is always visible. Configuration and profiles live in `~/.gapp-scrapper`
(override it with the `GAPP_SCRAPPER_HOME` environment variable).

> Profile folders contain your accounts' cookies: don't share them or push them to a repository.

## Commands

| Command | What it does |
|---|---|
| `gapp add <name> <url>` | Save an app, discover its functions and make it current |
| `gapp apps` | List saved apps |
| `gapp use <name>` | Change the current app (`--profile` also changes its profile) |
| `gapp remove <name>` | Delete a saved app |
| `gapp functions` | List the app's functions (`--refresh` to query again) |
| `gapp call <function> [args...]` | Run a function and print the result |
| `gapp shell` | Interactive session to call several functions in a row |
| `gapp profile add <name>` | Create a profile with default credentials |
| `gapp profile creds <name>` | Change credentials (`--host` for a specific site) |
| `gapp profile list` | List profiles |
| `gapp profile logout <name>` | Sign out of the profile's session |
| `gapp profile remove <name>` | Delete a profile |
| `gapp install-browser` | Download Chromium (if Chrome isn't installed) |
| `gapp version` | Show the version |

Common options: `--app/-a <name or URL>`, `--profile/-p <profile>`, `--show`.

## Tests

```sh
pytest
```
