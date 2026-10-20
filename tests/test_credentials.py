import asyncio
import pytest
from gapp_scrapper import credentials
from gapp_scrapper.credentials import ANY_HOST, CredentialProvider, lookup, save_credential

@pytest.fixture
def cfg(monkeypatch, tmp_path):
    store={}
    monkeypatch.setattr(credentials.keyring, "set_password", lambda s, k, p: store.__setitem__((s, k), p))
    monkeypatch.setattr(credentials.keyring, "get_password", lambda s, k: store.get((s, k)))
    monkeypatch.setattr(credentials, "save_config", lambda c: None)
    return {"profiles": {"work": {"logins": {}, "trusted_hosts": []}}}

def test_default_credential_used_on_google_without_confirmation(cfg):
    save_credential(cfg, "work", ANY_HOST, "me@example.edu", "secret")
    assert lookup(cfg, "work", "accounts.google.com") == ("me@example.edu", "secret", False)

def test_default_credential_needs_confirmation_on_other_host(cfg):
    save_credential(cfg, "work", ANY_HOST, "me@example.edu", "secret")
    assert lookup(cfg, "work", "sso.example.edu") == ("me@example.edu", "secret", True)

def test_host_credential_wins_over_default(cfg):
    save_credential(cfg, "work", ANY_HOST, "me@example.edu", "secret")
    save_credential(cfg, "work", "sso.example.edu", "jdoe", "other")
    assert lookup(cfg, "work", "sso.example.edu") == ("jdoe", "other", False)
    assert lookup(cfg, "work", "accounts.google.com") == ("me@example.edu", "secret", False)

def test_no_credentials(cfg):
    assert lookup(cfg, "work", "accounts.google.com") is None

def test_provider_asks_once_and_remembers(cfg, monkeypatch):
    save_credential(cfg, "work", ANY_HOST, "me", "secret")
    answers=iter(["y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    provider=CredentialProvider(cfg, "work")
    assert asyncio.run(provider("sso.example.edu")) == ("me", "secret")
    assert cfg["profiles"]["work"]["trusted_hosts"] == ["sso.example.edu"]
    # Already confirmed: it doesn't ask again (input would exhaust the iterator).
    assert asyncio.run(provider("sso.example.edu")) == ("me", "secret")

def test_provider_denied(cfg, monkeypatch):
    save_credential(cfg, "work", ANY_HOST, "me", "secret")
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    provider=CredentialProvider(cfg, "work")
    assert asyncio.run(provider("phishing.example.com")) is None
    assert cfg["profiles"]["work"]["trusted_hosts"] == []
