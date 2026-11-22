"""Suivi de consommation de cannabinoïdes et moral du jour.

- Saisie : page /conso/app (bouton « Je viens de consommer », question du soir : moral 1-5 et
  conso du jour), notification push quotidienne à heure réglable (23 h 30 par défaut).
- Détection automatique (confiance « déduit ») : mails de commande des boutiques (gmail.py),
  notifications WhatsApp transmises par MacroDroid (/ingest/notification), historique WhatsApp
  traité sur le PC (/ingest/conso, voir whatsapp_import.py).
- Grafana lit les vues conso_jour_substance, conso_quotidien et moral_quotidien.

Une réponse du soir prime toujours sur ce qui a été déduit pour ce jour-là.
Données de santé : tout reste dans cette base, derrière le mot de passe de Caddy.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse, Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import config, store
from . import substances as sb

log = logging.getLogger("healthsync.conso")
router = APIRouter(prefix="/conso", tags=["conso"])
ingest_router = APIRouter(prefix="/ingest", tags=["conso"])

DEBUT_HISTORIQUE = date(2020, 1, 1)
REGLAGES_DEFAUT = {
    "push_heure": "23:30",
    "push_actif": True,
    # Jours de consommation déduits après un achat (boutique / message), sans réponse du soir
    "achat_jours": 14,
    "achat_rue_jours": 3,
}
SOURCES_DEDUITES = {"gmail", "notif", "whatsapp"}
KINDS = {"conso", "achat", "mention"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS conso_substances (
    code           text PRIMARY KEY,
    nom            text     NOT NULL,
    psychoactivite smallint NOT NULL CHECK (psychoactivite BETWEEN 0 AND 3),
    effet          text,
    a_confirmer    boolean  NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS conso_events (
    id         bigserial PRIMARY KEY,
    at         timestamptz NOT NULL,
    day        date        NOT NULL,
    substance  text        NOT NULL,
    kind       text        NOT NULL CHECK (kind IN ('conso', 'achat', 'mention')),
    source     text        NOT NULL,
    confiance  text        NOT NULL CHECK (confiance IN ('explicite', 'deduit')),
    grammes    real,
    ref        text,
    detail     jsonb       NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, ref, substance)
);
CREATE INDEX IF NOT EXISTS conso_events_day ON conso_events (day);
-- Réponse du soir : niveaux {code: 1-3} (vide = rien pris), moral 1-5
CREATE TABLE IF NOT EXISTS conso_jours (
    day        date PRIMARY KEY,
    niveaux    jsonb       NOT NULL DEFAULT '{}',
    moral      smallint    CHECK (moral BETWEEN 1 AND 5),
    note       text,
    repondu_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS conso_reglages (
    cle    text PRIMARY KEY,
    valeur jsonb NOT NULL
);
-- Messages déjà lus (mails sans produit reconnu inclus), pour ne pas les relire
CREATE TABLE IF NOT EXISTS conso_sources_vues (
    source text NOT NULL,
    ref    text NOT NULL,
    at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, ref)
);
CREATE TABLE IF NOT EXISTS push_abonnements (
    endpoint   text PRIMARY KEY,
    cles       jsonb       NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_ok    timestamptz,
    echecs     integer     NOT NULL DEFAULT 0
);
"""

