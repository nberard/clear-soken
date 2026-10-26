"""Accès PostgreSQL (schéma créé par db/init.sh, recréé ici si besoin)."""
from datetime import date, datetime

import psycopg
from psycopg.types.json import Jsonb

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_metrics (
    day        date             NOT NULL,
    metric     text             NOT NULL,
    value      double precision NOT NULL,
    source     text             NOT NULL DEFAULT 'google-health',
    updated_at timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (day, metric, source)
);
CREATE TABLE IF NOT EXISTS sleep_sessions (
    id             text PRIMARY KEY,
    start_time     timestamptz NOT NULL,
    end_time       timestamptz NOT NULL,
    minutes_asleep integer,
    minutes_awake  integer,
    minutes_deep   integer,
    minutes_light  integer,
    minutes_rem    integer,
    is_main        boolean,
    source         text        NOT NULL DEFAULT 'google-health',
    updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sync_log (
    id        bigserial PRIMARY KEY,
    at        timestamptz NOT NULL DEFAULT now(),
    data_type text        NOT NULL,
    ok        boolean     NOT NULL,
    rows      integer     NOT NULL DEFAULT 0,
    message   text
);
-- Enregistrements bruts reçus de Health Connect (envois incrémentaux)
CREATE TABLE IF NOT EXISTS hc_records (
    type       text        NOT NULL,
    rid        text        NOT NULL,
    day        date        NOT NULL,
    start_time timestamptz NOT NULL,
    end_time   timestamptz,
    vals       jsonb       NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (type, rid)
);
CREATE INDEX IF NOT EXISTS hc_records_type_day ON hc_records (type, day);

-- Migration des bases créées avant l'ajout des sources
ALTER TABLE daily_metrics ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'google-health';
ALTER TABLE sleep_sessions ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'google-health';
DO $$
BEGIN
    IF (SELECT array_length(conkey, 1) FROM pg_constraint
        WHERE conname = 'daily_metrics_pkey') = 2 THEN
        ALTER TABLE daily_metrics DROP CONSTRAINT daily_metrics_pkey;
        ALTER TABLE daily_metrics ADD PRIMARY KEY (day, metric, source);
    END IF;
END $$;
"""


def _views_sql(priority: list[str], tz: str = "Europe/Paris") -> str:
    """Vues lues par Grafana et /status : une seule source par jour et par métrique
    (la première de SOURCE_PRIORITY qui a une valeur), nuits sans doublon."""
    cases = " ".join(f"WHEN '{s}' THEN {i}" for i, s in enumerate(priority) if s.replace("-", "").isalnum())
    prio = f"CASE {{t}}.source {cases} ELSE 99 END"
    tz_safe = tz if all(c.isalnum() or c in "/_-+" for c in tz) else "UTC"
    return f"""
DROP VIEW IF EXISTS daily_best;
DROP VIEW IF EXISTS sleep_best;
CREATE VIEW daily_best AS
    SELECT DISTINCT ON (day, metric) day, metric, value, source, updated_at
    FROM daily_metrics m
    ORDER BY day, metric, {prio.format(t="m")};
-- main_night : la session principale du jour (fin de session, heure locale).
-- Google Health ne renseigne pas toujours is_main : on prend alors la plus longue,
-- les autres sont des siestes.
CREATE VIEW sleep_best AS
    SELECT b.*,
           COALESCE(b.is_main, row_number() OVER (
               PARTITION BY (b.end_time AT TIME ZONE '{tz_safe}')::date
               ORDER BY b.minutes_asleep DESC NULLS LAST, b.end_time - b.start_time DESC
           ) = 1) AS main_night
    FROM (
        SELECT s.* FROM sleep_sessions s
        WHERE NOT EXISTS (
            SELECT 1 FROM sleep_sessions o
            WHERE {prio.format(t="o")} < {prio.format(t="s")}
              AND o.start_time < s.end_time AND o.end_time > s.start_time
        )
    ) b;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;
    END IF;
END $$;
"""


async def connect() -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(config.DATABASE_URL, autocommit=True)


async def init() -> None:
    async with await connect() as conn:
        await conn.execute(SCHEMA)
        await conn.execute(_views_sql(config.SOURCE_PRIORITY, config.TZ.key))


async def upsert_metrics(rows: list[tuple[date, str, float]], source: str = "google-health") -> None:
    if not rows:
        return
    async with await connect() as conn, conn.cursor() as cur:
        await cur.executemany(
            """INSERT INTO daily_metrics (day, metric, value, source) VALUES (%s, %s, %s, %s)
               ON CONFLICT (day, metric, source) DO UPDATE
               SET value = EXCLUDED.value, updated_at = now()""",
            [(d, m, v, source) for d, m, v in rows],
        )


async def replace_source_metrics(
    day: date, prefixes: list[str], metrics: dict[str, float], source: str
) -> None:
    """Remplace les métriques d'un jour pour une source (efface celles devenues vides)."""
    async with await connect() as conn:
        async with conn.transaction():
            for p in prefixes:
                await conn.execute(
                    "DELETE FROM daily_metrics WHERE day = %s AND source = %s AND metric LIKE %s",
                    (day, source, p.replace("%", "") + "%"),
                )
            for metric, value in metrics.items():
                await conn.execute(
                    """INSERT INTO daily_metrics (day, metric, value, source) VALUES (%s, %s, %s, %s)
                       ON CONFLICT (day, metric, source) DO UPDATE
                       SET value = EXCLUDED.value, updated_at = now()""",
                    (day, metric, value, source),
                )


async def upsert_hc_records(rows: list[dict]) -> None:
    if not rows:
        return
    async with await connect() as conn, conn.cursor() as cur:
        await cur.executemany(
            """INSERT INTO hc_records (type, rid, day, start_time, end_time, vals)
               VALUES (%(type)s, %(rid)s, %(day)s, %(start)s, %(end)s, %(vals)s)
               ON CONFLICT (type, rid) DO UPDATE SET
                   day = EXCLUDED.day, start_time = EXCLUDED.start_time,
                   end_time = EXCLUDED.end_time, vals = EXCLUDED.vals, updated_at = now()""",
            [{**r, "vals": Jsonb(r["values"])} for r in rows],
        )


async def delete_hc_record(dtype: str, rid: str) -> date | None:
    """Supprime un enregistrement ; renvoie son jour pour le recalcul."""
    async with await connect() as conn:
        cur = await conn.execute(
            "DELETE FROM hc_records WHERE type = %s AND rid = %s RETURNING day", (dtype, rid)
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def hc_records_for(dtype: str, day: date) -> list[dict]:
    async with await connect() as conn:
        cur = await conn.execute(
            "SELECT start_time, vals FROM hc_records WHERE type = %s AND day = %s",
            (dtype, day),
        )
        return [{"start": s, "values": v} for s, v in await cur.fetchall()]


async def delete_sleep(sid: str) -> None:
    async with await connect() as conn:
        await conn.execute("DELETE FROM sleep_sessions WHERE id = %s", (sid,))


async def upsert_sleep(rows: list[dict], source: str = "google-health") -> None:
    if not rows:
        return
    rows = [{**r, "source": source} for r in rows]
    async with await connect() as conn, conn.cursor() as cur:
        await cur.executemany(
            """INSERT INTO sleep_sessions (id, start_time, end_time, minutes_asleep,
                   minutes_awake, minutes_deep, minutes_light, minutes_rem, is_main, source)
               VALUES (%(id)s, %(start)s, %(end)s, %(asleep)s, %(awake)s,
                       %(deep)s, %(light)s, %(rem)s, %(main)s, %(source)s)
               ON CONFLICT (id) DO UPDATE SET
                   start_time = EXCLUDED.start_time, end_time = EXCLUDED.end_time,
                   minutes_asleep = EXCLUDED.minutes_asleep,
                   minutes_awake = EXCLUDED.minutes_awake,
                   minutes_deep = EXCLUDED.minutes_deep,
                   minutes_light = EXCLUDED.minutes_light,
                   minutes_rem = EXCLUDED.minutes_rem,
                   is_main = EXCLUDED.is_main, source = EXCLUDED.source,
                   updated_at = now()""",
            rows,
        )


async def log(data_type: str, ok: bool, rows: int = 0, message: str | None = None) -> None:
    async with await connect() as conn:
        await conn.execute(
            "INSERT INTO sync_log (data_type, ok, rows, message) VALUES (%s, %s, %s, %s)",
            (data_type, ok, rows, message),
        )
        await conn.execute(
            "DELETE FROM sync_log WHERE at < now() - interval '30 days'"
        )


async def has_data() -> bool:
    async with await connect() as conn:
        cur = await conn.execute("SELECT EXISTS (SELECT 1 FROM daily_metrics)")
        return (await cur.fetchone())[0]


async def summary(today: date) -> dict:
    async with await connect() as conn:
        cur = await conn.execute(
            "SELECT metric, value FROM daily_best WHERE day = %s", (today,)
        )
        metrics = {m: v for m, v in await cur.fetchall()}
        cur = await conn.execute(
            """SELECT minutes_asleep, end_time FROM sleep_best
               WHERE main_night ORDER BY end_time DESC LIMIT 1"""
        )
        sleep = await cur.fetchone()
        cur = await conn.execute(
            "SELECT at, ok, message FROM sync_log WHERE data_type = '_run' ORDER BY at DESC LIMIT 1"
        )
        last = await cur.fetchone()
        cur = await conn.execute(
            "SELECT at, message FROM sync_log WHERE data_type = 'health-connect' ORDER BY at DESC LIMIT 1"
        )
        hc = await cur.fetchone()
    return {
        "today": metrics,
        "last_sleep_minutes": sleep[0] if sleep else None,
        "last_sleep_end": sleep[1].isoformat() if sleep else None,
        "last_sync": last[0].isoformat() if last else None,
        "last_sync_ok": last[1] if last else None,
        "last_sync_message": last[2] if last else None,
        "health_connect_last": hc[0].isoformat() if hc else None,
        "health_connect_message": hc[1] if hc else None,
    }


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
