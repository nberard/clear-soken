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

# --- Conso et moral (conso.py) ---
# Achats lus dans Gmail : ajoute le scope gmail.readonly (reconnecter le compte après activation).
GMAIL_SYNC = _env("GMAIL_SYNC", "false").lower() == "true"
if GMAIL_SYNC:
    SCOPES.append("https://www.googleapis.com/auth/gmail.readonly")
# Boutiques suivies, séparées par des virgules ; « :cbd » = molécule par défaut si le mail est illisible.
CONSO_BOUTIQUES = [b.split(":")[0].strip() for b in _env("CONSO_BOUTIQUES", "").split(",") if b.strip()]
_doms = " ".join(f"from:{d} to:{d}" for d in CONSO_BOUTIQUES)
GMAIL_QUERY = _env("GMAIL_QUERY", f"{{{_doms}}} subject:(commande OR order) -from:news" if _doms else "")
GMAIL_INTERVAL_MIN = int(_env("GMAIL_INTERVAL_MIN", "60"))
# Jeton des envois MacroDroid (notifications) et du script d'import WhatsApp. Vide = désactivé.
CONSO_INGEST_TOKEN = _env("CONSO_INGEST_TOKEN", "")
# Applications dont les notifications sont analysées (sous-chaîne du nom ou du paquet). Vide = toutes.
CONSO_NOTIF_APPS = [a.strip().lower() for a in _env("CONSO_NOTIF_APPS", "whatsapp").split(",") if a.strip()]
VAPID_FILE = _env("VAPID_FILE", "/data/vapid.json")
VAPID_SUB = _env("VAPID_SUB", "")
# Lien « Tableau de bord » de la page Ma journée (relatif à /health/api/conso/app sur le serveur)
GRAFANA_MORAL_URL = _env("GRAFANA_MORAL_URL", "../../d/moral")

DATABASE_URL = _env("DATABASE_URL", "postgresql://health:health@db:5432/health")
TOKEN_FILE = _env("TOKEN_FILE", "/data/token.json")

# --- Health Connect (appli Android « HC Webhook ») ---
# Jeton à mettre dans l'en-tête x-api-key de l'appli. Vide = connecteur désactivé.
HC_INGEST_TOKEN = _env("HC_INGEST_TOKEN", "")
# Ordre de préférence quand plusieurs sources ont une valeur pour le même jour.
SOURCE_PRIORITY = [
    s.strip() for s in _env("SOURCE_PRIORITY", "google-health,health-connect").split(",") if s.strip()
]

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