VIEWS = """
DROP VIEW IF EXISTS moral_quotidien;
DROP VIEW IF EXISTS conso_quotidien;
DROP VIEW IF EXISTS conso_jour_substance;

-- Une ligne par jour et par substance prise (explicite ou déduite).
CREATE VIEW conso_jour_substance AS
WITH reg AS (
    SELECT
        coalesce((SELECT (valeur #>> '{}')::int FROM conso_reglages WHERE cle = 'achat_jours'), 14) AS achat_jours,
        coalesce((SELECT (valeur #>> '{}')::int FROM conso_reglages WHERE cle = 'achat_rue_jours'), 3) AS achat_rue_jours
),
reponses AS (
    SELECT j.day, n.key AS substance, least(greatest((n.value #>> '{}')::int, 0), 3) AS niveau
    FROM conso_jours j, jsonb_each(j.niveaux) n
    WHERE (n.value #>> '{}')::int > 0
),
prises AS (   -- bouton « Je viens de consommer », jours sans réponse du soir
    SELECT e.day, e.substance, least(count(*), 3)::int AS niveau
    FROM conso_events e
    WHERE e.kind = 'conso' AND e.confiance = 'explicite'
      AND NOT EXISTS (SELECT 1 FROM conso_jours j WHERE j.day = e.day)
    GROUP BY e.day, e.substance
),
deduits AS (
    SELECT d::date AS day, e.substance, 1 AS niveau
    FROM conso_events e, reg,
         generate_series(e.day,
                         e.day + CASE WHEN e.kind = 'achat'
                                      THEN (CASE WHEN e.source = 'gmail' THEN reg.achat_jours ELSE reg.achat_rue_jours END) - 1
                                      ELSE 0 END,
                         interval '1 day') d
    WHERE e.confiance = 'deduit' AND e.kind IN ('conso', 'achat')
)
SELECT day, substance, niveau, 'explicite'::text AS confiance FROM reponses
UNION ALL
SELECT day, substance, niveau, 'explicite' FROM prises
UNION ALL
SELECT DISTINCT ON (d.day, d.substance) d.day, d.substance, d.niveau, 'deduit'
FROM deduits d
WHERE d.day <= (now() AT TIME ZONE '{tz}')::date
  AND NOT EXISTS (SELECT 1 FROM conso_jours j WHERE j.day = d.day)
  AND NOT EXISTS (SELECT 1 FROM conso_events p WHERE p.day = d.day AND p.kind = 'conso' AND p.confiance = 'explicite');

-- Une ligne par jour depuis 2020 : niveau psychoactif max, confiance, substances.
CREATE VIEW conso_quotidien AS
SELECT g.day,
       coalesce(max(s.psychoactivite) FILTER (WHERE c.substance IS NOT NULL), 0) AS psychoactivite,
       coalesce(max(c.niveau) FILTER (WHERE s.psychoactivite >= 2), 0) AS niveau_thc,
       coalesce(max(c.niveau), 0) AS niveau_max,
       CASE WHEN bool_or(c.confiance = 'explicite')
                 OR EXISTS (SELECT 1 FROM conso_jours j WHERE j.day = g.day) THEN 'explicite'
            WHEN bool_or(c.confiance = 'deduit') THEN 'deduit'
            ELSE 'inconnu' END AS confiance,
       string_agg(DISTINCT coalesce(s.nom, c.substance), ', ') AS substances,
       (SELECT moral FROM conso_jours j WHERE j.day = g.day) AS moral
FROM generate_series(DATE '2020-01-01', (now() AT TIME ZONE '{tz}')::date, interval '1 day') AS g(day)
LEFT JOIN conso_jour_substance c ON c.day = g.day
LEFT JOIN conso_substances s ON s.code = c.substance
GROUP BY g.day;

-- Indice de moral (0-100) : chaque donnée comparée à ta moyenne des 30 jours précédents
-- (écart en nombre d'écarts-types), puis moyenne des données disponibles ce jour-là.
-- Sens : sommeil, pas, VFC vers le haut = mieux ; FC au repos, conso psychoactive = moins bien.
CREATE VIEW moral_quotidien AS
WITH base AS (
    SELECT q.day::date AS day, q.moral,
           (SELECT max(minutes_asleep) FROM sleep_best s
             WHERE s.main_night AND (s.end_time AT TIME ZONE '{tz}')::date = q.day) AS sommeil,
           (SELECT avg(value) FROM daily_best WHERE day = q.day AND metric = 'steps.countSum') AS pas,
           (SELECT avg(value) FROM daily_best WHERE day = q.day AND metric LIKE 'daily-resting-heart-rate.%') AS fc_repos,
           (SELECT avg(value) FROM daily_best WHERE day = q.day AND metric LIKE 'daily-heart-rate-variability.%') AS vfc,
           CASE WHEN q.confiance = 'inconnu' THEN NULL ELSE q.niveau_thc END AS conso
    FROM conso_quotidien q
),
z AS (
    SELECT b.*,
        (sommeil  - avg(sommeil)  OVER w) / nullif(stddev_samp(sommeil)  OVER w, 0) AS z_sommeil,
        (pas      - avg(pas)      OVER w) / nullif(stddev_samp(pas)      OVER w, 0) AS z_pas,
        -(fc_repos - avg(fc_repos) OVER w) / nullif(stddev_samp(fc_repos) OVER w, 0) AS z_fc,
        (vfc      - avg(vfc)      OVER w) / nullif(stddev_samp(vfc)      OVER w, 0) AS z_vfc,
        -(conso   - avg(conso)    OVER w) / nullif(stddev_samp(conso)    OVER w, 0) AS z_conso
    FROM base b
    WINDOW w AS (ORDER BY day ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING)
)
SELECT day, moral, sommeil, pas, fc_repos, vfc, conso,
       z_sommeil, z_pas, z_fc, z_vfc, z_conso,
       CASE WHEN n > 0 THEN least(100, greatest(0, 50 + 15 * total / n)) END AS indice
FROM (
    SELECT z.*,
        (CASE WHEN z_sommeil IS NULL THEN 0 ELSE 1 END + CASE WHEN z_pas IS NULL THEN 0 ELSE 1 END
       + CASE WHEN z_fc IS NULL THEN 0 ELSE 1 END + CASE WHEN z_vfc IS NULL THEN 0 ELSE 1 END
       + CASE WHEN z_conso IS NULL THEN 0 ELSE 1 END) AS n,
        coalesce(least(greatest(z_sommeil, -3), 3), 0) + coalesce(least(greatest(z_pas, -3), 3), 0)
      + coalesce(least(greatest(z_fc, -3), 3), 0) + coalesce(least(greatest(z_vfc, -3), 3), 0)
      + coalesce(least(greatest(z_conso, -3), 3), 0) AS total
    FROM z
) t;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;
    END IF;
END $$;
"""


