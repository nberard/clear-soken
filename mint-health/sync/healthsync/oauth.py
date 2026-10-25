"""OAuth 2.0 Google (code + PKCE) et stockage local du jeton."""
import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from . import config

# state -> code_verifier (flux en cours, en mémoire : un seul utilisateur local)
_pending: dict[str, tuple[str, float]] = {}


def build_auth_url() -> str:
    if not config.GOOGLE_CLIENT_ID:
        raise RuntimeError("GOOGLE_CLIENT_ID n'est pas configuré dans .env")
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    _pending[state] = (verifier, time.time())
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(config.SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{config.AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str, state: str) -> dict:
    entry = _pending.pop(state, None)
    if not entry or time.time() - entry[1] > 600:
        raise ValueError("Paramètre state invalide ou expiré, relance la connexion.")
    verifier = entry[0]
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            config.TOKEN_URL,
            data={
                "code": code,
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "redirect_uri": config.REDIRECT_URI,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
        )
    r.raise_for_status()
    token = r.json()
    token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
    save_token(token)
    return token


def load_token() -> dict | None:
    p = Path(config.TOKEN_FILE)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def save_token(token: dict) -> None:
    p = Path(config.TOKEN_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(token, f)
    os.replace(tmp, p)


def delete_token() -> None:
    Path(config.TOKEN_FILE).unlink(missing_ok=True)


async def get_access_token() -> str | None:
    """Renvoie un access token valide, en le rafraîchissant si besoin."""
    token = load_token()
    if not token:
        return None
    if token.get("expires_at", 0) - 60 > time.time():
        return token["access_token"]
    refresh = token.get("refresh_token")
    if not refresh:
        return None
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            config.TOKEN_URL,
            data={
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
    if r.status_code in (400, 401):
        # refresh token révoqué ou expiré (fréquent en mode « Test » : 7 jours)
        delete_token()
        return None
    r.raise_for_status()
    new = r.json()
    token.update(new)
    token["expires_at"] = time.time() + int(new.get("expires_in", 3600))
    save_token(token)
    return token["access_token"]


async def revoke() -> None:
    token = load_token()
    if token:
        t = token.get("refresh_token") or token.get("access_token")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(config.REVOKE_URL, data={"token": t})
        except httpx.HTTPError:
            pass
    delete_token()
