"""Tests du connecteur Health Connect.

Unitaires : toujours. Intégration (vraie base) : seulement si TEST_DATABASE_URL est défini,
par ex. postgresql://health:health@localhost:5432/health
"""
import os
from datetime import date

import pytest

os.environ.setdefault("TZ", "Europe/Paris")
os.environ.setdefault("HC_INGEST_TOKEN", "secret-test")
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from healthsync import health_connect as hc  # noqa: E402

PAYLOAD = {
    "timestamp": "2026-10-25T14:00:00.000+01:00",
    "app_version": "1.9.30",
    "timezone": "Europe/Paris",
    "steps": [
        {"count": 4000, "start_time": "2026-10-25T00:00:00+02:00", "end_time": "2026-10-25T12:00:00+01:00",
         "metadata": {"id": "s1"}},
        {"count": 1500, "start_time": "2026-10-25T12:00:00+01:00", "end_time": "2026-10-25T13:00:00+01:00",
         "metadata": {"id": "s2"}},
        # 23h30 UTC le 24 = 01h30 le 25 à Paris (heure d'été) -> jour local du 25
        {"count": 100, "start_time": "2026-10-24T23:30:00Z", "end_time": "2026-10-24T23:45:00Z"},
    ],
    "distance": [{"meters": 3200.5, "start_time": "2026-10-25T08:00:00+01:00", "end_time": "2026-10-25T09:00:00+01:00"}],
    "heart_rate": [
        {"time": "2026-10-25T08:00:00+01:00", "avg": 70, "min": 60, "max": 90, "bpm": 70},
        {"time": "2026-10-25T09:00:00+01:00", "bpm": 80},
    ],
    "weight": [
        {"kilograms": 80.0, "time": "2026-10-25T07:00:00+01:00"},
        {"kilograms": 79.5, "time": "2026-10-25T21:00:00+01:00"},
    ],
    "sleep": [
        {
            "session_end_time": "2026-10-25T07:11:00+01:00",
            "duration_seconds": 8 * 3600,
            "metadata": {"id": "n1"},
            "stages": [
                {"stage": "STAGE_TYPE_LIGHT", "start_time": "2026-10-24T23:11:00+02:00",
                 "end_time": "2026-10-25T01:11:00+01:00", "duration_seconds": 3 * 3600},
                {"stage": 5, "start_time": "2026-10-25T01:11:00+01:00",
                 "end_time": "2026-10-25T03:11:00+01:00", "duration_seconds": 2 * 3600},
                {"stage": "REM", "start_time": "2026-10-25T03:11:00+01:00",
                 "end_time": "2026-10-25T05:11:00+01:00", "duration_seconds": 2 * 3600},
                {"stage": "AWAKE", "start_time": "2026-10-25T05:11:00+01:00",
                 "end_time": "2026-10-25T06:11:00+01:00", "duration_seconds": 3600},
            ],
        }
    ],
    "blood_glucose": [{"mmol_per_liter": 5.2, "time": "2026-10-25T08:00:00+01:00"}],
}
DAY = date(2026, 10, 25)


def by_type(records, t):
    return [r for r in records if r["type"] == t]


def test_parse_records_days_and_ids():
    recs = hc.parse_records(PAYLOAD)
    steps = by_type(recs, "steps")
    assert {r["day"] for r in steps} == {DAY}
    assert {r["rid"] for r in steps} == {"s1", "s2", "steps@2026-10-24T23:30:00Z"}
    assert not by_type(recs, "blood_glucose")  # type non géré


def test_daily_metrics():
    recs = hc.parse_records(PAYLOAD)
    assert hc.daily_metrics("steps", by_type(recs, "steps")) == {"steps.countSum": 5600}
    assert hc.daily_metrics("distance", by_type(recs, "distance")) == {"distance.millimetersSum": 3200500}
    hr = hc.daily_metrics("heart_rate", by_type(recs, "heart_rate"))
    assert hr == {
        "heart-rate.beatsPerMinuteAvg": 75,
        "heart-rate.beatsPerMinuteMax": 90,
        "heart-rate.beatsPerMinuteMin": 60,
    }
    assert hc.daily_metrics("weight", by_type(recs, "weight")) == {"weight.kilograms": 79.5}