def _tz_sql() -> str:
    tz = config.TZ.key
    return tz if all(c.isalnum() or c in "/_-+" for c in tz) else "UTC"


async def init() -> None:
    async with await store.connect() as conn:
        await conn.execute(SCHEMA)
        async with conn.cursor() as cur:
            # Catalogue : ajoute les nouvelles molécules sans écraser tes corrections
            await cur.executemany(
                """INSERT INTO conso_substances (code, nom, psychoactivite, effet, a_confirmer)
                   VALUES (%s, %s, %s, %s, %s) ON CONFLICT (code) DO NOTHING""",
                [(c, n, p, e, a) for c, (n, p, e, a) in sb.SUBSTANCES.items()],
            )
        await conn.execute(VIEWS.replace("{tz}", _tz_sql()))


# --- Réglages ---

async def reglages() -> dict:
    async with await store.connect() as conn:
        cur = await conn.execute("SELECT cle, valeur FROM conso_reglages")
        rows = dict(await cur.fetchall())
    return {**REGLAGES_DEFAUT, **{k: v for k, v in rows.items()}}


async def set_reglage(cle: str, valeur) -> None:
    async with await store.connect() as conn:
        await conn.execute(
            """INSERT INTO conso_reglages (cle, valeur) VALUES (%s, %s)
               ON CONFLICT (cle) DO UPDATE SET valeur = EXCLUDED.valeur""",
            (cle, Jsonb(valeur)),
        )


# --- Écriture des événements ---

def jour_local(at: datetime) -> date:
    return at.astimezone(config.TZ).date()


async def ajouter_evenements(rows: list[dict]) -> int:
    """rows : at, substance, kind, source, confiance, ref, grammes?, detail?. Doublons ignorés."""
    if not rows:
        return 0
    n = 0
    async with await store.connect() as conn:
        async with conn.transaction():
            for r in rows:
                cur = await conn.execute(
                    """INSERT INTO conso_events (at, day, substance, kind, source, confiance, grammes, ref, detail)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (source, ref, substance) DO NOTHING""",
                    (
                        r["at"], jour_local(r["at"]), r["substance"], r["kind"], r["source"],
                        r["confiance"], r.get("grammes"), r.get("ref"), Jsonb(r.get("detail") or {}),
                    ),
                )
                n += cur.rowcount
    return n


async def deja_vu(source: str, ref: str) -> bool:
    async with await store.connect() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM conso_sources_vues WHERE source = %s AND ref = %s", (source, ref)
        )
        return await cur.fetchone() is not None


async def marquer_vu(source: str, ref: str) -> None:
    async with await store.connect() as conn:
        await conn.execute(
            "INSERT INTO conso_sources_vues (source, ref) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (source, ref),
        )


# --- État pour la page ---

