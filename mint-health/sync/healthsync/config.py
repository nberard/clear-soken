"""Configuration lue depuis les variables d'environnement (.env)."""
import os
from zoneinfo import ZoneInfo


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Variable d'environnement manquante : {name}")
    return value


GOOGLE_CLIENT_ID = _env("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = _env("GOOGLE_CLIENT_SECRET", "")
PUBLIC_URL = _env("PUBLIC_URL", "http://localhost:8765").rstrip("/")
REDIRECT_URI = f"{PUBLIC_URL}/auth/callback"

SCOPE_PREFIX = "https://www.googleapis.com/auth/googlehealth"
SCOPES = [
    f"{SCOPE_PREFIX}.{s.strip()}"
    for s in _env(
        "GOOGLE_HEALTH_SCOPES",
        "activity_and_fitness.readonly,health_metrics_and_measurements.readonly,sleep.readonly",
    ).split(",")
    if s.strip()
]

# Types agrégés par jour via dailyRollUp (identifiants kebab-case de l'API).
ROLLUP_TYPES = [
    t.strip()
    for t in _env(
        "ROLLUP_TYPES",
        "steps,distance,total-calories,active-minutes,heart-rate,"
        "daily-resting-heart-rate,daily-heart-rate-variability,weight",
    ).split(",")
    if t.strip()
]
SYNC_SLEEP = _env("SYNC_SLEEP", "true").lower() == "true"

DATABASE_URL = _env("DATABASE_URL", "postgresql://health:health@db:5432/health")
TOKEN_FILE = _env("TOKEN_FILE", "/data/token.json")

TZ = ZoneInfo(_env("TZ", "Europe/Paris"))
SYNC_INTERVAL_MIN = int(_env("SYNC_INTERVAL_MIN", "15"))
BACKFILL_DAYS = int(_env("BACKFILL_DAYS", "90"))
RECENT_DAYS = int(_env("RECENT_DAYS", "3"))
# L'API limite la plage d'une requête ; on découpe en tranches sûres.
CHUNK_DAYS = int(_env("CHUNK_DAYS", "14"))

API_BASE = "https://health.googleapis.com/v4/users/me"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
