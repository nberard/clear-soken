"""Accès PostgreSQL (schéma créé par db/init.sh, recréé ici si besoin)."""
from datetime import date, datetime

import psycopg

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_metrics (
    day        date             NOT NULL,
    metric     text             NOT NULL,
    value      double precision NOT NULL,
    updated_at timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (day, metric)
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
"""


async def connect() -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(config.DATABASE_URL, autocommit=True)


async def init() -> None:
    async with await connect() as conn:
        await conn.execute(SCHEMA)


async def upsert_metrics(rows: list[tuple[date, str, float]]) -> None:
    if not rows:
        return
    async with await connect() as conn, conn.cursor() as cur:
        await cur.executemany(
            """INSERT INTO daily_metrics (day, metric, value) VALUES (%s, %s, %s)
               ON CONFLICT (day, metric) DO UPDATE
               SET value = EXCLUDED.value, updated_at = now()""",
            rows,
        )


async def upsert_sleep(rows: list[dict]) -> None:
    if not rows:
        return
    async with await connect() as conn, conn.cursor() as cur:
        await cur.executemany(
            """INSERT INTO sleep_sessions (id, start_time, end_time, minutes_asleep,
                   minutes_awake, minutes_deep, minutes_light, minutes_rem, is_main)
               VALUES (%(id)s, %(start)s, %(end)s, %(asleep)s, %(awake)s,
                       %(deep)s, %(light)s, %(rem)s, %(main)s)
               ON CONFLICT (id) DO UPDATE SET
                   start_time = EXCLUDED.start_time, end_time = EXCLUDED.end_time,
                   minutes_asleep = EXCLUDED.minutes_asleep,
                   minutes_awake = EXCLUDED.minutes_awake,
                   minutes_deep = EXCLUDED.minutes_deep,
                   minutes_light = EXCLUDED.minutes_light,
                   minutes_rem = EXCLUDED.minutes_rem,
                   is_main = EXCLUDED.is_main, updated_at = now()""",
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
            "SELECT metric, value FROM daily_metrics WHERE day = %s", (today,)
        )
        metrics = {m: v for m, v in await cur.fetchall()}
        cur = await conn.execute(
            """SELECT minutes_asleep, end_time FROM sleep_sessions
               WHERE is_main IS NOT FALSE ORDER BY end_time DESC LIMIT 1"""
        )
        sleep = await cur.fetchone()
        cur = await conn.execute(
            "SELECT at, ok, message FROM sync_log WHERE data_type = '_run' ORDER BY at DESC LIMIT 1"
        )
        last = await cur.fetchone()
    return {
        "today": metrics,
        "last_sleep_minutes": sleep[0] if sleep else None,
        "last_sleep_end": sleep[1].isoformat() if sleep else None,
        "last_sync": last[0].isoformat() if last else None,
        "last_sync_ok": last[1] if last else None,
        "last_sync_message": last[2] if last else None,
    }


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