async def etat() -> dict:
    tz = config.TZ
    today = datetime.now(tz).date()
    async with await store.connect() as conn:
        cur = await conn.execute(
            "SELECT code, nom, psychoactivite, effet, a_confirmer FROM conso_substances ORDER BY psychoactivite DESC, nom"
        )
        catalogue = [
            {"code": c, "nom": n, "psy": p, "effet": e, "a_confirmer": a} for c, n, p, e, a in await cur.fetchall()
        ]
        psy = {s["code"]: s["psy"] for s in catalogue}
        fortes = [c for c, p in psy.items() if p >= sb.SEUIL_PSYCHOACTIF]

        # Dernière prise « THC ou équivalent » : bouton (heure exacte) ou réponse du soir (fin de journée)
        cur = await conn.execute(
            """SELECT max(at) FROM conso_events
               WHERE kind = 'conso' AND confiance = 'explicite' AND substance = ANY(%s)""",
            (fortes,),
        )
        derniere_bouton = (await cur.fetchone())[0]
        cur = await conn.execute(
            """SELECT max(j.day) FROM conso_jours j, jsonb_each(j.niveaux) n
               WHERE n.key = ANY(%s) AND (n.value #>> '{}')::int > 0""",
            (fortes,),
        )
        dernier_jour = (await cur.fetchone())[0]
        derniere = derniere_bouton
        if dernier_jour and (not derniere or jour_local(derniere) < dernier_jour):
            fin = datetime.combine(dernier_jour, time(23, 59), tz)
            derniere = fin

        # Substances en cours : dernier achat (≤ 45 j) + prises des 14 derniers jours
        cur = await conn.execute(
            """SELECT substance, max(at) AS at, kind, source, max(confiance) AS confiance
               FROM conso_events
               WHERE (kind = 'achat' AND at > now() - interval '45 days')
                  OR (kind = 'conso' AND at > now() - interval '14 days')
               GROUP BY substance, kind, source ORDER BY 2 DESC"""
        )
        en_cours: dict[str, dict] = {}
        for sub, at, kind, source, conf in await cur.fetchall():
            if sub not in en_cours:
                en_cours[sub] = {"code": sub, "depuis": at.isoformat(), "kind": kind, "source": source, "confiance": conf}

        cur = await conn.execute(
            """SELECT at, detail FROM conso_events WHERE kind = 'achat' AND source = 'gmail'
               ORDER BY at DESC LIMIT 1"""
        )
        row = await cur.fetchone()
        commande = {"at": row[0].isoformat(), **row[1]} if row else None

        cur = await conn.execute(
            """SELECT day, psychoactivite, niveau_thc, niveau_max, confiance, substances, moral
               FROM conso_quotidien WHERE day > %s ORDER BY day""",
            (today - timedelta(days=30),),
        )
        jours = [
            {"day": d.date().isoformat() if isinstance(d, datetime) else d.isoformat(), "psy": p, "thc": t,
             "niveau": n, "confiance": c, "substances": s, "moral": m}
            for d, p, t, n, c, s, m in await cur.fetchall()
        ]
        cur = await conn.execute("SELECT niveaux, moral, note FROM conso_jours WHERE day = %s", (today,))
        r = await cur.fetchone()
        aujourdhui = {"repondu": bool(r), "niveaux": r[0] if r else {}, "moral": r[1] if r else None}
        cur = await conn.execute(
            """SELECT id, at, substance FROM conso_events
               WHERE source = 'saisie' AND day = %s ORDER BY at""",
            (today,),
        )
        aujourdhui["prises"] = [{"id": i, "at": a.isoformat(), "code": s} for i, a, s in await cur.fetchall()]
        cur = await conn.execute("SELECT count(*) FROM push_abonnements")
        abonnes = (await cur.fetchone())[0]

    from . import push  # import tardif : évite le cycle

    return {
        "date": today.isoformat(),
        "catalogue": catalogue,
        "derniere_prise_thc": derniere.isoformat() if derniere else None,
        "en_cours": list(en_cours.values()),
        "derniere_commande": commande,
        "jours": jours,
        "aujourdhui": aujourdhui,
        "reglages": await reglages(),
        "push": {"cle_publique": push.cle_publique(), "abonnes": abonnes},
        "grafana": config.GRAFANA_MORAL_URL,
    }


# --- API de la page ---