def test_parse_sleep_stages():
    [n] = hc.parse_sleep(PAYLOAD)
    assert n["id"] == "hc:n1"
    assert (n["light"], n["deep"], n["rem"]) == (180, 120, 120)
    assert n["asleep"] == 420 and n["awake"] == 60
    # Début = 1re phase. Nuit du changement d'heure : 23h11 (UTC+2) -> 7h11 (UTC+1) = 9 h réelles
    assert n["start"].isoformat() == "2026-10-24T23:11:00+02:00"
    assert (n["end"] - n["start"]).total_seconds() == 9 * 3600


def test_sleep_without_stages_uses_duration():
    [n] = hc.parse_sleep({"sleep": [{"session_end_time": "2026-10-25T07:00:00+01:00", "duration_seconds": 25200}]})
    assert n["asleep"] == 420 and n["deep"] is None


# --- Intégration : vraie base PostgreSQL + API ---

needs_db = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL non défini")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from healthsync import main, sync

    async def no_loop():  # pas de synchro Google pendant les tests
        return None

    sync.loop = no_loop
    with TestClient(main.app) as c:
        # Repart d'un état propre pour le jour de test (le schéma est créé au démarrage)
        q("DELETE FROM hc_records WHERE day = %s", DAY)
        q("DELETE FROM daily_metrics WHERE day = %s", DAY)
        q("DELETE FROM sleep_sessions WHERE id IN ('hc:n1', 'gh1')")
        yield c


async def _query(sql, *args):
    from healthsync import store

    async with await store.connect() as conn:
        cur = await conn.execute(sql, args or None)
        return await cur.fetchall() if cur.description else []


def q(sql, *args):
    import asyncio

    return asyncio.run(_query(sql, *args))


@needs_db
def test_ingest_end_to_end(client):
    url = "/ingest/health-connect"
    assert client.post(url, json=PAYLOAD).status_code == 401
    assert client.post(url, json=PAYLOAD, headers={"x-api-key": "faux"}).status_code == 401

    r = client.post(url, json=PAYLOAD, headers={"x-api-key": "secret-test"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ignored_types"] == ["blood_glucose"]
    assert body["records"]["steps"] == 3 and body["records"]["sleep"] == 1

    # Renvoyer le même lot ne double pas les totaux
    client.post(url, json=PAYLOAD, headers={"Authorization": "Bearer secret-test"})
    assert q("SELECT value FROM daily_metrics WHERE day=%s AND metric='steps.countSum' AND source='health-connect'", DAY) == [(5600.0,)]

    # Envoi incrémental : un nouveau bloc de pas s'ajoute au total du jour
    client.post(url, headers={"x-api-key": "secret-test"}, json={
        "timestamp": "x", "app_version": "x", "timezone": "x",
        "steps": [{"count": 400, "start_time": "2026-10-25T13:00:00+01:00", "end_time": "2026-10-25T14:00:00+01:00",
                   "metadata": {"id": "s3"}}],
    })
    assert q("SELECT value FROM daily_best WHERE day=%s AND metric='steps.countSum'", DAY) == [(6000.0,)]

    # Suppression d'un enregistrement -> total recalculé
    client.post(url, headers={"x-api-key": "secret-test"}, json={"deleted": [{"type": "steps", "id": "s3"}]})
    assert q("SELECT value FROM daily_best WHERE day=%s AND metric='steps.countSum'", DAY) == [(5600.0,)]

    # Priorité : Google Health l'emporte quand il a une valeur le même jour
    q("INSERT INTO daily_metrics (day, metric, value, source) VALUES (%s, 'steps.countSum', 1108, 'google-health')", DAY)
    assert q("SELECT value, source FROM daily_best WHERE day=%s AND metric='steps.countSum'", DAY) == [(1108.0, "google-health")]

    # Nuits : une nuit Google Health qui chevauche masque celle de Health Connect
    assert [r[0] for r in q("SELECT id FROM sleep_best WHERE id IN ('hc:n1', 'gh1')")] == ["hc:n1"]
    q("""INSERT INTO sleep_sessions (id, start_time, end_time, minutes_asleep, source)
         VALUES ('gh1', '2026-10-24T23:30:00+02:00', '2026-10-25T07:00:00+01:00', 400, 'google-health')""")
    assert [r[0] for r in q("SELECT id FROM sleep_best WHERE id IN ('hc:n1', 'gh1')")] == ["gh1"]

    # /status lit les vues et signale le dernier envoi Health Connect
    st = client.get("/status").json()
    assert st["health_connect_last"] and "1 suppression" in st["health_connect_message"]
