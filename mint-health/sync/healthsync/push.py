"""Notifications web push (VAPID) : question du soir de « Ma journée ».

Les clés VAPID sont créées au premier démarrage dans le volume des jetons (VAPID_FILE) :
les supprimer oblige à réactiver les notifications sur le téléphone.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import config, conso, store

log = logging.getLogger("healthsync.push")
_cle_publique: str | None = None


def _fichier() -> Path:
    return Path(config.VAPID_FILE)


def _charger() -> tuple[str, str] | None:
    """Renvoie (clé privée PEM, clé publique base64url) ; les crée si besoin."""
    global _cle_publique
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError:
        return None
    p = _fichier()
    if p.exists():
        d = json.loads(p.read_text())
    else:
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode()
        pub = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        d = {"prive": pem, "public": base64.urlsafe_b64encode(pub).rstrip(b"=").decode()}
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d))
        tmp.chmod(0o600)
        tmp.replace(p)
    _cle_publique = d["public"]
    return d["prive"], d["public"]


def cle_publique() -> str | None:
    if _cle_publique is None:
        try:
            _charger()
        except Exception:
            log.exception("Clés VAPID illisibles")
    return _cle_publique


def _claims() -> dict:
    sub = config.VAPID_SUB or (config.PUBLIC_URL if config.PUBLIC_URL.startswith("https://") else "mailto:mint-health@localhost")
    return {"sub": sub}


def _envoyer_un(abonnement: dict, donnees: dict, prive_pem: str) -> int:
    from py_vapid import Vapid
    from pywebpush import WebPushException, webpush

    try:
        r = webpush(
            subscription_info=abonnement,
            data=json.dumps(donnees),
            vapid_private_key=Vapid.from_pem(prive_pem.encode()),
            vapid_claims=dict(_claims()),
            ttl=6 * 3600,
        )
        return r.status_code
    except WebPushException as e:
        return e.response.status_code if e.response is not None else 0


async def envoyer(donnees: dict) -> dict:
    cles = _charger()
    if not cles:
        return {"envoyes": 0, "erreur": "pywebpush absent"}
    async with await store.connect() as conn:
        cur = await conn.execute("SELECT endpoint, cles FROM push_abonnements")
        abonnements = await cur.fetchall()
    ok = 0
    for endpoint, k in abonnements:
        code = await asyncio.to_thread(_envoyer_un, {"endpoint": endpoint, "keys": k}, donnees, cles[0])
        async with await store.connect() as conn:
            if 200 <= code < 300:
                ok += 1
                await conn.execute(
                    "UPDATE push_abonnements SET last_ok = now(), echecs = 0 WHERE endpoint = %s", (endpoint,)
                )
            elif code in (404, 410):  # abonnement expiré (désinstallation, permission retirée)
                await conn.execute("DELETE FROM push_abonnements WHERE endpoint = %s", (endpoint,))
            else:
                log.warning("Push refusé (%s)", code)
                await conn.execute(
                    "UPDATE push_abonnements SET echecs = echecs + 1 WHERE endpoint = %s", (endpoint,)
                )
    return {"envoyes": ok, "abonnes": len(abonnements)}


class Abonnement(BaseModel):
    endpoint: str = Field(max_length=1000, pattern=r"^https://")
    keys: dict[str, str]


@conso.router.post("/push/abonnement", status_code=201)
async def abonner(a: Abonnement):
    if not {"p256dh", "auth"} <= a.keys.keys():
        raise HTTPException(400, "Clés p256dh et auth attendues")
    async with await store.connect() as conn:
        await conn.execute(
            """INSERT INTO push_abonnements (endpoint, cles) VALUES (%s, %s)
               ON CONFLICT (endpoint) DO UPDATE SET cles = EXCLUDED.cles, echecs = 0""",
            (a.endpoint, Jsonb({"p256dh": a.keys["p256dh"], "auth": a.keys["auth"]})),
        )
    return {"ok": True}


class Desabonnement(BaseModel):
    endpoint: str = Field(max_length=1000)


@conso.router.post("/push/desabonnement")
async def desabonner(d: Desabonnement):
    async with await store.connect() as conn:
        await conn.execute("DELETE FROM push_abonnements WHERE endpoint = %s", (d.endpoint,))
    return {"ok": True}


@conso.router.post("/push/test")
async def tester():
    return await envoyer({"titre": "Test", "texte": "Les notifications de « Ma journée » fonctionnent.", "tag": "test"})


def doit_envoyer(maintenant: datetime, heure: str, deja_envoye: str | None, repondu: bool) -> bool:
    """Envoi une fois par jour, dès l'heure réglée passée (rattrapage si le service redémarre
    avant minuit), sauf si la journée a déjà été renseignée."""
    h, m = (int(x) for x in heure.split(":"))
    passe = (maintenant.hour, maintenant.minute) >= (h, m)
    return passe and deja_envoye != maintenant.date().isoformat() and not repondu


async def tick() -> None:
    reg = await conso.reglages()
    if not reg.get("push_actif"):
        return
    now = datetime.now(config.TZ)
    async with await store.connect() as conn:
        cur = await conn.execute("SELECT 1 FROM conso_jours WHERE day = %s", (now.date(),))
        repondu = await cur.fetchone() is not None
    if not doit_envoyer(now, reg["push_heure"], reg.get("push_dernier"), repondu):
        return
    await conso.set_reglage("push_dernier", now.date().isoformat())
    res = await envoyer({"titre": "Ta journée", "texte": "Humeur et conso du jour : 10 secondes.",
                         "url": f"app?jour={now.date().isoformat()}"})
    await store.log("push", res.get("envoyes", 0) > 0, res.get("envoyes", 0), json.dumps(res))
