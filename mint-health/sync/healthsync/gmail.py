"""Achats détectés dans Gmail : confirmations de commande des boutiques de CBD.

Utilise le même compte Google que la synchro santé, avec en plus le scope gmail.readonly
(GMAIL_SYNC=true, puis « Connecter » à nouveau). Seuls les mails qui répondent à GMAIL_QUERY sont
lus ; on ne garde que la date, la boutique, les produits et les molécules (pas le mail).
"""
from __future__ import annotations

import base64
import html
import logging
import re
from datetime import date, datetime, timedelta, timezone

import httpx

from . import commandes, config, conso, oauth, store

log = logging.getLogger("healthsync.gmail")
API = "https://gmail.googleapis.com/gmail/v1/users/me"
SOURCE = "gmail"


class ScopeManquant(Exception):
    pass


def _texte(payload: dict) -> str:
    """Corps texte d'un message (text/plain, sinon HTML sans balises)."""
    plain, rich = [], []

    def walk(p: dict) -> None:
        mime = p.get("mimeType", "")
        data = (p.get("body") or {}).get("data")
        if data:
            raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
            (plain if mime == "text/plain" else rich if mime == "text/html" else []).append(raw)
        for part in p.get("parts") or []:
            walk(part)

    walk(payload)
    if plain:
        return "\n".join(plain)
    h = "\n".join(rich)
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|td|th|li|h\d)>", "\n", h)
    return html.unescape(re.sub(r"<[^>]+>", " ", h))


def _entete(msg: dict, nom: str) -> str:
    for h in (msg.get("payload") or {}).get("headers", []):
        if h.get("name", "").lower() == nom.lower():
            return h.get("value", "")
    return ""


async def _get(client: httpx.AsyncClient, token: str, path: str, **params) -> dict:
    r = await client.get(f"{API}/{path}", params=params, headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 403:
        raise ScopeManquant(r.text[:200])
    r.raise_for_status()
    return r.json()


def evenements(msg_id: str, at: datetime, cmd: commandes.Commande) -> list[dict]:
    produits = [
        {"produit": l.produit, "substances": l.substances, "grammes": l.grammes, "quantite": l.quantite}
        for l in cmd.lignes
    ]
    rows = []
    for sub in cmd.substances:
        g = sum(l.grammes or 0 for l in cmd.lignes if sub in l.substances) or None
        rows.append(
            {"at": at, "substance": sub, "kind": "achat", "source": SOURCE, "confiance": "deduit",
             "ref": msg_id, "grammes": g,
             "detail": {"boutique": cmd.boutique, "total": cmd.total, "produits": produits}}
        )
    return rows


async def run() -> dict:
    if not config.GMAIL_SYNC or not config.GMAIL_QUERY:
        return {"status": "desactive"}
    token = await oauth.get_access_token()
    if not token:
        return {"status": "not_connected"}
    reg = await conso.reglages()
    depuis = date.fromisoformat(reg.get("gmail_depuis") or "2020-01-01")
    q = f"({config.GMAIL_QUERY}) after:{depuis:%Y/%m/%d}"
    lus = ajoutes = 0
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            ids, page = [], None
            while True:
                params = {"q": q, "maxResults": 100}
                if page:
                    params["pageToken"] = page
                res = await _get(client, token, "messages", **params)
                ids += [m["id"] for m in res.get("messages", [])]
                page = res.get("nextPageToken")
                if not page or len(ids) > 2000:
                    break
            for mid in ids:
                if await conso.deja_vu(SOURCE, mid):
                    continue
                msg = await _get(client, token, f"messages/{mid}", format="full")
                lus += 1
                sujet, de, a = _entete(msg, "Subject"), _entete(msg, "From"), _entete(msg, "To")
                boutique = commandes.boutique_de(f"{de} {a}", sujet)
                if boutique and commandes.est_confirmation(sujet):
                    at = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, timezone.utc)
                    cmd = commandes.lire(_texte(msg.get("payload") or {}), boutique)
                    ajoutes += await conso.ajouter_evenements(evenements(mid, at, cmd))
                await conso.marquer_vu(SOURCE, mid)
        except ScopeManquant:
            await store.log(SOURCE, False, 0, "Accès Gmail refusé : reconnecte le compte Google (GMAIL_SYNC=true)")
            return {"status": "scope_manquant"}
    # Prochaine fois : seulement les mails récents (marge de 3 jours)
    await conso.set_reglage("gmail_depuis", (datetime.now(config.TZ).date() - timedelta(days=3)).isoformat())
    await store.log(SOURCE, True, ajoutes, f"{lus} mail(s) lus, {ajoutes} achat(s) ajoutés")
    return {"status": "ok", "lus": lus, "ajoutes": ajoutes}