class Prise(BaseModel):
    substance: str = Field(max_length=20)
    at: datetime | None = None


class Jour(BaseModel):
    day: date | None = None
    niveaux: dict[str, int] = Field(default_factory=dict)
    moral: int | None = Field(None, ge=1, le=5)
    note: str | None = Field(None, max_length=500)


class Reglages(BaseModel):
    push_heure: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    push_actif: bool | None = None
    achat_jours: int | None = Field(None, ge=0, le=60)
    achat_rue_jours: int | None = Field(None, ge=0, le=30)


async def _codes() -> set[str]:
    async with await store.connect() as conn:
        cur = await conn.execute("SELECT code FROM conso_substances")
        return {r[0] for r in await cur.fetchall()}


@router.get("/etat")
async def get_etat():
    return await etat()


@router.post("/prise", status_code=201)
async def post_prise(p: Prise):
    if p.substance not in await _codes():
        raise HTTPException(400, "Substance inconnue")
    at = p.at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=config.TZ)
    if at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HTTPException(400, "Date dans le futur")
    async with await store.connect() as conn:
        cur = await conn.execute(
            """INSERT INTO conso_events (at, day, substance, kind, source, confiance)
               VALUES (%s, %s, %s, 'conso', 'saisie', 'explicite') RETURNING id""",
            (at, jour_local(at), p.substance),
        )
        return {"id": (await cur.fetchone())[0]}


@router.delete("/prise/{event_id}", status_code=204)
async def delete_prise(event_id: int):
    async with await store.connect() as conn:
        await conn.execute("DELETE FROM conso_events WHERE id = %s AND source = 'saisie'", (event_id,))
    return Response(status_code=204)


@router.post("/jour")
async def post_jour(j: Jour):
    day = j.day or datetime.now(config.TZ).date()
    if day > datetime.now(config.TZ).date():
        raise HTTPException(400, "Jour dans le futur")
    codes = await _codes()
    niveaux = {k: min(max(int(v), 0), 3) for k, v in j.niveaux.items() if k in codes and v > 0}
    async with await store.connect() as conn:
        await conn.execute(
            """INSERT INTO conso_jours (day, niveaux, moral, note) VALUES (%s, %s, %s, %s)
               ON CONFLICT (day) DO UPDATE SET niveaux = EXCLUDED.niveaux, moral = EXCLUDED.moral,
                   note = EXCLUDED.note, repondu_at = now()""",
            (day, Jsonb(niveaux), j.moral, j.note),
        )
    return {"ok": True, "day": day.isoformat(), "niveaux": niveaux}


@router.put("/reglages")
async def put_reglages(r: Reglages):
    for cle, valeur in r.model_dump(exclude_none=True).items():
        await set_reglage(cle, valeur)
    return await reglages()


# --- Ingestion (MacroDroid, script PC) : protégée par CONSO_INGEST_TOKEN, pas par Caddy ---

def _verifier_jeton(x_api_key: str | None, authorization: str | None) -> None:
    if not config.CONSO_INGEST_TOKEN:
        raise HTTPException(503, "Ingestion désactivée (CONSO_INGEST_TOKEN vide)")
    given = x_api_key or (authorization or "").removeprefix("Bearer ").strip()
    if not given or not hmac.compare_digest(given.encode(), config.CONSO_INGEST_TOKEN.encode()):
        raise HTTPException(401, "Jeton invalide")


class Notification(BaseModel):
    app: str = Field("", max_length=100)
    titre: str = Field("", max_length=300)
    texte: str = Field("", max_length=4000)
    at: datetime | None = None


def ref_message(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]


@ingest_router.post("/notification")
async def ingest_notification(
    n: Notification, x_api_key: str | None = Header(None), authorization: str | None = Header(None)
):
    """Notification Android transmise par MacroDroid. Rien n'est gardé si aucune mention
    n'est détectée ; sinon seulement la date, la molécule et les mots repérés (pas le texte)."""
    _verifier_jeton(x_api_key, authorization)
    app = n.app.lower()
    if config.CONSO_NOTIF_APPS and not any(a in app for a in config.CONSO_NOTIF_APPS):
        return {"retenu": False, "raison": "application ignorée"}
    det = sb.detecter_message(n.texte)
    if not det:
        return {"retenu": False}
    at = n.at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=config.TZ)
    # Même message reçu deux fois (notification mise à jour) : même minute, même texte -> ignoré
    ref = ref_message(n.titre, n.texte, at.astimezone(timezone.utc).strftime("%Y%m%d%H%M"))
    rows = [
        {"at": at, "substance": s, "kind": det.kind, "source": "notif", "confiance": "deduit",
         "ref": ref, "detail": {"mots": det.mots, "app": n.app[:40]}}
        for s in det.substances
    ]
    added = await ajouter_evenements(rows)
    return {"retenu": True, "kind": det.kind, "substances": det.substances, "ajoutes": added}


