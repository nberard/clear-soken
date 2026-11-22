"""Rétro : noter l'humeur mois par mois depuis 2020, avec une carte d'aide-mémoire par mois.

Les cartes sont préparées sur le PC par clearmind-tools (social_analytics/retro_cards.py) : moments de la
Chronologie, événements de l'agenda, nombres de messages WhatsApp, retraits « conso », et un court résumé
des messages envoyés écrit par Claude (le texte des messages ne quitte pas le PC, seul le résumé arrive ici).
La page /conso/retro/app affiche chaque carte avec ce que mint-health sait déjà du mois (sommeil, pas,
conso) et enregistre trois notes de -3 à +3 : moyenne, pic bas, pic haut.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import Header, HTTPException
from fastapi.responses import HTMLResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import conso, store

router = conso.router
ingest_router = conso.ingest_router


def _mois(texte: str) -> date:
    try:
        a, m = texte[:7].split("-")
        return date(int(a), int(m), 1)
    except (ValueError, AttributeError):
        raise HTTPException(400, f"Mois invalide : {texte!r} (AAAA-MM attendu)")


# --- Envois depuis le PC (jeton CONSO_INGEST_TOKEN) ---

class Carte(BaseModel):
    mois: str = Field(pattern=r"^\d{4}-\d{2}$")
    chronologie: list[str] = Field(default_factory=list, max_length=200)
    agenda: list[str] = Field(default_factory=list, max_length=200)
    whatsapp: dict[str, float] = Field(default_factory=dict)
    retraits: dict[str, float] = Field(default_factory=dict)
    resume: str | None = Field(None, max_length=4000)


class Cartes(BaseModel):
    cartes: list[Carte] = Field(max_length=600)


@ingest_router.post("/retro")
async def ingest_retro(body: Cartes, x_api_key: str | None = Header(None), authorization: str | None = Header(None)):
    conso._verifier_jeton(x_api_key, authorization)
    async with await store.connect() as conn:
        async with conn.transaction():
            for c in body.cartes:
                d = c.model_dump()
                if d["resume"] is None:  # pas de résumé cette fois : garder celui déjà reçu
                    cur = await conn.execute("SELECT carte->>'resume' FROM retro_cartes WHERE mois = %s", (_mois(c.mois),))
                    row = await cur.fetchone()
                    d["resume"] = row[0] if row else None
                await conn.execute(
                    """INSERT INTO retro_cartes (mois, carte) VALUES (%s, %s)
                       ON CONFLICT (mois) DO UPDATE SET carte = EXCLUDED.carte, maj = now()""",
                    (_mois(c.mois), Jsonb(d)),
                )
    return {"recues": len(body.cartes)}


class Jour(BaseModel):
    day: date
    envoyes: int = Field(0, ge=0)
    recus: int = Field(0, ge=0)
    nuit: int = Field(0, ge=0)
    contacts: int = Field(0, ge=0)


class Activite(BaseModel):
    source: str = Field(pattern="^(whatsapp|sms|msn|instagram)$")
    jours: list[Jour] = Field(max_length=20000)


@ingest_router.post("/activite")
async def ingest_activite(body: Activite, x_api_key: str | None = Header(None), authorization: str | None = Header(None)):
    conso._verifier_jeton(x_api_key, authorization)
    async with await store.connect() as conn, conn.cursor() as cur:
        await cur.executemany(
            """INSERT INTO activite_jours (day, source, envoyes, recus, nuit, contacts)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (day, source) DO UPDATE SET envoyes = EXCLUDED.envoyes, recus = EXCLUDED.recus,
                   nuit = EXCLUDED.nuit, contacts = EXCLUDED.contacts""",
            [(j.day, body.source, j.envoyes, j.recus, j.nuit, j.contacts) for j in body.jours],
        )
    return {"jours": len(body.jours)}


# --- Page Rétro ---

@router.get("/retro/donnees")
async def donnees():
    """Un élément par mois depuis 2020 : carte, notes, et ce que mint-health sait du mois."""
    async with await store.connect() as conn:
        cur = await conn.execute(
            """WITH m AS (
                   SELECT generate_series(DATE '2020-01-01', date_trunc('month', now())::date, interval '1 month')::date AS mois
               ),
               q AS (
                   SELECT date_trunc('month', day)::date AS mois,
                          count(*) FILTER (WHERE niveau_thc > 0) AS jours_thc,
                          count(*) FILTER (WHERE niveau_max > 0 AND niveau_thc = 0) AS jours_leger,
                          count(*) FILTER (WHERE confiance <> 'inconnu') AS jours_connus
                   FROM conso_quotidien GROUP BY 1
               ),
               mq AS (
                   SELECT date_trunc('month', day)::date AS mois, avg(sommeil) AS sommeil, avg(pas) AS pas,
                          round(avg(estime)::numeric, 1) AS estime
                   FROM moral_quotidien GROUP BY 1
               )
               SELECT m.mois, c.carte, r.moyenne, r.pic_bas, r.pic_haut, r.note,
                      q.jours_thc, q.jours_leger, q.jours_connus, mq.sommeil, mq.pas, mq.estime
               FROM m
               LEFT JOIN retro_cartes c ON c.mois = m.mois
               LEFT JOIN moral_retro r ON r.mois = m.mois
               LEFT JOIN q ON q.mois = m.mois
               LEFT JOIN mq ON mq.mois = m.mois
               ORDER BY m.mois"""
        )
        rows = await cur.fetchall()
    out = []
    for mois, carte, moy, bas, haut, note, jthc, jleger, jconnus, sommeil, pas, estime in rows:
        out.append({
            "mois": mois.strftime("%Y-%m"),
            "carte": carte,
            "notes": {"moyenne": moy, "pic_bas": bas, "pic_haut": haut, "note": note},
            "sante": {
                "jours_thc": jthc, "jours_leger": jleger, "jours_connus": jconnus,
                "sommeil_h": round(sommeil / 60, 1) if sommeil else None,
                "pas": round(pas) if pas else None,
                "estime": float(estime) if estime is not None else None,
            },
        })
    reg = await conso.reglages()
    return {"mois": out, "seuil_critique": reg["seuil_critique"]}


class Note(BaseModel):
    moyenne: int | None = Field(None, ge=-3, le=3)
    pic_bas: int | None = Field(None, ge=-3, le=3)
    pic_haut: int | None = Field(None, ge=-3, le=3)
    note: str | None = Field(None, max_length=500)


@router.put("/retro/{mois}")
async def noter(mois: str, n: Note):
    m = _mois(mois)
    if m > date.today().replace(day=1):
        raise HTTPException(400, "Mois dans le futur")
    bas, haut = n.pic_bas, n.pic_haut
    if n.moyenne is not None:
        if bas is not None and bas > n.moyenne:
            raise HTTPException(400, "Le pic bas ne peut pas être au-dessus de la moyenne")
        if haut is not None and haut < n.moyenne:
            raise HTTPException(400, "Le pic haut ne peut pas être sous la moyenne")
    async with await store.connect() as conn:
        await conn.execute(
            """INSERT INTO moral_retro (mois, moyenne, pic_bas, pic_haut, note) VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (mois) DO UPDATE SET moyenne = EXCLUDED.moyenne, pic_bas = EXCLUDED.pic_bas,
                   pic_haut = EXCLUDED.pic_haut, note = EXCLUDED.note, repondu_at = now()""",
            (m, n.moyenne, bas, haut, n.note),
        )
    return {"ok": True}


@router.get("/retro/app", response_class=HTMLResponse)
async def page():
    return HTMLResponse(RETRO_HTML, headers={"Cache-Control": "no-cache"})


RETRO_HTML = (Path(__file__).parent / "retro_app.html").read_text(encoding="utf-8")