class EvenementImport(BaseModel):
    at: datetime
    substance: str = Field(max_length=20)
    kind: str
    ref: str = Field(max_length=64)
    mots: list[str] = Field(default_factory=list, max_length=20)
    auteur: str | None = Field(None, pattern="^(moi|autre)$")


class Import(BaseModel):
    source: str = Field(pattern="^(whatsapp|sms|msn)$")
    evenements: list[EvenementImport] = Field(max_length=5000)


@ingest_router.post("/conso")
async def ingest_conso(
    body: Import, x_api_key: str | None = Header(None), authorization: str | None = Header(None)
):
    """Événements déjà détectés sur le PC (le texte des messages ne quitte pas le PC)."""
    _verifier_jeton(x_api_key, authorization)
    codes = await _codes()
    rows = []
    for e in body.evenements:
        if e.substance not in codes or e.kind not in KINDS:
            continue
        at = e.at if e.at.tzinfo else e.at.replace(tzinfo=config.TZ)
        rows.append(
            {"at": at, "substance": e.substance, "kind": e.kind, "source": body.source, "confiance": "deduit",
             "ref": e.ref, "detail": {"mots": e.mots[:20], "auteur": e.auteur}}
        )
    return {"recus": len(body.evenements), "ajoutes": await ajouter_evenements(rows)}


# --- Page, manifest, service worker ---

@router.get("/app", response_class=HTMLResponse)
async def app_page():
    return HTMLResponse(APP_HTML, headers={"Cache-Control": "no-cache"})


@router.get("/manifest.webmanifest")
async def manifest():
    return Response(MANIFEST, media_type="application/manifest+json")


@router.get("/icon.svg")
async def icon():
    return Response(ICON_SVG, media_type="image/svg+xml", headers={"Cache-Control": "max-age=86400"})


@router.get("/sw.js")
async def service_worker():
    return Response(SW_JS, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<rect width="512" height="512" rx="112" fill="#16181d"/>
<circle cx="256" cy="256" r="168" fill="#5b8def"/>
<path d="M176 300c30 36 130 36 160 0" fill="none" stroke="#fff" stroke-width="28" stroke-linecap="round"/>
<circle cx="200" cy="216" r="22" fill="#fff"/><circle cx="312" cy="216" r="22" fill="#fff"/>
</svg>"""

MANIFEST = """{
  "name": "Ma journée",
  "short_name": "Ma journée",
  "lang": "fr",
  "start_url": "app",
  "scope": "./",
  "display": "standalone",
  "background_color": "#16181d",
  "theme_color": "#16181d",
  "icons": [{ "src": "icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable" }],
  "shortcuts": [{ "name": "Je viens de consommer", "url": "app?prise=1" }]
}"""

SW_JS = r"""// Service worker de « Ma journée » : notification du soir et ouverture de la page.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
	let d = {};
	try { d = event.data ? event.data.json() : {}; } catch (_) {}
	event.waitUntil(self.registration.showNotification(d.titre || 'Ta journée', {
		body: d.texte || 'Moral et conso du jour : 10 secondes.',
		icon: 'icon.svg',
		badge: 'icon.svg',
		tag: d.tag || 'conso-jour',
		renotify: true,
		data: { url: d.url || 'app' },
	}));
});

self.addEventListener('notificationclick', (event) => {
	event.notification.close();
	const url = new URL(event.notification.data && event.notification.data.url || 'app', self.registration.scope).href;
	event.waitUntil((async () => {
		const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
		for (const w of wins) {
			if (w.url.startsWith(self.registration.scope)) { await w.navigate(url); return w.focus(); }
		}
		return self.clients.openWindow(url);
	})());
});
"""

APP_HTML = (Path(__file__).parent / "conso_app.html").read_text(encoding="utf-8")
